"""The ``pftag`` command line and its manual.

Key components:
    - parser_build: the arguments
    - synopsis: the manual text
    - main: the entry point, honouring an explicit ``argv``

Typical usage:
    pftag --tag "run-%{timestamp|replace(:,-)}-on-%{hostname}.log"
    pftag --lookupDictAdd '{"s": {"user": "chris"}}' --tag "%{user|md5(8)}"
    pftag --man

Dependencies:
    - pftag.pftag, pftag.models
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence

from pftag import __version__
from pftag.models import TagOptions, TagResult
from pftag.pftag import Pftag

BANNER: str = r"""
          __  _
         / _|| |
   _ __ | |_ | |_   __ _   __ _
  | '_ \|  _|| __| / _` | / _` |
  | |_) | |  | |_ | (_| || (_| |
  | .__/|_|   \__| \__,_| \__, |
  | |                      __/ |
  |_|                     |___/

                       string template processor

        Text with %{tags} in it, resolved when the text is used. A tag
        names a value and may pipe it through functions:

            %{inputWorkingFile|rmext}.jpg
            %{timestamp|replace(:,-)|md5(6)}

                             -- version {version} --
"""

CLI_SELF: str = """
        --tag <template>                                                        \\
        [--lookupDictAdd <json>]                                                \\
        [--strict]                                                              \\
        [--json]                                                                \\
        [--verbosity <level>]                                                   \\
        [--man] [--synopsis] [--version]"""

ARGS_SYNOPSIS: str = """
    ARGUMENTS

        --tag <template>
        The template to process: any text, with tags written %{...}.

        [--lookupDictAdd <json>]
        Named lookup dictionaries to add, as a JSON object

            '{"secrets": {"CUBEuser": "chris", "CUBEpassword": "chris1234"}}'

        or a list of such objects. Each adds a group of tags, here
        %{CUBEuser} and %{CUBEpassword}, that can be piped through functions
        like any tag. A tag name is an identifier: letters, digits and
        underscores, not starting with a digit. A name may be defined by one
        dictionary only, unless it is always written qualified: %{secrets.CUBEuser}.

        [--strict]
        An unknown tag, or a bare %name of a known name outside braces (a 1.x
        template), fails the run (exit 1) instead of being left as written.

        [--json]
        Print the whole result as JSON: the text, the tags found, the unknown
        and 1.x-style tags, the functions applied, any errors.

        [--verbosity <level>]
        0 (the default) prints only the result; 1 adds warnings about 1.x-style
        tags; higher levels log more.

        [--man] [--synopsis] [--version]
        The full manual, the brief one, the version.
"""

GRAMMAR: str = """
    GRAMMAR

        A tag is %{ followed by a head, optional functions, and }:

            %{name}
            %{name|function}
            %{name|function(arg, arg)|function}
            %{"literal text"|function}

        Nothing outside %{...} is a tag: printf "%s", date +%Y%m%d and %20 in
        a URL pass through untouched. Inside the braces % is ordinary, so
        %{timestamp|strftime(%Y%m%d)} works. \\%{ is a literal "%{".

        The head is a tag name, qualified with its dictionary's name when
        two dictionaries define it (%{secrets.user}), or a quoted string that
        starts a chain from literal text. Functions follow in pipe order,
        left to right, each receiving the previous result. Arguments are
        comma-separated inside parentheses, bare or quoted; a bare argument
        is trimmed and may not contain , ) | or }; inside quotes, \\" \\' and
        \\\\ escape. A function with no arguments may be written with or
        without ().

        Text after the closing } is kept: %{file|rmext}.txt keeps ".txt".
        An unknown name is left as written and reported (see --strict). A
        function that fails leaves its tag as written and fails the run.
        Values are substituted once; a value containing %{...} is not
        processed again.
"""

TAGS_AND_FUNCTIONS: str = """
    TAGS

        %{timestamp}  the current local time, ISO 8601 with offset
        %{date}       today's date, YYYY-MM-DD
        %{hostname}   the host name (in a container, the container id)
        %{platform}   platform.system(), such as Linux
        %{user}       the login name, or the numeric uid without a passwd entry
        %{pid}        the process id

        plus every tag in a registered lookup dictionary. %{core.timestamp}
        reaches a core tag that a dictionary has shadowed.

    FUNCTIONS

        rmext                   drop the last extension: brain.nii.gz -> brain.nii
        ext                     the last extension without its dot: gz
        basename                the last path component
        dirname                 the path without its last component
        replace(a, b)           replace every a with b, literally
        re(pattern, repl)       replace every regular-expression match
        upper, lower            change case
        strip[(chars)]          drop surrounding whitespace, or the given chars
        pad(width[, char])      left-pad with char (default 0): 7 -> 0007
        slice(stop) / slice(start, stop)
                                characters by index, Python style
        md5[(n)], sha256[(n)]   hex digest, cut to n characters
        strftime(format)        format an ISO 8601 timestamp: %{timestamp|strftime(%Y%m%d)}
        mask(pattern)           per position, * keeps the character, anything
                                else replaces it; positions past the pattern
                                are kept
        dcmname[(seed)]         a LAST^FIRST pseudonym, stable for a seed (the
                                value itself when no seed is given). Needs
                                pip install 'pftag[names]'. A seeded hash
                                wearing a name, not anonymization.

        Carrying protected text safely, hashed rather than written:

            %{"Subject12345"|sha256(8)}
