#!/usr/bin/env python
__version__ = '1.2.4'

from    pathlib                 import Path

import  os, sys, json, platform, re
import  pudb
from    pudb.remote             import set_trace

from    concurrent.futures      import ThreadPoolExecutor
from    threading               import current_thread

from    datetime                import datetime, timezone

from    typing                  import Any, Callable, Tuple
from    faker                   import  Faker

import  logging
import  hashlib

import  math
from    argparse                import  Namespace, ArgumentParser
from    argparse                import  RawTextHelpFormatter

from    .                       import  data

# Turn off logging for the 'faker' module and create a class instance
# of the object
fakelogger: logging.Logger  = logging.getLogger('faker')
fakelogger.propagate        = False
fake:Faker                  = Faker()


def parser_setup(str_desc) -> ArgumentParser:
    parser:ArgumentParser = ArgumentParser(
                description         = str_desc,
                formatter_class     = RawTextHelpFormatter
            )

    parser.add_argument(
                '--version',
                default = False,
                dest    = 'b_version',
                action  = 'store_true',
                help    = 'print version info'
    )
    parser.add_argument(
                '--man',
                default = False,
                action  = 'store_true',
                help    = 'show a man page'
    )
    parser.add_argument(
                '--osenv',
                default = False,
                action  = 'store_true',
                help    = 'show the base os environment'
    )
    parser.add_argument(
                '--synopsis',
                default = False,
                action  = 'store_true',
                help    = 'show a synopsis'
    )
    parser.add_argument(
                '--inputdir',
                default = './',
                help    = 'optional directory specifying extra input-relative data'
    )
    parser.add_argument(
                '--outputdir',
                default = './',
                help    = 'optional directory specifying location of any output data'
    )
    parser.add_argument(
                '--tag',
                default = '',
                help    = 'tag string to process'
    )
    parser.add_argument(
                '--tagMarker',
                default = '%',
                help    = 'the marker string that identifies a tag (default "%")'
    )
    parser.add_argument(
                '--funcMarker',
                default = '_',
                help    = 'the marker string that pre- and post marks a function (default "_")'
    )
    parser.add_argument(
                '--funcArgMarker',
                default = '|',
                help    = 'the marker string between function arguments and also between arg list and function (default "|")'
    )
    parser.add_argument(
                '--funcSep',
                default = ',',
                help    = 'the separation string between successive function/argument constructs (default ",")'
    )
    parser.add_argument(
                '--verbosity',
                default = '0',
                help    = 'verbosity level of app'
    )
    parser.add_argument(
                "--debug",
                help    = "if true, toggle telnet pudb debugging",
                dest    = 'debug',
                action  = 'store_true',
                default = False
    )
    parser.add_argument(
                "--debugTermSize",
                help    = "the terminal 'cols,rows' size for debugging",
                default = '253,62'
    )
    parser.add_argument(
                "--debugPort",
                help    = "the debugging telnet port",
                default = '7900'
    )
    parser.add_argument(
                "--debugHost",
                help    = "the debugging telnet host",
                default = '0.0.0.0'
    )
    return parser

def parser_interpret(parser, *args):
    """
    Interpret the list space of *args, or sys.argv[1:] if
    *args is empty
    """
    if len(args):
        args    = parser.parse_args(args[0])
    else:
        args    = parser.parse_args(sys.argv[1:])
    return args

def parser_JSONinterpret(parser, d_JSONargs):
    """
    Interpret a JSON dictionary in lieu of CLI.
    For each <key>:<value> in the d_JSONargs, append to
    list two strings ["--<key>", "<value>"] and then
    argparse.
    """
    l_args  = []
    for k, v in d_JSONargs.items():
        if type(v) == type(True):
            if v: l_args.append('--%s' % k)
            continue
        l_args.append('--%s' % k)
        l_args.append('%s' % v)
    return parser_interpret(parser, l_args)

