"""The data models of pftag.

A template is text with ``%{...}`` tags in it. These models describe the options a
processor is built with, the parts a tag parses into, and what processing a template
or a command line produced.

Key components:
    - TagOptions: lookups and strictness
    - FunctionCall: one function name with its arguments
    - TagToken: one parsed tag with its span, head and chain
    - TagResult: a processed template and an account of every tag
    - ArgvResult: a processed command line

Typical usage:
    options = TagOptions(lookups={"pfdo": {"inputWorkingDir": "/in/a"}})
    result = Pftag(options)("%{inputWorkingDir}/%{inputWorkingFile|rmext}.nii")

Dependencies:
    - standard library only
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

TAG_OPEN: str = "%{"
TAG_CLOSE: str = "}"
PIPE: str = "|"
ESCAPE: str = "\\"
QUALIFIER: str = "."


@dataclass
class TagOptions:
    """Everything the tag processor needs.

    Attributes:
        lookups: named dictionaries of tag name to value. A name may appear in one
            dictionary only, unless it is always written qualified, ``%{dict.name}``.
        strict: an unknown tag, or a 1.x-style bare ``%name`` of a known name, fails
            the result instead of being left verbatim and warned about.
        tag: the template, when given on the command line.
        json: the command prints the whole result as JSON.
        verbosity: ``0`` prints only the result.

    Example:
        >>> TagOptions(lookups={"a": {"x": "1"}}).lookups["a"]["x"]
        '1'
    """

    lookups: dict[str, dict[str, str]] = field(default_factory=dict)
    strict: bool = False
    tag: str = ""
    json: bool = False
    verbosity: int = 0


@dataclass
class FunctionCall:
    """One function in a tag's chain.

    Attributes:
        name: the function's name, as registered.
        args: its arguments, in order, unquoted and unescaped.

    Example:
        >>> FunctionCall("md5", ["4"]).args
        ['4']
    """

    name: str
    args: list[str] = field(default_factory=list)


@dataclass
class TagToken:
    """One ``%{...}`` tag found in a template.

    Attributes:
        head: the tag name, qualified or not, or the literal text when ``isLiteral``.
        isLiteral: the head was a quoted string rather than a name.
        functions: the chain to apply to the head's value, in order.
        start: index of ``%{`` in the template.
        end: index just past the closing ``}``.
        known: the head is a literal or resolved to a value.

    Example:
        >>> TagToken("timestamp", False, [], 0, 12, True).end
        12
    """

    head: str
    isLiteral: bool
    functions: list[FunctionCall]
    start: int
    end: int
    known: bool

    def text(self, template: str) -> str:
        """The tag's own characters in the template."""
        return template[self.start : self.end]


@dataclass
class TagResult:
    """The outcome of processing a template.

    Attributes:
        status: False when ``strict`` met an unknown or 1.x-style tag, a tag did not
            parse, or a function failed.
        result: the processed text; a failing tag is left as written.
        template: the text as given.
        tagsFound: every tag head met, in order.
        unknownTags: heads that resolved to nothing and were left verbatim.
        legacyTags: bare ``%name`` occurrences of known names outside braces, which
            look like 1.x templates and are not substituted.
        functionsApplied: ``name(arg,arg)`` for every function run, in order.
        errors: what went wrong, one message per failure.

    Example:
        >>> TagResult(True, "x", "x").tagsFound
        []
    """

    status: bool
    result: str
    template: str
    tagsFound: list[str] = field(default_factory=list)
    unknownTags: list[str] = field(default_factory=list)
    legacyTags: list[str] = field(default_factory=list)
    functionsApplied: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def toDict(self) -> dict[str, object]:
        """A JSON-ready view of the result."""
        return asdict(self)


@dataclass
class ArgvResult:
    """The outcome of processing a command line, one argument at a time.

    Attributes:
        status: every argument processed cleanly; a command whose status is False
            must not be run.
        argv: the processed arguments, one per input argument.
        results: the TagResult of each argument, in order.

    Example:
        >>> ArgvResult(True, ["ls"], []).argv
        ['ls']
    """

    status: bool
    argv: list[str]
    results: list[TagResult] = field(default_factory=list)

    def errors(self) -> list[str]:
        """Every error across the arguments, in order."""
        return [error for result in self.results for error in result.errors]

    def toDict(self) -> dict[str, object]:
        """A JSON-ready view of the result."""
        return asdict(self)