"""

EXAMPLES: str = """
    EXAMPLES

        pftag --tag "run-%{timestamp}-on-%{hostname}.log"
        pftag --tag "run-%{timestamp|replace(:,-)}-on-%{hostname}.log"
        pftag --tag "run-%{timestamp|strftime(%Y%m%d-%H%M)}.log"
        pftag --lookupDictAdd '{"s": {"user": "chris"}}' --tag "user %{user}, hash %{user|md5(8)}"
        pftag --tag "100% done, %{date}"
        pftag --tag "%{nope}" --strict        # exit 1
"""

VERBOSITY_LOG_LEVELS: dict[int, int] = {0: logging.ERROR, 1: logging.WARNING, 2: logging.INFO}


def synopsis(shortOnly: bool = False) -> str:
    """The manual text.

    Args:
        shortOnly: NAME and SYNOPSIS only.

    Returns:
        The text, without the banner.
    """
    short: str = (
        """
    NAME

        pftag - resolve %{tags} in a template, with optional functions

    SYNOPSIS

        pftag \\"""
        + CLI_SELF
        + "\n"
    )
    if shortOnly:
        return short
    description: str = """
    DESCRIPTION

        pftag is both a command and a library for processing templates: text
        whose %{tags} are resolved when the text is used, each optionally
        piped through functions. The core tags describe the machine and the
        moment; a program adds its own tags as named lookup dictionaries.
        The pf* family uses it wherever a user writes a template on the
        command line, such as pfdo_run's --exec string and pflog's
        telemetry URLs. See docs/tags.adoc for the full reference.
"""
    return short + description + ARGS_SYNOPSIS + GRAMMAR + TAGS_AND_FUNCTIONS + EXAMPLES


def parser_build() -> argparse.ArgumentParser:
    """The command's parser.

    Returns:
        The parser; ``--help`` is the quick reference and points at ``--man``.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="pftag",
        description="Resolve %%{tags} in a template, optionally through piped functions. Manual: pftag --man",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--tag", dest="tag", default="", help="the template to process")
    parser.add_argument("--lookupDictAdd", dest="lookupDictAdd", default="", help="lookup dictionaries, JSON")
    parser.add_argument("--strict", dest="strict", action="store_true", help="unknown or 1.x-style tags fail")
    parser.add_argument("--json", dest="json", action="store_true", help="print the whole result as JSON")
    parser.add_argument("--verbosity", dest="verbosity", type=int, default=0, help="0 prints only the result")
    parser.add_argument("--man", dest="man", action="store_true", help="show the full manual and exit")
    parser.add_argument("--synopsis", dest="synopsis", action="store_true", help="show the brief manual")
    parser.add_argument("--version", action="version", version=f"pftag {__version__}")
    return parser


def options_fromArgs(args: argparse.Namespace) -> TagOptions:
    """Turn parsed arguments into options."""
    return TagOptions(strict=args.strict, tag=args.tag, json=args.json, verbosity=args.verbosity)


def manual_print(shortOnly: bool) -> None:
    """Print the banner and the manual."""
    print(BANNER.replace("{version}", __version__))
    print(synopsis(shortOnly))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command.

    Args:
        argv: arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        0 when the template was processed; 1 when ``--strict`` met an unknown or
        1.x-style tag, a tag did not parse, or a function failed; 2 on bad arguments.
    """
    parser: argparse.ArgumentParser = parser_build()
    args: argparse.Namespace = parser.parse_args(argv)
    if args.man or args.synopsis:
        manual_print(shortOnly=not args.man)
        return 0
    if not args.tag:
        parser.error("--tag is required")
    options: TagOptions = options_fromArgs(args)
    logging.basicConfig(
        level=VERBOSITY_LOG_LEVELS.get(options.verbosity, logging.DEBUG), format="%(message)s"
    )
    try:
        tagger: Pftag = Pftag(options)
        if args.lookupDictAdd:
            tagger.lookups_addFromJson(args.lookupDictAdd)
    except ValueError as err:
        parser.error(str(err))
    result: TagResult = tagger.process(options.tag)
    if options.json:
        print(json.dumps(result.toDict(), indent=4, sort_keys=True))
    else:
        print(result.result)
    for error in result.errors:
        print(error, file=sys.stderr)
    return 0 if result.status else 1


if __name__ == "__main__":
    sys.exit(main())
