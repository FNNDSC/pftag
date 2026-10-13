"""The ``pftag`` command line and its manual.

Key components:
    - parser_build: the arguments
    - synopsis: the manual text
    - main: the entry point, honouring an explicit ``argv``

Typical usage:
    pftag --tag "run-%timestamp_chrplc|:|-_-on-%platform.log"
    pftag --lookupDictAdd '{"secrets": {"user": "chris"}}' --tag "%user_md5|8_"
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
from pftag.pftag import CORE_TAGS, Pftag

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

        An in-place string token lookup and optional function processor.
        A template is text with %tags in it; each tag is resolved when the
        template is processed, and may be passed through functions.

                             -- version {version} --
"""

CLI_SELF: str = """
        --tag <template>                                                        \\
        [--lookupDictAdd <json>]                                                \\
        [--strict]                                                              \\
        [--json]                                                                \\
        [--tagMarker <char>] [--funcMarker <char>]                              \\
        [--funcArgMarker <char>] [--funcSep <char>]                             \\
        [--verbosity <level>]                                                   \\
        [--man] [--synopsis] [--version]"""

ARGS_SYNOPSIS: str = """
    ARGUMENTS

        --tag <template>
        The template to process. Any text; tags begin with the tag marker.

        [--lookupDictAdd <json>]
        Named lookup dictionaries to add, as JSON: either an object

            '{"secrets": {"CUBEuser": "chris", "CUBEpassword": "chris1234"}}'

        or a list of such objects. Each adds a group of tags, here %CUBEuser
        and %CUBEpassword, that substitute their values and can be passed
        through functions like any tag. A tag name may not contain a marker.

        [--strict]
        A tag whose name is not known fails the run (exit 1) instead of being
        left in the text as written.

        [--json]
        Print the whole result as JSON: the text, the tags found, the unknown
        tags, the functions applied, any errors.

        [--tagMarker <char>]        (default "%")
        [--funcMarker <char>]       (default "_")
        [--funcArgMarker <char>]    (default "|")
        [--funcSep <char>]          (default ",")
        The grammar's four characters. Each must be a single character and
        they must differ. A backslash before any of them makes it literal.

        [--verbosity <level>]
        0 (the default) prints only the result; higher levels log more.

        [--man] [--synopsis] [--version]
        The full manual, the brief one, the version.
"""

GRAMMAR: str = """
    GRAMMAR

        A tag is the tag marker followed by a name:

            %platform

        The name is matched longest first against every known name, so a
        tag may run straight into other text: %platform-report.txt. A name
        that is not known is left as written (see --strict).

        Functions follow the tag between two function markers, in Reverse
        Polish order: the tag, then what to do to it, left to right, each
        function's result feeding the next:

            %tag_func_
            %tag_func|arg1|arg2_
            %tag_func|arg1|arg2,func2|arg_

        Text after the closing marker is kept: %file_rmext_.txt replaces the
        tag and keeps ".txt". Inside an argument, a backslash keeps a marker
        literal: %literal_echo|a\\,b_ yields "a,b". The four characters can
        be changed, for instance

            --tagMarker "@" --funcMarker "[" --funcArgMarker "," --funcSep "|"

        so that the same template reads @tag[func,a1,a2|func2,b1[.
"""

TAGS_AND_FUNCTIONS: str = """
    TAGS

        %literal    the word "literal"; pair it with echo to inject text
        %os         os.name
        %platform   platform.system()
        %release    platform.release()
        %machine    platform.machine()
        %arch       platform.architecture(), joined with "-"
        %timestamp  the current local time, ISO 8601 with offset

        plus every tag in a registered lookup dictionary.

    FUNCTIONS

        echo|<text>             replace the value with <text>.
                                  %literal_echo|hello_
        md5[|<chars>]           the MD5 hex digest of the value, cut to
                                <chars> characters when given.
                                  %timestamp_md5|4_
        chrplc|<target>|<new>   replace <target> with <new>; <target> is
                                literal, or a regular expression when written
                                re:<pattern>.
                                  %timestamp_chrplc|:|-_
        strrepl|<target>|<new>  the same, under pfdo_run's name.
        strmsk|<mask>           for each position, "*" in the mask keeps the
                                value's character, anything else replaces it;
                                positions past the mask are kept.
                                  %platform_strmsk|l****_
        rmext                   drop the last extension: brain.nii.gz becomes
                                brain.nii.
        upper, lower            change case.
        dcmname[|<seed>[|<tail>]]
                                a DICOM-style LAST^FIRST name; the same <seed>
                                always gives the same name; <tail> is appended.
                                  %NAME_dcmname|foobar|^ANON_
        name                    the same as dcmname.

        Hashing a literal, the usual way to carry protected text safely:

            %literal_echo|Subject12345,md5|5_
"""

