# pftag

[![ci](https://github.com/FNNDSC/pftag/actions/workflows/ci.yml/badge.svg)](https://github.com/FNNDSC/pftag/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pftag.svg)](https://pypi.org/project/pftag/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://pypi.org/project/pftag/)

A string template processor: `%{tags}` in text are resolved when the text is used, each optionally piped through functions. Both a library and a command.

## Overview

A template is ordinary text with tags in it. A tag is `%{`, a name, optional functions, `}`:

```
run-%{timestamp}-on-%{hostname}.log
%{inputWorkingFile|rmext}.jpg
%{timestamp|replace(:,-)|md5(6)}
%{"Subject12345"|sha256(8)}
```

Names resolve against the core tags (`timestamp`, `date`, `hostname`, `platform`, `user`, `pid`) and against dictionaries the calling program registers. Functions read left to right, each feeding the next; text after the closing `}` is kept. Nothing outside `%{...}` is a tag, so `printf "%s"`, `date +%Y%m%d` and `%20` in a URL pass through untouched. An unknown name is left as written unless `--strict`.

The full reference is [docs/tags.adoc](docs/tags.adoc). The pf* family uses pftag wherever a user writes a template on the command line: `pfdo_run`'s `--exec` string, `pflog`'s telemetry URLs.

## Installation

```bash
pip install pftag            # no dependencies
pip install 'pftag[names]'   # adds faker, for the dcmname pseudonym function
```

Python 3.11 or newer.

## Command

```bash
pftag --tag "run-%{timestamp}-on-%{hostname}.log"
pftag --tag "run-%{timestamp|replace(:,-)|md5(6)}.log"
pftag --tag "run-%{timestamp|strftime(%Y%m%d-%H%M)}.log"
pftag --lookupDictAdd '{"s": {"user": "chris"}}' --tag "user %{user}, hash %{user|md5(8)}"
pftag --tag "%{nope}" --strict        # exit 1: unknown tag
pftag --tag "..." --json              # the whole result: tags found, unknown, legacy, functions applied, errors
pftag --man
```

## Library

```python
import shlex
from pftag import Pftag, TagOptions

tagger = Pftag(TagOptions(lookups={"run": {"subject": "sub-01", "file": "T1.nii.gz"}}))
tagger("%{subject}/%{file|rmext}.jpg").result  # 'sub-01/T1.nii.jpg'
tagger.argv_process(shlex.split("convert %{file} %{file|rmext}.jpg")).argv
```

`process(template)` is for text; `argv_process(argv)` is for commands: split the user's command first, then each argument is a template of its own, so a value with a space or a quote cannot change the shape of the command. `lookup_add(name, values)` registers a dictionary; a `FunctionRegistry` passed to `Pftag` takes new functions with `add(name, fn)`, where `fn(value, args) -> str`.

## Functions

| function | effect |
|---|---|
| `rmext`, `ext`, `basename`, `dirname` | path parts |
| `replace(a, b)`, `re(pattern, repl)` | literal and regular-expression replacement |
| `upper`, `lower`, `strip[(chars)]`, `pad(width[, char])`, `slice(start[, stop])` | text shaping |
| `md5[(n)]`, `sha256[(n)]` | hashing |
| `strftime(format)` | format a timestamp |
| `mask(pattern)` | `*` keeps a character, anything else replaces it |
| `dcmname[(seed)]` | a `LAST^FIRST` pseudonym, stable for a seed; needs `pftag[names]` |

## Changes in 3.0

- Tags are `%{...}` only. The bare `%name` form is gone; a bare `%` is always literal. A bare `%name` of a known name is reported as a 1.x tag (and fails under `--strict`) so that old templates do not pass through silently.
- Functions are `|fn(arg, arg)` in pipe order; arguments bare or quoted; `fn` or `fn()`. A quoted head starts a chain from literal text, replacing `%literal` and `echo`.
- Names may contain underscores; `%{dict.name}` qualifies; two dictionaries defining one name is an error at registration.
- `argv_process` for commands. Values are substituted once, never re-processed.
- Functions renamed to common names: `replace`, `re`, `mask`; `ext`, `basename`, `dirname`, `strip`, `pad`, `slice`, `sha256`, `strftime` added; `chrplc`, `strrepl`, `strmsk`, `echo` gone. `dcmname` moves behind the `names` extra and seeds its own generator.
- Core tags: `timestamp`, `date`, `hostname`, `platform`, `user`, `pid`; `os`, `release`, `machine`, `arch`, `literal` gone.
- No configurable markers, no dependencies, no `pudb`/`loguru`/`XDG_CONFIG_HOME` side effects; `pyproject.toml` only, CI on 3.11–3.14 and 3.14t, published from a `v*` tag; the Docker image is no longer built.
