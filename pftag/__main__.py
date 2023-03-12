#!/usr/bin/env python
try:
    from    .                   import pftag
except:
    from pftag                  import pftag

from    pathlib                 import Path
from    argparse                import ArgumentParser,                  \
                                       Namespace,                       \
                                       ArgumentDefaultsHelpFormatter,   \
                                       RawTextHelpFormatter

from importlib.metadata import Distribution

__pkg       = Distribution.from_name(__package__)
__version__ = __pkg.version

import  os, sys, json
import  pudb
from    pudb.remote             import set_trace
from    pftag.pftag             import parser_setup, parser_interpret, parser_JSONinterpret


DISPLAY_TITLE = r"""

        __ _
       / _| |
 _ __ | |_| |_ __ _  __ _
| '_ \|  _| __/ _` |/ _` |
| |_) | | | || (_| | (_| |
| .__/|_|  \__\__,_|\__, |
| |                  __/ |
|_|                 |___/

"""

str_desc: str                =  DISPLAY_TITLE + """

                        -- version """ + __version__ + """ --

        An in-place string token lookup and optional function processor. This
        package provides both a CLI client as well as a python module.


"""

package_CLIself:str         = """
        --tag <tagString>                                                       \\
        [--tagMarker <mark>]                                                    \\
        [--funcMarker <mark>]                                                   \\
        [--funcArgMarker <mark>]                                                \\
        [--funcSep <mark>]                                                      \\
        [--inputdir <inputdir>]                                                 \\
        [--outputdir <outputdir>]                                               \\
        [--man]                                                                 \\
        [--verbosity <level>]                                                   \\
        [--debug]                                                               \\
        [--debugTermsize <cols,rows>]                                           \\
        [--debugHost <0.0.0.0>]                                                 \\
        [--debugPort <7900>]"""

package_CLIsynpsisArgs:str  = """
    ARGUMENTS

        --tag <tagString>
        The tag string to process.

        [--tagMarker <mark>]
        The marker string that identifies a tag (default "%")

        [--funcMarker <mark>]
        The marker string that pre- and post marks a function (default "_").

        [--funcArgMarker <mark>]
        The marker string between function arguments and also between arg list
        and function (default "|").

        [--funcSep <mark>]
        The marker string separating successive function/argument constructs
        (default ",").

        [--pftelUser <user>] ("chris")
        The name of the pftel user. Reserved for future use.

        [--inputdir <inputdir>]
        An optional input directory specifier. Reserverd for future use.

        [--outputdir <outputdir>]
        An optional output directory specifier. Reserved for future use.

        [--man]
        If specified, show this help page and quit.

        [--verbosity <level>]
        Set the verbosity level. The app is currently chatty at level 0 and level 1
        provides even more information.

        [--debug]
        If specified, toggle internal debugging. This will break at any breakpoints
        specified with 'Env.set_trace()'

        [--debugTermsize <253,62>]
        Debugging is via telnet session. This specifies the <cols>,<rows> size of
        the terminal.

        [--debugHost <0.0.0.0>]
        Debugging is via telnet session. This specifies the host to which to connect.

        [--debugPort <7900>]
        Debugging is via telnet session. This specifies the port on which the telnet
        session is listening.
"""

package_CLIfunctions:str = r"""

    FUNCTIONS

        OVERVIEW
        In addition to performing a lookup on a template string token, this
        package can also process the lookup value in various ways. These
        process functions follow a Reverse Polish Notation (RPN) schema of

            tag func1 func2 func3 ...

        where first the <tag> is looked up, then this lookup is processed by
        <func1>. The result is then processed by <func2>, and so on and
        so forth.

        This RPN approach also mirrors the standard UNIX piping schema.

        A function that is to be applied to a <tag> should be connected
        to the tag with a <funcMarker> string, usually '_'. The final
        function should end with the same <funcMarker>, so

            %tag_func_

        will apply the function called "func" to the tag called "tag".

        Some functions can accept arguments. Arguments are passed to a function
        with a <funcArgMarker> string, typically '|', that also separates
        arguments:

            %tag_func|a1|a2|a3_

        will pass 'a1', 'a2', and 'a3' as parameters to "func".

        Finally, several functions can be chained within the '_'...'_' by
        separating the <func>|<argList> constructs with commas, so

            %tag_func|a1|a2|a3,func2|b1|b2|b3_

        All these special characters (tag marker, function pre- and post,
        arg separation, fand unction separation can be overriden. For instance,
        with a selection of

        --tagMarker "@" --funcMarker "[" --funcArgMarker "," --funcSep "|"

        strings can be specified as

            @tag[func,a1,a2,a3|func2,b1,b2,b3[

        where preference/legibilty is left to the user
"""