EXAMPLES: str = """
    EXAMPLES

        pftag --tag "run-%timestamp-on-%platform.log"
        pftag --tag "run-%timestamp_chrplc|:|-_-on-%platform.log"
        pftag --tag "run-%timestamp_chrplc|:|-,md5|6_-on-%platform.log"
        pftag --lookupDictAdd '{"s": {"user": "chris"}}' --tag "user %user hash %user_md5|8_"
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

        pftag - resolve %tags in a template, with optional functions

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
        whose %tags are resolved at run time, each optionally passed through
        a chain of functions. The core tags describe the machine and the
        moment; a caller adds its own tags as named lookup dictionaries. The
        pf* family uses it wherever a user writes a template on the command
        line, such as pfdo_run's --exec string and pflog's telemetry URLs.
"""
    return short + description + ARGS_SYNOPSIS + GRAMMAR + TAGS_AND_FUNCTIONS + EXAMPLES


def parser_build() -> argparse.ArgumentParser:
    """The command's parser.

    Returns:
        The parser; ``--help`` is the quick reference and points at ``--man``.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="pftag",
        description="Resolve %tags in a template, optionally through chained functions. Manual: pftag --man",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--tag", dest="tag", default="", help="the template to process")
    parser.add_argument(
        "--lookupDictAdd", dest="lookupDictAdd", default="", help="named lookup dictionaries, JSON"
    )
    parser.add_argument("--strict", dest="strict", action="store_true", help="an unknown tag fails the run")
    parser.add_argument("--json", dest="json", action="store_true", help="print the whole result as JSON")
    parser.add_argument("--tagMarker", dest="tagMarker", default="%", help="the tag marker (default %%)")
    parser.add_argument(
        "--funcMarker", dest="funcMarker", default="_", help="opens and closes functions (default _)"
    )
    parser.add_argument(
        "--funcArgMarker", dest="funcArgMarker", default="|", help="separates arguments (default |)"
    )
    parser.add_argument(
        "--funcSep", dest="funcSep", default=",", help="separates chained functions (default ,)"
    )
    parser.add_argument("--verbosity", dest="verbosity", type=int, default=0, help="0 prints only the result")
    parser.add_argument("--man", dest="man", action="store_true", help="show the full manual and exit")
    parser.add_argument(
        "--synopsis", dest="synopsis", action="store_true", help="show the brief manual and exit"
    )
    parser.add_argument("--version", action="version", version=f"pftag {__version__}")
    return parser


def options_fromArgs(args: argparse.Namespace) -> TagOptions:
    """Turn parsed arguments into options.

    Args:
        args: the parser's Namespace.

    Returns:
        TagOptions with the markers, strictness, template and output flags.
    """
    return TagOptions(
        tagMarker=args.tagMarker,
        funcMarker=args.funcMarker,
        funcArgMarker=args.funcArgMarker,
        funcSep=args.funcSep,
        strict=args.strict,
        tag=args.tag,
        json=args.json,
        verbosity=args.verbosity,
    )


def manual_print(shortOnly: bool) -> None:
    """Print the banner and the manual."""
    print(BANNER.format(version=__version__))
    print(synopsis(shortOnly))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command.

    Args:
        argv: arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        0 when the template was processed; 1 when ``--strict`` met an unknown tag
        or a function failed; 2 on bad arguments.
    """
    parser: argparse.ArgumentParser = parser_build()
    args: argparse.Namespace = parser.parse_args(argv)
    if args.man or args.synopsis:
        manual_print(shortOnly=not args.man)
        return 0
    if not args.tag:
        parser.error("--tag is required")
    try:
        options: TagOptions = options_fromArgs(args)
        tagger: Pftag = Pftag(options)
        if args.lookupDictAdd:
            tagger.lookups_addFromJson(args.lookupDictAdd)
    except ValueError as err:
        parser.error(str(err))
    logging.basicConfig(
        level=VERBOSITY_LOG_LEVELS.get(options.verbosity, logging.DEBUG), format="%(message)s"
    )
    result: TagResult = tagger.tag_process(options.tag)
    if options.json:
        print(json.dumps(result.toDict(), indent=4, sort_keys=True))
    else:
        print(result.result)
    for error in result.errors:
        print(error, file=sys.stderr)
    return 0 if result.status else 1


def coreTags_list() -> list[str]:
    """The core tag names, for callers that document them."""
    return list(CORE_TAGS)


if __name__ == "__main__":
    sys.exit(main())
