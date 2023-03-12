pftag
=====

|Version| |MIT License| |ci|

Abstract
--------

This software provides a string token parser, useful in cases where a
fixed *a priori* template string is to be resolved at run time by some
process.

Overview
--------

``pftag`` is a simple app that is both a stand alone client as well as a
python module. Its main purpose is to parse *template strings*. A
template string is one where sub-parts of the string are *tokenized* by
a token marker. These tokens are resolved at execution time.

From a taxonomy perspective, ``pftag`` implements a highly opinionated
SGML string parser.

Installation
------------

Local python venv
~~~~~~~~~~~~~~~~~

For *on the metal* installations, ``pip`` it:

.. code:: bash

   pip install pftag

docker container
~~~~~~~~~~~~~~~~

.. code:: bash

   docker pull fnndsc/pftag

Runnning
--------

Script mode
~~~~~~~~~~~

To use ``pftag`` in script mode you simply call the script with
appropriate arguments

.. code:: bash


   pftag --tag "run-%timestamp-on-%platform-%arch.log"

   run-2023-03-10T13:41:58.921660-05:00-on-Linux-64bit-ELF.log

Module mode
~~~~~~~~~~~

There are several ways to use ``pftag`` in python module mode. Perhaps
the simplest is just to declare an object and instantiate with an empty
dictionary. Then call the object with the ``tag`` to process.

If you wanted to set any other values in the declaration, use an
appropriate dictionary. The dictionary keys are *identical* to the
script CLI keys (*sans* the leading ``--``):

.. code:: python

   from pftag import pftag

   str_tag:str = r'run-%timestamp-on-%platform-%arch.log'

   tagger:pftag.Pftag      = pftag.Pftag({})
   d_tag:dict              = tagger(str_tag)

   # The result is in the
   print(d_tag['results'])

Arguments
---------

The set of CLI arguments can also be passed in a dictionary of

.. code:: python

   {
           "CLIkey1": "value1",
           "CLIkey2": "value2",
   }

.. code:: html

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

Available tags and functions
----------------------------

::

           TAGS

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

           FUNCTIONS

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

Functions
---------

::

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

Development
-----------

Instructions for developers.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To debug, the simplest mechanism is to trigger the internal remote
telnet session with the ``--debug`` CLI. Then, in the code, simply add
``Env.set_trace()`` calls where appropriate. These can remain in the
codebase (i.e. you don’t need to delete/comment them out) since they are
only *live* when a ``--debug`` flag is passed.

Testing
~~~~~~~

Run unit tests using ``pytest``

.. code:: bash

   # In repo root dir:
   pytest

*-30-*

.. |Version| image:: https://img.shields.io/docker/v/fnndsc/pftag?sort=semver
   :target: https://hub.docker.com/r/fnndsc/pftag
.. |MIT License| image:: https://img.shields.io/github/license/fnndsc/pftag
   :target: https://github.com/FNNDSC/pftag/blob/main/LICENSE
.. |ci| image:: https://github.com/FNNDSC/pftag/actions/workflows/ci.yml/badge.svg
   :target: https://github.com/FNNDSC/pftag/actions/workflows/build.yml
