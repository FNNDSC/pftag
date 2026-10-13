"""The functions a tag's value can be passed through.

A function takes the value so far and the arguments written after it in the
template, and returns new text. They chain left to right, so
``%timestamp_chrplc|:|-,md5|6_`` replaces the colons in the timestamp and then
hashes the result to six characters. The registry maps names to functions and is
extensible: a package built on pftag registers its own.

Key components:
    - TagFunction: the signature every function has
    - FunctionRegistry: name to function, with the built-ins preloaded
    - the built-ins: echo, md5, strmsk, chrplc, strrepl, rmext, upper, lower,
      dcmname

Typical usage:
    registry = FunctionRegistry()
    registry.add("shout", lambda value, args: value.upper() + "!")

Dependencies:
    - faker, for dcmname
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import PurePosixPath

from faker import Faker

TagFunction = Callable[[str, list[str]], str]

REGEX_PREFIX: str = "re:"
MASK_KEEP: str = "*"
DICOM_NAME_SEPARATOR: str = "^"


class FunctionError(ValueError):
    """A function was given arguments it cannot work with."""


def args_require(name: str, args: list[str], atLeast: int) -> None:
    """Fail clearly when a function is missing arguments.

    Args:
        name: the function, for the message.
        args: the arguments given.
        atLeast: how many are needed.

    Raises:
        FunctionError: when too few were given.
    """
    if len(args) < atLeast:
        raise FunctionError(f"{name} needs {atLeast} argument(s), got {len(args)}: {args}")


def echo(value: str, args: list[str]) -> str:
    """Replace the value with the first argument.

    Useful with ``%literal`` to inject text into a template, often to hash it:
    ``%literal_echo|Subject12345,md5|5_``.
    """
    args_require("echo", args, 1)
    return args[0]


def md5(value: str, args: list[str]) -> str:
    """The MD5 hex digest of the value, cut to the first argument's length when given."""
    digest: str = hashlib.md5(value.encode("utf-8")).hexdigest()  # a tag, not a secret
    if args:
        try:
            return digest[: int(args[0])]
        except ValueError as err:
            raise FunctionError(f"md5 length must be an integer, not {args[0]!r}") from err
    return digest


def strmsk(value: str, args: list[str]) -> str:
    """Mask the value character by character.

    For each position of the mask, ``*`` keeps the value's character and any other
    character replaces it. Positions past the end of the mask are kept; the result is
    never shorter than the value, which is where 1.x differed.
    """
    args_require("strmsk", args, 1)
    mask: str = args[0]
    out: list[str] = []
    for index, char in enumerate(value):
        if index < len(mask) and mask[index] != MASK_KEEP:
            out.append(mask[index])
        else:
            out.append(char)
    return "".join(out)


def chrplc(value: str, args: list[str]) -> str:
    """Replace one text with another in the value.

    The target is taken literally; written as ``re:<pattern>`` it is a regular
    expression. 1.x treated every target as a regular expression, so a ``.`` meant
    any character.
    """
    args_require("chrplc", args, 2)
    target, replacement = args[0], args[1]
    if target.startswith(REGEX_PREFIX):
        return re.sub(target[len(REGEX_PREFIX) :], replacement, value)
    return value.replace(target, replacement)


def strrepl(value: str, args: list[str]) -> str:
    """Replace one text with another in the value; pfdo_run's name for ``chrplc``."""
    return chrplc(value, args)


def rmext(value: str, args: list[str]) -> str:
    """Drop the value's last extension: ``brain.nii.gz`` becomes ``brain.nii``."""
    path: PurePosixPath = PurePosixPath(value)
    if path.suffix:
        return value[: -len(path.suffix)]
    return value


def upper(value: str, args: list[str]) -> str:
    """The value in upper case."""
    return value.upper()


def lower(value: str, args: list[str]) -> str:
    """The value in lower case."""
    return value.lower()


def dcmname(value: str, args: list[str]) -> str:
    """A DICOM-style ``LAST^FIRST`` name in place of the value.

    With a first argument, the name is seeded by it, so the same seed always gives
    the same name; a second argument is appended, as in ``%NAME_dcmname|s|^ANON_``.
    """
    faker: Faker = Faker()
    if args:
        faker.seed_instance(args[0])
    name: str = f"{faker.last_name().upper()}{DICOM_NAME_SEPARATOR}{faker.first_name().upper()}"
    if len(args) > 1:
        name += args[1]
    return name


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
            "echo": echo,
            "md5": md5,
            "strmsk": strmsk,
            "chrplc": chrplc,
            "strrepl": strrepl,
            "rmext": rmext,
            "upper": upper,
            "lower": lower,
            "dcmname": dcmname,
            "name": dcmname,
        }

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
            raise FunctionError(f"unknown function {name!r}; known: {', '.join(self.names())}")
        return self.functions[name](value, args)