class Pftag:

    def env_setup(self, options: Namespace) -> bool:
        """
        Setup the environment

        Args:
            options (Namespace):    options passed from the CLI caller
        """
        status  : bool          = True
        options.inputdir        = Path(options.inputdir)
        options.outputdir       = Path(options.outputdir)
        self.env.inputdir       = options.inputdir
        self.env.outputdir      = options.outputdir
        self.env.debug_setup(
                    debug       = options.debug,
                    termsize    = options.debugTermSize,
                    port        = options.debugPort,
                    host        = options.debugHost
        )
        # if not len(options.tag):
        #     self.env.ERROR("The '--tag <tag>' CLI MUST be specified!")
        #     status              = False
        return status

    def __init__(self, options, *args, **kwargs):
        """
        constructor

        Responsible primarily for setting up the client connection
        to the pftel server.

        Possible TODO? How to check _elegantly_ on dead server?
        """
        global Env
        self.env:data.env                   = data.env()

        self.d_tagReserved:dict[str, list[str]]                  = {
            'core'      : ['literal',
                           'os',
                           'platform',
                           'release',
                           'machine',
                           'arch',
                           'timestamp']
        }

        # If the <options> is a dictionary, then we interpret this as if
        # it were the CLI (instead of the real CLI) and convert to a
        # namespace
        if type(options) is dict:
            parser:ArgumentParser           = parser_setup('Setup client using dict')
            options:Namespace               = parser_JSONinterpret(parser, options)
        if type(options) is Namespace:
            self.options:Namespace          = options
            self.env.options                = options
            self.envOK:bool                 = True
        if not self.env_setup(options):
            self.env.ERROR("Env setup failure, exiting...")
            self.envOK                  = False
        self.str_tagMarker:str              = options.tagMarker     # '%
        self.str_funcMarker:str             = options.funcMarker    # '_'
        self.str_funcArgSep:str             = options.funcArgMarker # '|'
        self.str_funcSep:str                = options.funcSep       # ','

        self.env_show()

    def env_show(self) -> None:
        """
        Perform some setup

        Args:
            None (internal self)

        Returns:
            None
        """

        if int(self.options.verbosity) < 4: return

        self.self.env.DEBUG("app arguments...", level = 3)
        for k,v in self.options.__dict__.items():
             self.self.env.DEBUG("%25s:  [%s]" % (k, v), level = 3)
        self.self.env.DEBUG("", level = 3)

        if self.options.osenv:
            self.self.env.DEBUG("base environment...")
            for k,v in os.environ.items():
                self.self.env.DEBUG("%25s:  [%s]" % (k, v), level = 3)
            self.self.env.DEBUG("")

    def tag_findDict(self, tag:str) -> list[Tuple]:
        """
        For a given <tag> superstring, determine if any reserved dictionaries
        contain a token within the <tag>. If found, add the dictionary name and
        token to a tuple list, and eventually return a list of tuples of
        (<dict>, <tag>) containing hits.

        For example, imagine that the string to analyze is

                %platform-name-os

        where the %platform is a tag to be substituted. Imagine further that
        'name' and 'os' are valid tags, but note that they do not have the
        leading tag marker, '%', and so should be literals (i.e. unprocessed).

        Give an tag superstring of 'platform-name-os' this method will
        correctly determine that 'platform' is the tag to analyze and also
        return the internal dictionary name containing this tag.

        Args:
            tag (str): the "tag" to search

        Returns:
            list[Tuple]: a list of tuples with the housing dictionary
            and tag within that dictionary
        """
        T:str                   = self.str_tagMarker
        l_tagPossibilities:list = []    # Is the tag in one of the possible dictionaries?
        l_tagHit:list           = []    # Which tag, *exactly*, is sought in the possibilities?
        tagHit:str              = ''    # This is it!
        l_tagDict:list          = []    # A list of tuples of (<dict>, <tag>)
        for d in list(self.d_tagReserved.keys()):
            l_tagPossibilities:list     = [i for i in self.d_tagReserved[d] if i in tag]
            l_tagHit:list               = [i for i in l_tagPossibilities if f'{T}'+i in f'{T}'+tag]
            tagHit:str                  = l_tagHit[0] if len(l_tagHit) else ''
            if tagHit:                  l_tagDict.append( (d, tagHit) )
        return l_tagDict

    def tag_lookupCore(self, tag:str) -> str:
        """Lookup a tag in the "core" dictionary.

        Args:
            tag (str): the tag to lookup

        Returns:
            str: the string lookup
        """
        timenow:Callable[[], str]       = lambda: datetime.now(timezone.utc).astimezone().isoformat()
        lookup:str  = ""
        tag:str     = tag.lower()
        if 'literal'        in tag: lookup  = 'literal'
        if 'os'             in tag: lookup  = os.name
        if 'platform'       in tag: lookup  = platform.system()
        if 'release'        in tag: lookup  = platform.release()
        if 'machine'        in tag: lookup  = platform.machine()
        if 'arch'           in tag: lookup  = '%s-%s' % platform.architecture()
        if 'timestamp'      in tag: lookup  = timenow()
        return lookup

    def tag_lookup(self, tagTuple:tuple) -> str:
        """
        Main dispatching method for looking up a tag across a variety of
        possible use cases (<dictionaryName>).

        Args:
            tagTuple (tuple): a tuple of <dictionaryName> and <tag> to lookup

        Returns:
            str: the lookup value for the <tag>
        """
        lookup:str  = ""
        match tagTuple[0]:
            case 'core':
                lookup  = self.tag_lookupCore(tagTuple[1])
        return lookup

    def tag_process(self, astr:str, *args, **kwargs):
        """
        This method processes a string that contains "%<tag>" tokens in a
        variety of ways. Various %<tags> are understood, for example:

            * %timestamp     - a timestamp
            * %os            - the OS name
            * %platform      - the platform system
            * %release       - the platform release

        For example, an input tag that is specified as the following string:

                    %os-%platform-output.txt

        will be parsed to

                    posix-Linux-6.2.2-zen1-1-zen-output.txt

        It is also possible to apply certain permutations/functions
        to a tag. For example, a function is specified as

                %<tag>_<funcName>|<arg1>|<arg2>...

        which will apply the <funcName> (with <arg1>, <arg2>) to the
        lookup value of <tag>
        """

        def echo(funcArgs:str, strproc:str) -> str:
            """
            Simply replace the tag with an "echo" passed
            in args.

            This is useful to inject a client side string
            into the superstring payload

            Args:
                funcArgs (str): the function_and_args construct
                strproc (str): the string to process

            Returns:
                str: the processed string
            """
            F:str               = self.str_funcMarker
            A:str               = self.str_funcArgSep
            l_args:list[str]    = funcArgs.split(f'{A}')
            value:str           = strproc.split(f'{F}')[0]
            result:str          = l_args[1]

            return result

        def strmsk(funcArgs:str, strproc:str) -> str:
            """
            string mask
            """
            F:str               = self.str_funcMarker
            A:str               = self.str_funcArgSep
            l_args:list[str]    = funcArgs.split(f'{A}')
            value:str           = strproc.split(f'{F}')[0]
            str_msk:str         = l_args[1]
            l_n:list            = []
            result:str          = ""

            for i, j in zip(list(value), list(str_msk)):
                if j == '*':    l_n.append(i)
                else:           l_n.append(j)
            result  = ''.join(l_n)
            return result

        def md5(funcArgs:str, strproc:str) -> str:
            """
            Apply an md5 hash on the <astr>. A single argument
            is accepted, denoting the length of the return hash.

            Args:
                funcArgs (str): the function_and_args construct
                strproc (str): the string to process

            Returns:
                str: the processed string
            """
            F:str               = self.str_funcMarker
            A:str               = self.str_funcArgSep
            l_args:list[str]    = funcArgs.split(f'{A}')
            value:str           = strproc.split(f'{F}')[0]
            chars:str               = ''
            result:str              = hashlib.md5(value.encode('utf-8')).hexdigest()
            if len(l_args) > 1:
                chars       = l_args[1]
                result:str  = result[0:int(chars)]
            return result

        def chrplc(funcArgs:str , strproc:str)-> str:
            """
            Replace characters in <astr>

            Args:
                funcArgs (str): the function_and_args construct
                strproc (str): the string to process

            Returns:
                str: the processed string
            """
            F:str               = self.str_funcMarker
            A:str               = self.str_funcArgSep
            l_args:list[str]    = funcArgs.split(f'{A}')
            value:str           = strproc.split(f'{F}')[0]
            result:str              = re.sub(f'{l_args[1]}', f'{l_args[2]}', value)
            return result

        def convertToNumber (s:str) -> int:
            return int.from_bytes(s.encode(), 'little')

        def convertFromNumber (n:int)-> bytes:
            return n.to_bytes(math.ceil(n.bit_length() / 8), 'little').decode()

        def dcmname(funcArgs:str, strproc) -> str:
            """
            replace <strproc> with name in DICOM conventions

            If passed a string in the "function" arguments, this is used to seed
            the name caller. If the same argument is used for additional calls to
            this sub-function, then the returned name will be identical.

            Args:
                funcArgs (str): the function_and_args construct
                strproc (str): the string to process

            Returns:
                str: the processed string
            """
            # pudb.set_trace()
            F:str               = self.str_funcMarker
            A:str               = self.str_funcArgSep
            l_args:list[str]    = funcArgs.split(f'{A}')
            value:str           = strproc.split(f'{F}')[0]
            result:str          = ""
            if len(l_args) >  1:
                randSeed:int    = convertToNumber(l_args[1])
                Faker.seed(randSeed)
            str_firstLast:str   = fake.name()
            l_firstLast:list    = str_firstLast.split()
            str_first:str       = l_firstLast[0]
            str_last:str        = l_firstLast[1]
            result              = '%s^%s' % (str_last.upper(), str_first.upper())
            if len(l_args) > 2:
                result += l_args[2]
            return result

        str_replace:str         = ''        # the lookup/processed tag value
        l_tags:list             = []        # the input string split by '%'
        func:str                = ''        # the function to apply
        tag:str                 = ''        # the tag in the funcTag combo
        result:str              = ''        # result of any applied function
        prevResult:str          = ''        # previous function stack result
        tagLookup:str           = ''        # the lookup value for the tag
        d_ret:dict[str, Any]    = {
            'status':           False,
            'funcApplied':      [],
            'result':           ""
        }
        T:str                   = self.str_tagMarker
        F:str                   = self.str_funcMarker
        S:str                   = self.str_funcSep

        if not f'{T}' in astr: return d_ret
        d_ret['status']     = True
        l_tags:list         = astr.split(f'{T}')[1:]
        for tagFunc in l_tags:
            l_tagFunc:list  = tagFunc.split(f'{F}')
            if len(l_tagFunc) > 1:  tag, func = (l_tagFunc[0], l_tagFunc[1])
            else:                   tag, func = (l_tagFunc[0], "")
            lt_hit:list[Tuple]  = self.tag_findDict(tag)
            tagLookup           = tag if not lt_hit else self.tag_lookup(lt_hit[0])
            if func:
                for f in func.split(f'{S}'):
                    tagFunc         = tagFunc.replace(f'{tag}', tagLookup)
                    b_funcDo:bool   = False
                    if 'echo'       in f: result  = echo(f, tagFunc)        ; b_funcDo  = True
                    if 'md5'        in f: result  = md5(f, tagFunc)         ; b_funcDo  = True
                    if 'strmsk'     in f: result  = strmsk(f, tagFunc)      ; b_funcDo  = True
                    if 'chrplc'     in f: result  = chrplc(f, tagFunc)      ; b_funcDo  = True
                    if 'dcmname'    in f: result  = dcmname(f, str_replace) ; b_funcDo  = True
                    d_ret['funcApplied'].append(b_funcDo)
                    if b_funcDo:
                        if f'{T}{tag}{F}{f},'       in astr:    astr:str    = astr.replace(f'{T}{tag}{F}{f},', f'{result}{F}')
                        if f'{T}{tag}{F}{f}{F}'     in astr:    astr:str    = astr.replace(f'{T}{tag}{F}{f}{F}', result)
                        if f'{prevResult}{F}{f},'   in astr:    astr:str    = astr.replace(f'{prevResult}{F}{f},', f'{result}{F}')
                        if f'{prevResult}{F}{f}{F}' in astr:    astr:str    = astr.replace(f'{prevResult}{F}{f}{F}', result)
                        if f'{tagLookup}{F}{f},'    in tagFunc: tagFunc:str = tagFunc.replace(f'{tagLookup}{F}{f},', f'{result}{F}')
                        if f'{tagLookup}{F}{f}{F}'  in tagFunc: tagFunc:str = tagFunc.replace(f'{tagLookup}{F}{f}{F}', result)
                        if f'{prevResult}{F}{f},'   in tagFunc: tagFunc:str = tagFunc.replace(f'{prevResult}{F}{f},', f'{result}{F}')
                        if f'{prevResult}{F}{f}{F}' in tagFunc: tagFunc:str = tagFunc.replace(f'{prevResult}{F}{f}{F}', result)
                    prevResult      = result
            elif lt_hit:
                if f'{T}{lt_hit[0][1]}' in astr:
                    astr:str    = astr.replace(f'{T}{lt_hit[0][1]}', tagLookup)
        d_ret['result'] = astr
        return d_ret

    def run(self, tag:str) -> dict:
        """Main "run" method

        Args:
            tag (str): the tag string to process

        Returns:
            dict: a status and result dictionary
        """
        b_status:bool       = False
        if not self.envOK:  return {'status': b_status}

        result:dict         = self.tag_process(tag)
        return result

    def __call__(self, tag:str, *args: Any, **kwds: Any) -> dict:
        self.options.tag = tag
        return self.run(tag)

def timestamp_dt(str_datetime:str) -> datetime:
    """
    Accept a string generated by the %timestamp tag and return a
    datetime object

    Args:
        str_datetime (str): a string generated by %timestamp

    Returns:
        datetime: a datetime object of the input
    """
    return datetime.strptime(str_datetime, '%Y-%m-%dT%H:%M:%S.%f%z')
