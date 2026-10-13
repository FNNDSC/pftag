# pftag

[![ci](https://github.com/FNNDSC/pftag/actions/workflows/ci.yml/badge.svg)](https://github.com/FNNDSC/pftag/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pftag.svg)](https://pypi.org/project/pftag/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://pypi.org/project/pftag/)

A string template processor: `%tags` in text are resolved at run time, each optionally passed through a chain of functions. Both a library and a command.

## Overview

A template is ordinary text with tags in it. A tag is `%` and a name, optionally followed by functions between underscores:

```
run-%timestamp-on-%platform.log
run-%timestamp_chrplc|:|-_-on-%platform.log
%subject_upper_-%timestamp_chrplc|:|-,md5|6_.log
```

The name is looked up in the core tags (`timestamp`, `platform`, `os`, `release`, `machine`, `arch`, `literal`) or in dictionaries the caller registers. Functions read left to right, each feeding the next; text after the closing underscore is kept, so `%file_rmext_.txt` keeps its `.txt`. A name that is not known is left as written unless `--strict`. A backslash before any marker makes it literal.

The pf* family uses pftag wherever a user writes a template on the command line: `pfdo_run`'s `--exec` string, `pflog`'s telemetry URLs.

## Installation

```bash
pip install pftag
```

Python 3.11 or newer; depends on `faker` for the `dcmname` function.

## Command

```bash
pftag --tag "run-%timestamp-on-%platform.log"
pftag --tag "run-%timestamp_chrplc|:|-,md5|6_-on-%platform.log"
pftag --lookupDictAdd '{"s": {"user": "chris"}}' --tag "user %user hash %user_md5|8_"
pftag --tag "%nope" --strict        # exit 1: unknown tag
pftag --tag "..." --json            # the whole result: tags found, unknown, functions applied, errors
pftag --man
```

The four grammar characters are options: `--tagMarker`, `--funcMarker`, `--funcArgMarker`, `--funcSep`.

## Library

```python
from pftag import Pftag, TagOptions

tagger = Pftag(TagOptions(lookups={"run": {"subject": "sub-01", "file": "T1.nii.gz"}}))
result = tagger("%subject/%file_rmext_.jpg")
result.result  # 'sub-01/T1.nii.jpg'
result.tagsFound  # ['subject', 'file']
result.functionsApplied  # ['rmext']
```

`Pftag.lookup_add(name, values)` registers a dictionary after construction; `lookups_addFromJson` takes the command line's JSON. `TagResult.status` is False when `strict` met an unknown tag or a function failed, in which case the failing tag is left as written and `errors` says why. A `FunctionRegistry` holds the functions and takes new ones with `add(name, fn)`, where `fn(value, args) -> str`.

## Functions

| function | effect |
|---|---|
| `echo\|<text>` | replace the value with `<text>`; with `%literal`, injects text |
| `md5[\|<chars>]` | MD5 hex digest, cut to `<chars>` |
| `chrplc\|<target>\|<new>` | replace literal `<target>`; `re:<pattern>` for a regular expression |
| `strrepl\|<target>\|<new>` | the same, under pfdo_run's name |
| `strmsk\|<mask>` | per position, `*` keeps the character, anything else replaces it |
| `rmext` | drop the last extension |
| `upper`, `lower` | change case |
| `dcmname[\|<seed>[\|<tail>]]`, `name` | a `LAST^FIRST` name, stable for a given seed |

## Changes in 2.0

- A real tokenizer: names are matched longest first, functions are parsed to their closing marker, nothing is matched by substring. `%os` no longer fires inside `%outputWorkingDir`; a chained function no longer rewrites the same text elsewhere in the template.
- Functions can be chained, arguments can contain escaped markers, and an unterminated chain is a plain tag followed by text.
- `strmsk` never shortens the value; `chrplc` is literal unless `re:`; `rmext` and `strrepl` added from pfdo_run; `upper` and `lower` added.
- `dcmname` seeds its own generator rather than the global one, and builds the name from first and last names so prefixes cannot break it.
- `Pftag(TagOptions(...))` returns a `TagResult` dataclass, not a dict; `lookup_add` takes a dictionary, not JSON.
- `--strict`, `--json`; `--version`, `--man`, `--synopsis` exit 0; `main(argv)` honours `argv`.
- No `pudb`, `loguru` or `XDG_CONFIG_HOME` side effects at import; the removed `--inputdir`, `--outputdir`, `--osenv` and `--debug*` options did nothing.
- Packaging is `pyproject.toml` only, published from CI on a `v*` tag; the Docker image is no longer built.
