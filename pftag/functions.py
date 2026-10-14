"""The functions a tag's value can be piped through.

A function takes the value so far and the arguments written in the template, and
returns new text. Functions chain left to right: ``%{timestamp|replace(:,-)|md5(6)}``
replaces the colons in the timestamp and hashes the result to six characters. The
registry maps names to functions and is extensible; the pseudonym generator lives in
``pftag.names`` and is registered only when its dependency is installed.

Key components:
    - TagFunction: the signature every function has
    - FunctionRegistry: name to function, with the built-ins preloaded
    - the built-ins: path parts, replacement, case, padding, slicing, hashing,
      masking, time formatting

Typical usage:
    registry = FunctionRegistry()
    registry.add("shout", lambda value, args: value.upper() + "!")

Dependencies:
    - standard library only
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import PurePosixPath

TagFunction = Callable[[str, list[str]], str]

MASK_KEEP: str = "*"


class FunctionError(ValueError):
    """A function was given arguments it cannot work with, or does not exist."""


def args_count(name: str, args: list[str], atLeast: int, atMost: int | None = None) -> None:
    """Fail clearly on a wrong number of arguments.

    Args:
        name: the function, for the message.
        args: the arguments given.
        atLeast: the minimum.
        atMost: the maximum; None for no limit.

    Raises:
        FunctionError: when the count is outside the range.
    """
    if len(args) < atLeast or (atMost is not None and len(args) > atMost):
        expected: str = str(atLeast) if atMost == atLeast else f"{atLeast} to {atMost or 'any'}"
        raise FunctionError(f"{name} takes {expected} argument(s), got {len(args)}: {args}")


def int_arg(name: str, text: str) -> int:
    """An integer argument, or a clear failure."""
    try:
        return int(text)
    except ValueError as err:
        raise FunctionError(f"{name}: {text!r} is not an integer") from err


def rmext(value: str, args: list[str]) -> str:
    """Drop the last extension: ``brain.nii.gz`` becomes ``brain.nii``."""
    args_count("rmext", args, 0, 0)
    suffix: str = PurePosixPath(value).suffix
    return value[: -len(suffix)] if suffix else value


def ext(value: str, args: list[str]) -> str:
    """The last extension without its dot: ``brain.nii.gz`` gives ``gz``."""
    args_count("ext", args, 0, 0)
    return PurePosixPath(value).suffix.lstrip(".")


def basename(value: str, args: list[str]) -> str:
    """The last path component."""
    args_count("basename", args, 0, 0)
    return PurePosixPath(value).name


def dirname(value: str, args: list[str]) -> str:
    """The path without its last component."""
    args_count("dirname", args, 0, 0)
    return str(PurePosixPath(value).parent)


def replace(value: str, args: list[str]) -> str:
    """Replace every occurrence of the first argument with the second, literally."""
    args_count("replace", args, 2, 2)
    return value.replace(args[0], args[1])


def re_sub(value: str, args: list[str]) -> str:
    """Replace every match of a regular expression with the second argument."""
    args_count("re", args, 2, 2)
    try:
        return re.sub(args[0], args[1], value)
    except re.error as err:
        raise FunctionError(f"re: bad pattern {args[0]!r}: {err}") from err


def upper(value: str, args: list[str]) -> str:
    """Upper case."""
    args_count("upper", args, 0, 0)
    return value.upper()


def lower(value: str, args: list[str]) -> str:
    """Lower case."""
    args_count("lower", args, 0, 0)
    return value.lower()


def strip(value: str, args: list[str]) -> str:
    """Drop leading and trailing whitespace, or the characters in the argument."""
    args_count("strip", args, 0, 1)
    return value.strip(args[0]) if args else value.strip()


def pad(value: str, args: list[str]) -> str:
    """Left-pad to a width with a character (default ``0``): ``pad(4)`` turns ``7`` into ``0007``."""
    args_count("pad", args, 1, 2)
    width: int = int_arg("pad", args[0])
    fill: str = args[1] if len(args) > 1 else "0"
    if len(fill) != 1:
        raise FunctionError(f"pad: fill must be one character, not {fill!r}")
    return value.rjust(width, fill)


def slice_(value: str, args: list[str]) -> str:
    """Characters from the first index up to the second, Python style; one argument means a prefix."""
    args_count("slice", args, 1, 2)
    if len(args) == 1:
        return value[: int_arg("slice", args[0])]
    return value[int_arg("slice", args[0]) : int_arg("slice", args[1])]


def md5(value: str, args: list[str]) -> str:
    """The MD5 hex digest, cut to the first argument's length when given."""
    args_count("md5", args, 0, 1)
    digest: str = hashlib.md5(value.encode("utf-8")).hexdigest()  # a tag, not a secret
    return digest[: int_arg("md5", args[0])] if args else digest


