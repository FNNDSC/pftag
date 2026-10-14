"""pftag: a string template processor.

Text with ``%{tags}`` in it is resolved at run time: each tag names a value from the
core tags (``%{timestamp}``, ``%{hostname}``, ...) or from dictionaries the caller
registers, and may be piped through functions, ``%{file|rmext|upper}``. Both a library
and a command.

Key components:
    - Pftag: the engine, with ``process`` for text and ``argv_process`` for commands
    - TagOptions, TagResult, ArgvResult: options in, results out
    - FunctionRegistry: the functions, extensible
    - __main__: the ``pftag`` command

Typical usage:
    from pftag import Pftag, TagOptions
    Pftag(TagOptions(lookups={"run": {"subject": "sub-01"}}))("%{subject}-%{date}.log").result

Dependencies:
    - faker, optionally, for the dcmname function (``pip install 'pftag[names]'``)
"""

from __future__ import annotations

__version__: str = "3.1.0"

from pftag.functions import FunctionError, FunctionRegistry
from pftag.models import ArgvResult, FunctionCall, TagOptions, TagResult, TagToken
from pftag.pftag import CORE_TAGS, Pftag, TagSyntaxError, coreTag_value

__all__ = [
    "CORE_TAGS",
    "ArgvResult",
    "FunctionCall",
    "FunctionError",
    "FunctionRegistry",
    "Pftag",
    "TagOptions",
    "TagResult",
    "TagSyntaxError",
    "TagToken",
    "__version__",
    "coreTag_value",
]
