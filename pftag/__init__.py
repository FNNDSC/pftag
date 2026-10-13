"""pftag: a string template processor.

Text with ``%tags`` in it is resolved at run time: each tag is looked up in the
core tags (``%timestamp``, ``%platform``, ...) or in dictionaries the caller
registers, and may be passed through a chain of functions written after it,
``%tag_fn|arg,fn2_``. Both a library and a command.

Key components:
    - Pftag: the engine
    - TagOptions, TagResult: options in, result out
    - FunctionRegistry: the functions, extensible
    - __main__: the ``pftag`` command

Typical usage:
    from pftag import Pftag, TagOptions
    Pftag(TagOptions(lookups={"run": {"subject": "sub-01"}}))("%subject-%timestamp.log").result

Dependencies:
    - faker, for the dcmname function
"""

from __future__ import annotations

__version__: str = "2.0.0"

from pftag.functions import FunctionError, FunctionRegistry
from pftag.models import FunctionCall, TagOptions, TagResult, TagToken
from pftag.pftag import CORE_TAGS, Pftag, coreTag_value

__all__ = [
    "CORE_TAGS",
    "FunctionCall",
    "FunctionError",
    "FunctionRegistry",
    "Pftag",
    "TagOptions",
    "TagResult",
    "TagToken",
    "__version__",
    "coreTag_value",
]
