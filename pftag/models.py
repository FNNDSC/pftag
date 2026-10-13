"""The data models of pftag.

A template is text with tags in it; a tag is a marker, a name, and optionally a
chain of functions. These models describe the options that fix the grammar's
markers and supply the lookups, the tokens the tokenizer finds, and the result of
processing a template.

Key components:
    - TagOptions: markers, lookups, strictness
    - FunctionCall: one function name with its arguments
    - TagToken: one tag as found in the text, with its span and functions
    - TagResult: the processed text and what happened to each tag

Typical usage:
    options = TagOptions(lookups={"pfdo": {"inputWorkingDir": "/in/a"}})
    result = Pftag(options)("%inputWorkingDir/%inputWorkingFile_rmext_.nii")

Dependencies:
    - standard library only
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

DEFAULT_TAG_MARKER: str = "%"
DEFAULT_FUNC_MARKER: str = "_"
DEFAULT_FUNC_ARG_MARKER: str = "|"
DEFAULT_FUNC_SEP: str = ","
ESCAPE: str = "\\"


@dataclass
class TagOptions:
    """Everything the tag processor needs.

    Attributes:
        tagMarker: the character that opens a tag (default ``%``).
        funcMarker: the character that opens and closes a function chain (default
            ``_``), so ``%tag_fn_``.
        funcArgMarker: separates a function from its arguments and the arguments
            from each other (default ``|``), so ``%tag_fn|a|b_``.
        funcSep: separates chained functions (default ``,``), so ``%tag_fn,gn_``.
        lookups: named dictionaries of tag name to value. Names are matched longest
            first across every dictionary and the core tags.
        strict: an unknown tag fails the result instead of being left verbatim.
        tag: the template, when given on the command line.
        json: the command prints the whole result as JSON.
        verbosity: ``0`` silences the console.

    Example:
        >>> TagOptions(lookups={"a": {"x": "1"}}).lookups["a"]["x"]
        '1'
    """

    tagMarker: str = DEFAULT_TAG_MARKER
    funcMarker: str = DEFAULT_FUNC_MARKER
    funcArgMarker: str = DEFAULT_FUNC_ARG_MARKER
    funcSep: str = DEFAULT_FUNC_SEP
    lookups: dict[str, dict[str, str]] = field(default_factory=dict)
    strict: bool = False
    tag: str = ""
    json: bool = False
    verbosity: int = 0

    def __post_init__(self) -> None:
        """Check the markers are single, distinct characters.

        Raises:
            ValueError: if a marker is not one character, or two markers coincide.
        """
        markers: dict[str, str] = {
            "tagMarker": self.tagMarker,
            "funcMarker": self.funcMarker,
            "funcArgMarker": self.funcArgMarker,
            "funcSep": self.funcSep,
        }
        for name, marker in markers.items():
            if len(marker) != 1:
                raise ValueError(f"{name} must be one character, not {marker!r}")
            if marker == ESCAPE:
                raise ValueError(f"{name} cannot be the escape character {ESCAPE!r}")
        if len(set(markers.values())) != len(markers):
            raise ValueError(f"markers must differ from each other: {markers}")


@dataclass
class FunctionCall:
    """One function in a tag's chain.

    Attributes:
        name: the function's name, as registered.
        args: its arguments, in order, already unescaped.

    Example:
        >>> FunctionCall("md5", ["4"]).args
        ['4']
    """

    name: str
    args: list[str] = field(default_factory=list)


@dataclass
class TagToken:
    """One tag found in a template.

    Attributes:
        name: the tag's name.
        functions: the chain to apply to its value, in order.
        start: index of the marker in the template.
        end: index just past the tag, and past its closing marker when it has one.
        known: the name resolved to a lookup or a core tag.

    Example:
        >>> TagToken("os", [], 0, 3, True).end
        3
    """

    name: str
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
        status: True unless ``strict`` was set and a tag was unknown, or a function
            failed.
        result: the processed text.
        template: the text as given.
        tagsFound: every tag name met, known or not, in order.
        unknownTags: the names that resolved to nothing and were left verbatim.
        functionsApplied: ``name|arg|arg`` for every function run, in order.
        errors: messages from functions that failed.

    Example:
        >>> TagResult(True, "x", "x").tagsFound
        []
    """

    status: bool
    result: str
    template: str
    tagsFound: list[str] = field(default_factory=list)
    unknownTags: list[str] = field(default_factory=list)
    functionsApplied: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def toDict(self) -> dict[str, object]:
        """A JSON-ready view of the result."""
        return asdict(self)
