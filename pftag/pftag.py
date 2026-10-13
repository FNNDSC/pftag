"""The pftag engine: find the tags in a template and replace each with its value.

A template is ordinary text with tags in it. A tag is the tag marker, a name, and
optionally a function chain between two function markers::

    %name
    %name_fn_
    %name_fn|arg|arg,fn2|arg_

The engine scans the text once, left to right. At a marker it matches the longest
known name (from the core tags and the registered lookups); a name it does not know
is left in the text as written, unless ``strict`` is set. A known tag's value is passed
through its functions in order and the result replaces the tag. Backslash before a
marker makes it literal, inside or outside a tag.

Key components:
    - Pftag: the engine; ``lookup_add`` registers names, ``tag_process`` runs a template
    - CORE_TAGS: the names every engine knows (``timestamp``, ``platform``, ...)
    - coreTag_value: their values

Typical usage:
    tagger = Pftag(TagOptions(lookups={"run": {"subject": "sub-01"}}))
    tagger("%subject_upper_-%timestamp_chrplc|:|-_.log").result

Dependencies:
    - pftag.models, pftag.functions
"""

from __future__ import annotations

import json
import logging
import platform
import re
from datetime import UTC, datetime

from pftag.functions import FunctionError, FunctionRegistry
from pftag.models import ESCAPE, FunctionCall, TagOptions, TagResult, TagToken

logger: logging.Logger = logging.getLogger("pftag")

CORE_LOOKUP: str = "core"
CORE_TAGS: tuple[str, ...] = ("literal", "os", "platform", "release", "machine", "arch", "timestamp")
IDENTIFIER: re.Pattern[str] = re.compile(r"[A-Za-z][A-Za-z0-9]*")
FUNCTION_NAME: re.Pattern[str] = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def coreTag_value(name: str) -> str:
    """The value of a core tag, computed when asked.

    Args:
        name: one of ``CORE_TAGS``.

    Returns:
        ``literal`` for ``literal``; the OS name, platform system, release, machine
        and architecture from ``platform``; the current local time in ISO 8601 with
        offset for ``timestamp``.

    Raises:
        KeyError: for a name that is not a core tag.
    """
    match name:
        case "literal":
            return "literal"
        case "os":
            return __import__("os").name
        case "platform":
            return platform.system()
        case "release":
            return platform.release()
        case "machine":
            return platform.machine()
        case "arch":
            return "-".join(platform.architecture())
        case "timestamp":
            return datetime.now(UTC).astimezone().isoformat()
        case _:
            raise KeyError(name)


