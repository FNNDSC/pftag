"""The pftag engine: find the ``%{...}`` tags in a template and replace each one.

A template is text. A tag is ``%{`` ... ``}``: a head, then zero or more functions
separated by ``|``. The head is a name, qualified or not, or a quoted literal::

    %{timestamp}
    %{pfdo.inputWorkingFile}
    %{inputWorkingFile|rmext}.jpg
    %{timestamp|replace(:,-)|md5(6)}
    %{"Subject12345"|sha256(8)}

Nothing outside ``%{...}`` is a tag, so ``printf "%s"``, ``date +%Y%m%d`` and
``%20`` in a URL pass through untouched. ``\\%{`` is a literal ``%{``. An unknown name
is left as written and reported; a bare ``%name`` of a known name outside braces is
reported as a 1.x-style tag; ``strict`` fails both. A failing function leaves its tag
as written and fails the result.

Key components:
    - Pftag: the engine; ``lookup_add`` registers names, ``process`` runs a template,
      ``argv_process`` runs a command line one argument at a time
    - CORE_TAGS: ``timestamp``, ``date``, ``hostname``, ``platform``, ``user``, ``pid``

Typical usage:
    tagger = Pftag(TagOptions(lookups={"run": {"subject": "sub-01"}}))
    tagger("%{subject|upper}-%{timestamp|strftime(%Y%m%d)}.log").result

Dependencies:
    - pftag.models, pftag.functions
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import platform
import re
import socket
from datetime import UTC, datetime

from pftag.functions import FunctionError, FunctionRegistry
from pftag.models import (
    ESCAPE,
    PIPE,
    QUALIFIER,
    TAG_CLOSE,
    TAG_OPEN,
    ArgvResult,
    FunctionCall,
    TagOptions,
    TagResult,
    TagToken,
)

logger: logging.Logger = logging.getLogger("pftag")

CORE_LOOKUP: str = "core"
CORE_TAGS: tuple[str, ...] = ("timestamp", "date", "hostname", "platform", "user", "pid")
NAME: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?")
FUNCTION_NAME: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
LEGACY_TAG: re.Pattern[str] = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)")
QUOTES: str = "\"'"
BARE_ARG_STOPS: str = ",)" + PIPE + TAG_CLOSE


def legacyName_find(identifier: str, known: set[str]) -> str | None:
    """The known name a bare ``%identifier`` was probably meant as, if any.

    A 1.x tag was ``%name`` or ``%name_fn|args_``, so the identifier after a bare
    ``%`` is a known name, or a known name followed by ``_`` and a function chain.

    Args:
        identifier: the text after a bare ``%``.
        known: every unqualified name that resolves.

    Returns:
        The name, or None when the identifier does not look like a 1.x tag.
    """
    if identifier in known:
        return identifier
    for name in sorted(known, key=len, reverse=True):
        if identifier.startswith(name + "_"):
            return name
    return None


class TagSyntaxError(ValueError):
    """A ``%{...}`` tag could not be parsed."""


def coreTag_value(name: str) -> str:
    """The value of a core tag, computed when asked.

    Args:
        name: one of ``CORE_TAGS``.

    Returns:
        The current local time in ISO 8601 with offset; today's date; the host name;
        the platform system; the user's login name, or the numeric uid when the
        process has no passwd entry; the process id.

    Raises:
        KeyError: for a name that is not a core tag.
    """
    match name:
        case "timestamp":
            return datetime.now(UTC).astimezone().isoformat()
        case "date":
            return datetime.now(UTC).astimezone().date().isoformat()
        case "hostname":
            return socket.gethostname()
        case "platform":
            return platform.system()
        case "user":
            try:
                return getpass.getuser()
            except (KeyError, OSError):
                return str(os.getuid())
        case "pid":
            return str(os.getpid())
        case _:
            raise KeyError(name)


class Pftag:
    """Find tags in templates and replace them with their values.

    Attributes:
        options: the lookups and strictness in force.
        registry: the functions tags can be piped through.
        lookups: dictionary name to its tag names and values, as registered.
        names: tag name to the dictionary it belongs to, for unqualified lookup.

    Example:
        >>> Pftag()("%{\\"hi\\"|upper}").result
        'HI'
    """

    def __init__(self, options: TagOptions | None = None, registry: FunctionRegistry | None = None) -> None:
        self.options: TagOptions = options if options is not None else TagOptions()
        self.registry: FunctionRegistry = registry if registry is not None else FunctionRegistry()
        self.lookups: dict[str, dict[str, str]] = {}
        self.names: dict[str, str] = {}
        for name, values in self.options.lookups.items():
            self.lookup_add(name, values)

    def lookup_add(self, name: str, values: dict[str, object]) -> None:
        """Register a named dictionary of tags.

        Args:
            name: the dictionary's name, usable as a qualifier: ``%{name.tag}``.
            values: tag name to value; values are stringified.

        Raises:
            ValueError: if the dictionary name or a tag name is not an identifier, or a
                tag name is already defined by another dictionary.
        """
        if not FUNCTION_NAME.fullmatch(name) or name == CORE_LOOKUP:
            raise ValueError(f"lookup name {name!r} must be an identifier other than {CORE_LOOKUP!r}")
        for tag in values:
            if not FUNCTION_NAME.fullmatch(str(tag)):
                raise ValueError(f"tag name {tag!r} in lookup {name!r} must be an identifier")
            owner: str | None = self.names.get(str(tag))
            if owner is not None and owner != name:
                raise ValueError(f"tag {tag!r} is already defined by lookup {owner!r}; qualify or rename it")
        self.lookups[name] = {str(tag): str(value) for tag, value in values.items()}
        for tag in self.lookups[name]:
            self.names[tag] = name

    def lookups_addFromJson(self, text: str) -> None:
        """Register lookups given as JSON, as ``--lookupDictAdd`` passes them.

        Args:
            text: ``{"name": {"tag": "value"}}``, or a list of such objects.

        Raises:
            ValueError: if the JSON does not have one of those shapes.
        """
        try:
            parsed: object = json.loads(text)
        except json.JSONDecodeError as err:
            raise ValueError(f"lookups are not valid JSON: {err}") from err
        groups: list[object] = parsed if isinstance(parsed, list) else [parsed]
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError("lookups must be a JSON object or a list of objects")
            for name, values in group.items():
                if not isinstance(values, dict):
                    raise ValueError(f"lookup {name!r} must map tag names to values")
                self.lookup_add(str(name), values)

    def value_lookup(self, head: str) -> str | None:
        """The value of a tag head, or None when unknown.

        Args:
            head: ``name`` or ``lookup.name``; ``core.name`` reaches a core tag.

        Returns:
            The value, or None.
        """
        lookupName, _, tag = head.rpartition(QUALIFIER)
        if lookupName:
            if lookupName == CORE_LOOKUP:
                return coreTag_value(tag) if tag in CORE_TAGS else None
            return self.lookups.get(lookupName, {}).get(tag)
        owner: str | None = self.names.get(head)
        if owner is not None:
            return self.lookups[owner][head]
        if head in CORE_TAGS:
            return coreTag_value(head)
        return None

    def knownNames(self) -> set[str]:
        """Every unqualified name that resolves."""
        return set(self.names) | set(CORE_TAGS)

    def process(self, template: str) -> TagResult:
        """Replace every tag in a template.

        Args:
            template: the text to process.

        Returns:
            The processed text and an account of every tag met.
        """
        result: TagResult = TagResult(status=True, result="", template=template)
        out: list[str] = []
        index: int = 0
        while index < len(template):
            if template.startswith(ESCAPE + TAG_OPEN, index):
                out.append(TAG_OPEN)
                index += len(ESCAPE + TAG_OPEN)
                continue
            if not template.startswith(TAG_OPEN, index):
                out.append(template[index])
                index += 1
                continue
            try:
                token: TagToken = self.token_parse(template, index)
            except TagSyntaxError as err:
                result.status = False
                result.errors.append(str(err))
                out.append(template[index:])
                break
            out.append(self.token_render(token, template, result))
            index = token.end
        result.result = "".join(out)
        self.legacy_check(template, result)
        return result

    def legacy_check(self, template: str, result: TagResult) -> None:
        """Report bare ``%name`` occurrences of known names, which look like 1.x tags.

        Args:
            template: the text.
            result: the result to record them on; ``strict`` fails it.
        """
        known: set[str] = self.knownNames()
        for match in LEGACY_TAG.finditer(template):
            if template.startswith(TAG_OPEN, match.start()):
                continue
            name: str | None = legacyName_find(match.group(1), known)
            if name is not None:
                result.legacyTags.append("%" + name)
                message: str = f"%{name} looks like a 1.x tag; write %{{{name}}}"
                if self.options.strict:
                    result.status = False
                    result.errors.append(message)
                else:
                    logger.warning("%s", message)

    def token_parse(self, template: str, start: int) -> TagToken:
        """Parse the tag opening at ``start``.

        Args:
            template: the text.
            start: the index of ``%{``.

        Returns:
            The token, with its head, chain and span.

        Raises:
            TagSyntaxError: for an empty head, a bad function, or a missing ``}``.
        """
        index: int = start + len(TAG_OPEN)
        index = self.whitespace_skip(template, index)
        head: str
        isLiteral: bool
        if index < len(template) and template[index] in QUOTES:
            head, index = self.quoted_read(template, index)
            isLiteral = True
        else:
            nameMatch: re.Match[str] | None = NAME.match(template, index)
            if nameMatch is None:
                raise TagSyntaxError(f"tag at {start} has no name: {template[start : start + 20]!r}")
            head, index = nameMatch.group(), nameMatch.end()
            isLiteral = False
        functions: list[FunctionCall] = []
        index = self.whitespace_skip(template, index)
        while index < len(template) and template[index] == PIPE:
            call, index = self.call_parse(template, index + 1)
            functions.append(call)
            index = self.whitespace_skip(template, index)
        if index >= len(template) or template[index] != TAG_CLOSE:
            raise TagSyntaxError(f"tag at {start} is not closed: {template[start : start + 40]!r}")
        known: bool = isLiteral or self.value_lookup(head) is not None
        return TagToken(head, isLiteral, functions, start, index + 1, known)

    def call_parse(self, template: str, start: int) -> tuple[FunctionCall, int]:
        """Parse ``name`` or ``name(args)`` after a pipe.

        Returns:
            The call and the index after it.

        Raises:
            TagSyntaxError: for a missing name or an unclosed argument list.
        """
        index: int = self.whitespace_skip(template, start)
        nameMatch: re.Match[str] | None = FUNCTION_NAME.match(template, index)
        if nameMatch is None:
            raise TagSyntaxError(f"expected a function name at {index}: {template[index : index + 20]!r}")
        call: FunctionCall = FunctionCall(nameMatch.group())
        index = self.whitespace_skip(template, nameMatch.end())
        if index < len(template) and template[index] == "(":
            index = self.whitespace_skip(template, index + 1)
            if index < len(template) and template[index] == ")":
                return call, index + 1
            while True:
                arg, index = self.argument_read(template, index)
                call.args.append(arg)
                index = self.whitespace_skip(template, index)
                if index >= len(template):
                    raise TagSyntaxError(f"arguments of {call.name} are not closed")
                if template[index] == ",":
                    index = self.whitespace_skip(template, index + 1)
                    continue
                if template[index] == ")":
                    return call, index + 1
                raise TagSyntaxError(f"unexpected {template[index]!r} in arguments of {call.name}")
        return call, index

    def argument_read(self, template: str, start: int) -> tuple[str, int]:
        """Read one argument: quoted with escapes, or bare up to ``,`` or ``)``.

        Returns:
            The argument's text and the index after it. A bare argument is trimmed.
        """
        if start < len(template) and template[start] in QUOTES:
            return self.quoted_read(template, start)
        index: int = start
        while index < len(template) and template[index] not in BARE_ARG_STOPS:
            index += 1
        return template[start:index].strip(), index

    @staticmethod
    def quoted_read(template: str, start: int) -> tuple[str, int]:
        """Read a quoted string opening at ``start``; ``\\"``, ``\\'`` and ``\\\\`` escape.

        Returns:
            The unquoted text and the index after the closing quote.

        Raises:
            TagSyntaxError: if the quote never closes.
        """
        quote: str = template[start]
        out: list[str] = []
        index: int = start + 1
        while index < len(template):
            char: str = template[index]
            if char == ESCAPE and index + 1 < len(template) and template[index + 1] in QUOTES + ESCAPE:
                out.append(template[index + 1])
                index += 2
                continue
            if char == quote:
                return "".join(out), index + 1
            out.append(char)
            index += 1
        raise TagSyntaxError(f"quote opened at {start} is not closed: {template[start : start + 20]!r}")

    @staticmethod
    def whitespace_skip(template: str, index: int) -> int:
        """The index of the next non-space character at or after ``index``."""
        while index < len(template) and template[index] in " \t":
            index += 1
        return index

    def token_render(self, token: TagToken, template: str, result: TagResult) -> str:
        """The text a token becomes, recording what happened on the result.

        Args:
            token: the parsed tag.
            template: the text, for the verbatim fallback.
            result: the running result.

        Returns:
            The head's value after its functions; the tag as written when the head is
            unknown or a function fails.
        """
        result.tagsFound.append(token.head)
        value: str | None = token.head if token.isLiteral else self.value_lookup(token.head)
        if value is None:
            result.unknownTags.append(token.head)
            if self.options.strict:
                result.status = False
                result.errors.append(f"unknown tag {token.text(template)}")
            return token.text(template)
        for call in token.functions:
            try:
                value = self.registry.apply(call.name, value, call.args)
            except FunctionError as err:
                result.status = False
                result.errors.append(f"{token.text(template)}: {err}")
                return token.text(template)
            result.functionsApplied.append(f"{call.name}({','.join(call.args)})")
        return value

    def argv_process(self, argv: list[str]) -> ArgvResult:
        """Process a command line one argument at a time.

        Each argument is a template of its own, so a value with a space or a quote stays
        inside its argument and cannot change the shape of the command. The caller
        splits the user's command (``shlex.split``) before calling this.

        Args:
            argv: the command and its arguments.

        Returns:
            The processed arguments and each one's result. A command whose ``status`` is
            False must not be run.
        """
        results: list[TagResult] = [self.process(argument) for argument in argv]
        return ArgvResult(
            status=all(result.status for result in results),
            argv=[result.result for result in results],
            results=results,
        )

    def __call__(self, template: str) -> TagResult:
        """``process`` as a call."""
        return self.process(template)