package_CLItagsFuncs:str = r"""

        AVAILABLE TAGS AND FUNCTIONS

        The following tags are available:

            %literal   : simply replace the tag with the word 'literal'.
                          This tag is only useful in conjunction with the
                          'echo' function and together they provide a means
                          to inject arbitary text typically for md5 hashing.
            %name      : return the os.name
            %platform  : return the platform.system()
            %release   : return the platform.release()
            %machine   : return the platform.machine()
            %arch      : return the '%s' % platform.architecture()
            %timestamp :  return the a timestamp

        The following tags are available:

        md5|<chars>         : perform an md5hash on the upstream, limit result
                              to <chars> characters

                                eg: "%timestamp_md5|4_"

                              replace the %timestamp in the input string with
                              an md5 hash of 4 chars of the actual timestamp.

        chrplc|<t>|<n>      : replace <t> with <n> in the upstream input.

                                eg: "%timestamp_chrplc|:|-_"

                              replace the %timestamp in the input string with
                              the actual timestamp where all ":" are replaced with
                              "-".

        strmsk|<mask>       : for each '*' in mask pattern use upstream char
                              otherwise replace with <mask> char.

                                eg: "%platform_strmsk|l****_"

                              replace the %platform in the input string with
                              a string that starts with an 'l' and don't change
                              the subsequent 4 characters. If the %platform
                              has more than 4 characters, only return the 5
                              chars as masked.

        dcmname|<s>|<tail> : replace any upstream %VAR with a DICOM formatted
                              name. If <s> is passed, the seed the faker module
                              with <s> (any string) -- this guarantees that calls
                              with that same <s> result in the same name. If
                              <tail> is passed, then append <tail> to the name.

                                eg: %NAME_dcmname_

                             may produce "BROOKS^JOHN". Each call will have
                             a different name. However,

                                %NAME_dcmname|foobar_

                            will always generate "SCHWARTZ^THOMAS". While

                                %NAME_dcmname|foobar|^ANON

                            will generate "SCHWARTZ^THOMAS^ANON"

        echo|<something> :  Best used with the %literal tag for legibility, will
                            replace the tag with <something>. Be careful of commas
                            in the <something>. If they are to be preserved you
                            will need to set --funcSep to something other than a
                            comma.

                                %literal_echo|why-are-we-here?_

                            will replace the %literal with "why-are-we-here".
                            This is most useful when literal data is to obscured
                            in a template. For instance:

                                %literal_echo|Subject12345,md5|5_

                            where say "Subject12345" is privileged information but
                            important to add to the string. In this case, we can
                            add and then hash that literal string. In future,
                            if we know all the privileged strings, we can easily
                            hash and then and lookup in any `pftag` generated
                            strings to resolve which hashes belong to which
                            subjects.

"""

package_CLIexample:str = r"""
    BRIEF EXAMPLES
    Note that some shells (like fish) might require quoting about the tag argument.

        pftag --tag "run-%timestamp-on-%platform.log"
        pftag --tag "run-%timestamp_chrplc|:|-_-on-%platform.log"
        pftag --tag "run-%timestamp_chrplc|:|-,md5|6_-on-%platform.log"

"""

def synopsis(ab_shortOnly = False):
    scriptName = os.path.basename(sys.argv[0])
    shortSynopsis =  '''
    NAME

        pftag

    SYNOPSIS

        pftag                                                               \ '''\
        + package_CLIself + '''

    '''

    description = '''
    DESCRIPTION

        `pftag` is both a script and python module for processing "tag"ed
        strings with optional functions. It is useful when using templated
        strings that need to be processed at "runtime".

    ''' + package_CLIsynpsisArgs + package_CLIfunctions + package_CLItagsFuncs + package_CLIexample
    if ab_shortOnly:
        return shortSynopsis
    else:
        return shortSynopsis + description

# parser: ArgumentParser = ArgumentParser(description         = '''A client for pftag''',
#                                         formatter_class     = RawTextHelpFormatter
# )

def earlyExit_check(args) -> int:
    """
    Perform some preliminary checks

    If version or synospis are requested, print these and return
    code for early exit.
    """
    str_help:str = ''
    if args.man or args.synopsis:
        print(str_desc)
        if args.man:
            str_help     = synopsis(False)
        else:
            str_help     = synopsis(True)
        print(str_help)
        return 1
    if args.b_version:
        print("Name:    %s\nVersion: %s" % (__pkg.name, __version__))
        return 1
    if int(args.verbosity) > 1: print(DISPLAY_TITLE)
    return 0

def main(argv=None) -> int:
    """
    Main method for the programmatical calling the pftag
    module
    """

    # Call the following to collect the logger Namespace
    # and then edit values in the options:Namespace if needed
    parser:ArgumentParser   = parser_setup('A client for logging to a pftel server')
    options:Namespace       = parser_interpret(parser, argv)

    # any reason we should not continue?
    if earlyExit_check(options): return 1

    # set_trace(term_size=(253, 62), host = '0.0.0.0', port = 7900)
    tag:pftag.Pftag         = pftag.Pftag(options)
    d_pftag:dict            = tag.run(options.tag)
    print(d_pftag['result'])

    return 0 if d_pftag['status'] else 2

if __name__ == '__main__':
    sys.exit(main(sys.argv))