class Pftag:
    """Find tags in templates and replace them with their values.

    Attributes:
        options: the markers, lookups and strictness in force.
        registry: the functions tags can be passed through.
        lookups: name to value, flattened across every registered dictionary; a
            later registration of the same name wins.
        lookupNames: dictionary name to its tag names, as registered.

    Example:
        >>> Pftag()("%literal_echo|hi,upper_")  # doctest: +SKIP
        TagResult(status=True, result='HI', ...)
    """

    def __init__(self, options: TagOptions | None = None, registry: FunctionRegistry | None = None) -> None:
        self.options: TagOptions = options if options is not None else TagOptions()
        self.registry: FunctionRegistry = registry if registry is not None else FunctionRegistry()
        self.lookups: dict[str, str] = {}
        self.lookupNames: dict[str, list[str]] = {CORE_LOOKUP: list(CORE_TAGS)}
        for name, values in self.options.lookups.items():
            self.lookup_add(name, values)

    def lookup_add(self, name: str, values: dict[str, str]) -> None:
        """Register a named dictionary of tags.

        Args:
            name: the dictionary's name, for reporting.
            values: tag name to value. Values are stringified.

        Raises:
            ValueError: if a tag name is empty, or contains a marker or the escape.
        """
        reserved: str = (
            self.options.tagMarker
            + self.options.funcMarker
            + self.options.funcArgMarker
            + self.options.funcSep
            + ESCAPE
        )
        for tag in values:
            if not tag or any(char in reserved for char in tag):
                raise ValueError(f"tag name {tag!r} in lookup {name!r} is empty or contains a marker")
        self.lookupNames[name] = list(values)
        for tag, value in values.items():
            self.lookups[tag] = str(value)

    def lookups_addFromJson(self, text: str) -> None:
        """Register lookups given as JSON, as ``--lookupDictAdd`` passes them.

        Args:
            text: ``{"name": {"tag": "value"}}``, or the 1.x list form
                ``[{"name": {"tag": "value"}}, ...]``.

        Raises:
            ValueError: if the JSON does not have one of those shapes.
        """
        try:
            parsed: object = json.loads(text)
        except json.JSONDecodeError as err:
            raise ValueError(f"lookups are not valid JSON: {err}") from err
        groups: list[dict[str, dict[str, str]]]
        if isinstance(parsed, dict):
            groups = [parsed]
        elif isinstance(parsed, list):
            groups = parsed
        else:
            raise ValueError("lookups must be a JSON object or a list of objects")
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError("each lookup group must be a JSON object")
            for name, values in group.items():
                if not isinstance(values, dict):
                    raise ValueError(f"lookup {name!r} must map tag names to values")
                self.lookup_add(str(name), {str(k): str(v) for k, v in values.items()})

    def tagNames(self) -> list[str]:
        """Every known tag name, longest first, so matching prefers the longest."""
        names: set[str] = set(self.lookups) | set(CORE_TAGS)
        return sorted(names, key=lambda name: (-len(name), name))

    def value_lookup(self, name: str) -> str | None:
        """The value of a known tag, or None.

        A registered lookup wins over a core tag of the same name.
        """
        if name in self.lookups:
            return self.lookups[name]
        if name in CORE_TAGS:
            return coreTag_value(name)
        return None

    def name_match(self, template: str, start: int) -> str | None:
        """The longest known tag name beginning at ``start``, or None."""
        for name in self.tagNames():
            if template.startswith(name, start):
                return name
        return None

    def chain_parse(self, template: str, start: int) -> tuple[list[FunctionCall], int] | None:
        """Parse a function chain that opened just before ``start``.

        Args:
            template: the text.
            start: the index after the opening function marker.

        Returns:
            The calls and the index after the closing function marker, or None if
            the chain is malformed or never closed.
        """
        argMarker: str = self.options.funcArgMarker
        sep: str = self.options.funcSep
        close: str = self.options.funcMarker
        calls: list[FunctionCall] = []
        index: int = start
        while True:
            nameMatch: re.Match[str] | None = FUNCTION_NAME.match(template, index)
            if nameMatch is None:
                return None
            call: FunctionCall = FunctionCall(nameMatch.group())
            index = nameMatch.end()
            while index < len(template) and template[index] == argMarker:
                arg, index = self.argument_read(template, index + 1)
                call.args.append(arg)
            calls.append(call)
            if index >= len(template):
                return None
            if template[index] == sep:
                index += 1
                continue
            if template[index] == close:
                return calls, index + 1
            return None

    def argument_read(self, template: str, start: int) -> tuple[str, int]:
        """Read one function argument.

        An argument runs to the next argument marker, function separator or closing
        function marker; a backslash before any of those keeps it in the argument.

        Args:
            template: the text.
            start: where the argument begins.

        Returns:
            The unescaped argument and the index of the character that ended it.
        """
        stops: str = self.options.funcArgMarker + self.options.funcSep + self.options.funcMarker
        out: list[str] = []
        index: int = start
        while index < len(template):
            char: str = template[index]
            if char == ESCAPE and index + 1 < len(template) and template[index + 1] in stops + ESCAPE:
                out.append(template[index + 1])
                index += 2
                continue
            if char in stops:
                break
            out.append(char)
            index += 1
        return "".join(out), index

    def tag_process(self, template: str) -> TagResult:
        """Replace every tag in a template.

        Args:
            template: the text to process.

        Returns:
            The processed text and an account of every tag met. ``status`` is False
            when ``strict`` is set and a tag was unknown, or when a function failed;
            a failed tag is left as written.
        """
        result: TagResult = TagResult(status=True, result="", template=template)
        marker: str = self.options.tagMarker
        markers: str = marker + self.options.funcMarker + self.options.funcArgMarker + self.options.funcSep
        out: list[str] = []
        index: int = 0
        while index < len(template):
            char: str = template[index]
            if char == ESCAPE and index + 1 < len(template) and template[index + 1] in markers + ESCAPE:
                out.append(template[index + 1])
                index += 2
                continue
            if char != marker:
                out.append(char)
                index += 1
                continue
            token: TagToken | None = self.token_read(template, index)
            if token is None:
                out.append(char)
                index += 1
                continue
            result.tagsFound.append(token.name)
            if not token.known:
                result.unknownTags.append(token.name)
                if self.options.strict:
                    result.status = False
                    result.errors.append(f"unknown tag {marker}{token.name}")
                out.append(token.text(template))
            else:
                out.append(self.token_render(token, template, result))
            index = token.end
        result.result = "".join(out)
        return result

    def token_read(self, template: str, start: int) -> TagToken | None:
        """Read the tag that opens at ``start``.

        Returns:
            A known token with its function chain; an unknown token spanning the
            identifier after the marker; or None when no identifier follows the
            marker, which makes the marker literal.
        """
        nameStart: int = start + 1
        name: str | None = self.name_match(template, nameStart)
        if name is None:
            identifier: re.Match[str] | None = IDENTIFIER.match(template, nameStart)
            if identifier is None:
                return None
            return TagToken(identifier.group(), [], start, identifier.end(), known=False)
        end: int = nameStart + len(name)
        functions: list[FunctionCall] = []
        if end < len(template) and template[end] == self.options.funcMarker:
            parsed: tuple[list[FunctionCall], int] | None = self.chain_parse(template, end + 1)
            if parsed is not None:
                functions, end = parsed
        return TagToken(name, functions, start, end, known=True)

    def token_render(self, token: TagToken, template: str, result: TagResult) -> str:
        """The text a known token becomes.

        Args:
            token: the token.
            template: the text, for the fallback when a function fails.
            result: the running result, which records applied functions and errors.

        Returns:
            The value after its functions, or the tag as written if a function failed.
        """
        value: str | None = self.value_lookup(token.name)
        if value is None:
            return token.text(template)
        for call in token.functions:
            try:
                value = self.registry.apply(call.name, value, call.args)
            except FunctionError as err:
                result.status = False
                result.errors.append(f"{token.text(template)}: {err}")
                logger.error("%s", err)
                return token.text(template)
            result.functionsApplied.append("|".join([call.name, *call.args]))
        return value

    def __call__(self, template: str) -> TagResult:
        """``tag_process`` as a call."""
        return self.tag_process(template)