def sha256(value: str, args: list[str]) -> str:
    """The SHA-256 hex digest, cut to the first argument's length when given."""
    args_count("sha256", args, 0, 1)
    digest: str = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[: int_arg("sha256", args[0])] if args else digest


def strftime(value: str, args: list[str]) -> str:
    """Format an ISO 8601 timestamp with a ``strftime`` pattern: ``strftime(%Y%m%d)``."""
    args_count("strftime", args, 1, 1)
    try:
        moment: datetime = datetime.fromisoformat(value)
    except ValueError as err:
        raise FunctionError(f"strftime: {value!r} is not an ISO 8601 timestamp") from err
    return moment.strftime(args[0])


def mask(value: str, args: list[str]) -> str:
    """Mask character by character.

    For each position of the pattern, ``*`` keeps the value's character and any other
    character replaces it; positions past the pattern are kept, so the result is never
    shorter than the value.
    """
    args_count("mask", args, 1, 1)
    pattern: str = args[0]
    out: list[str] = []
    for index, char in enumerate(value):
        if index < len(pattern) and pattern[index] != MASK_KEEP:
            out.append(pattern[index])
        else:
            out.append(char)
    return "".join(out)


class FunctionRegistry:
    """Name to function, with the built-ins preloaded.

    Attributes:
        functions: the registered functions by name.

    Example:
        >>> FunctionRegistry().apply("upper", "abc", [])
        'ABC'
    """

    def __init__(self) -> None:
        self.functions: dict[str, TagFunction] = {
            "rmext": rmext,
            "ext": ext,
            "basename": basename,
            "dirname": dirname,
            "replace": replace,
            "re": re_sub,
            "upper": upper,
            "lower": lower,
            "strip": strip,
            "pad": pad,
            "slice": slice_,
            "md5": md5,
            "sha256": sha256,
            "strftime": strftime,
            "mask": mask,
        }
        self.names_register()

    def names_register(self) -> None:
        """Register the pseudonym functions when their dependency is installed."""
        try:
            from pftag.names import dcmname
        except ImportError:
            return
        self.functions["dcmname"] = dcmname

    def add(self, name: str, function: TagFunction) -> None:
        """Register a function, replacing any of the same name.

        Args:
            name: the name used in templates.
            function: ``(value, args) -> str``.
        """
        self.functions[name] = function

    def has(self, name: str) -> bool:
        """Whether a function is registered."""
        return name in self.functions

    def names(self) -> list[str]:
        """The registered names, sorted."""
        return sorted(self.functions)

    def apply(self, name: str, value: str, args: list[str]) -> str:
        """Run a function.

        Args:
            name: a registered name.
            value: the text so far.
            args: the arguments written in the template.

        Returns:
            The function's result.

        Raises:
            FunctionError: if the name is unknown or the arguments are unusable.
        """
        if name not in self.functions:
            if name == "dcmname":
                raise FunctionError("dcmname needs the names extra: pip install 'pftag[names]'")
            raise FunctionError(f"unknown function {name!r}; known: {', '.join(self.names())}")
        return self.functions[name](value, args)
