"""Tests for the pftag engine: grammar, lookups, functions, escapes, commands."""

from __future__ import annotations

import hashlib
import re
import shlex
from datetime import datetime

import pytest

from pftag.functions import FunctionError, FunctionRegistry
from pftag.models import TagOptions
from pftag.pftag import CORE_TAGS, Pftag, TagSyntaxError, coreTag_value


def tagger_make(**lookups: dict[str, str]) -> Pftag:
    return Pftag(TagOptions(lookups=dict(lookups)))


def test_coreTags_resolve() -> None:
    tagger: Pftag = Pftag()
    for name in CORE_TAGS:
        assert tagger(f"%{{{name}}}").result
    datetime.fromisoformat(tagger("%{timestamp}").result)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", tagger("%{date}").result)
    assert tagger("%{pid}").result.isdigit()
    with pytest.raises(KeyError):
        coreTag_value("nope")


def test_plainTag_andAdjacentText() -> None:
    tagger: Pftag = tagger_make(run={"subject": "sub-01"})
    assert tagger("%{subject}-report.txt").result == "sub-01-report.txt"
    assert tagger("%{subject}_01").result == "sub-01_01"
    assert tagger("a%{subject}b").result == "asub-01b"


def test_namesMayHaveUnderscoresAndDigits() -> None:
    tagger: Pftag = tagger_make(run={"input_working_dir2": "/in"})
    assert tagger("%{input_working_dir2}/x").result == "/in/x"


def test_percentOutsideBracesIsLiteral() -> None:
    tagger: Pftag = tagger_make(run={"s": "x"})
    text: str = 'printf "%s %d" 100% done +%Y%m%d %20 %{s}'
    assert tagger(text).result == 'printf "%s %d" 100% done +%Y%m%d %20 x'


def test_escapedOpenIsLiteral() -> None:
    assert Pftag()(r"a \%{b} c").result == "a %{b} c"


def test_unknownTag_leftVerbatim() -> None:
    result = Pftag()("hello %{nobody} and %{also|md5}")
    assert result.status
    assert result.result == "hello %{nobody} and %{also|md5}"
    assert result.unknownTags == ["nobody", "also"]
    assert result.tagsFound == ["nobody", "also"]


def test_unknownTag_strictFails() -> None:
    result = Pftag(TagOptions(strict=True))("%{nobody}")
    assert not result.status
    assert result.errors == ["unknown tag %{nobody}"]


def test_legacyTag_reportedAndStrictFails() -> None:
    tagger: Pftag = tagger_make(run={"subject": "s"})
    lenient = tagger("run-%timestamp_md5|6_ %subject %{subject}")
    assert lenient.status
    assert lenient.legacyTags == ["%timestamp", "%subject"]
    assert lenient.result == "run-%timestamp_md5|6_ %subject s"
    strict = Pftag(TagOptions(lookups={"run": {"subject": "s"}}, strict=True))("%timestamp")
    assert not strict.status
    assert "1.x tag" in strict.errors[0]


def test_unclosedTag_fails() -> None:
    result = Pftag()("x %{timestamp y")
    assert not result.status
    assert "not closed" in result.errors[0]
    assert result.result == "x %{timestamp y"
    with pytest.raises(TagSyntaxError):
        Pftag().token_parse("%{}", 0)


def test_literalHead() -> None:
    assert Pftag()('%{"hello"|upper}').result == "HELLO"
    assert Pftag()("%{'a|b, c'|upper}").result == "A|B, C"
    assert Pftag()(r'%{"say \"hi\""}').result == 'say "hi"'


def test_function_withoutAndWithParens() -> None:
    tagger: Pftag = tagger_make(run={"file": "brain.nii.gz"})
    assert tagger("%{file|rmext}.txt").result == "brain.nii.txt"
    assert tagger("%{file|rmext()}").result == "brain.nii"
    assert tagger("%{file|rmext|rmext}").result == "brain"


def test_function_bareAndQuotedArgs() -> None:
    tagger: Pftag = Pftag()
    assert tagger('%{"a:b:c"|replace(:,-)}').result == "a-b-c"
    assert tagger('%{"a:b:c"|replace( : , - )}').result == "a-b-c"
    assert tagger('%{"a:b:c"|replace(":", "-")}').result == "a-b-c"
    assert tagger("%{'a,b'|replace(',', ';')}").result == "a;b"
    assert tagger('%{\'a)b\'|replace(")", "]")}').result == "a]b"


def test_function_chain() -> None:
    expected: str = hashlib.md5(b"HELLO").hexdigest()[:6]
    result = Pftag()('%{"hello"|upper|md5(6)}')
    assert result.result == expected
    assert result.functionsApplied == ["upper()", "md5(6)"]


def test_function_unknownFailsAndLeavesTag() -> None:
    result = Pftag()("x %{date|nosuch} y")
    assert not result.status
    assert result.result == "x %{date|nosuch} y"
    assert "unknown function 'nosuch'" in result.errors[0]


def test_function_badArgsFail() -> None:
    for template in ("%{date|md5(many)}", "%{date|replace(x)}", "%{date|rmext(x)}", "%{date|pad(3,ab)}"):
        result = Pftag()(template)
        assert not result.status, template
        assert result.result == template


def test_function_syntaxErrors() -> None:
    for template in ("%{date|}", "%{date|md5(}", "%{date|md5(1 2)}", "%{date|md5(1}"):
        result = Pftag()(template)
        assert not result.status, template


def test_qualifiedNames_andDuplicates() -> None:
    tagger: Pftag = tagger_make(a={"user": "alice"}, b={"other": "x"})
    assert tagger("%{a.user} %{user} %{b.other}").result == "alice alice x"
    assert tagger("%{b.user}").unknownTags == ["b.user"]
    with pytest.raises(ValueError, match="already defined"):
        tagger.lookup_add("c", {"user": "carol"})
    tagger.lookup_add("a", {"user": "alice2"})  # redefining the same dictionary is allowed
    assert tagger("%{user}").result == "alice2"


def test_lookupShadowsCore_andCoreQualifier() -> None:
    tagger: Pftag = tagger_make(mine={"platform": "custom"})
    assert tagger("%{platform}").result == "custom"
    assert tagger("%{core.platform}").result == coreTag_value("platform")


def test_lookup_rejectsBadNames() -> None:
    with pytest.raises(ValueError, match="identifier"):
        tagger_make(bad={"a-b": "x"})
    with pytest.raises(ValueError, match="identifier"):
        Pftag().lookup_add("has space", {"a": "x"})
    with pytest.raises(ValueError, match="core"):
        Pftag().lookup_add("core", {"a": "x"})


def test_lookupsFromJson_bothShapes() -> None:
    tagger: Pftag = Pftag()
    tagger.lookups_addFromJson('{"s": {"user": "chris", "n": 3}}')
    tagger.lookups_addFromJson('[{"t": {"pw": "secret"}}]')
    hashed: str = hashlib.md5(b"secret").hexdigest()[:4]
    assert tagger("%{user}:%{n}:%{pw|md5(4)}").result == f"chris:3:{hashed}"
    for bad in ("not json", "[1]", '{"s": "flat"}'):
        with pytest.raises(ValueError):
            tagger.lookups_addFromJson(bad)


def test_noRecursion() -> None:
    tagger: Pftag = tagger_make(run={"a": "%{b}", "b": "B"})
    assert tagger("%{a}").result == "%{b}"


def test_argv_process_keepsArgumentsIntact() -> None:
    tagger: Pftag = tagger_make(pfdo={"file": "my file.nii", "out": "/out/dir with space"})
    argv: list[str] = shlex.split('convert "%{file}" %{out}/%{file|rmext}.jpg --label "a %{file}"')
    result = tagger.argv_process(argv)
    assert result.status
    assert result.argv == [
        "convert",
        "my file.nii",
        "/out/dir with space/my file.jpg",
        "--label",
        "a my file.nii",
    ]
    assert len(result.results) == 5


def test_argv_process_failureStopsCommand() -> None:
    result = Pftag().argv_process(["convert", "%{nope|rmext}", "%{date|nosuch}"])
    assert not result.status
    assert result.argv[1] == "%{nope|rmext}"
    assert len(result.errors()) == 1


def test_registry_custom() -> None:
    registry: FunctionRegistry = FunctionRegistry()
    registry.add("shout", lambda value, args: value.upper() + "!")
    assert Pftag(registry=registry)('%{"hi"|shout}').result == "HI!"
    assert "shout" in registry.names()
    with pytest.raises(FunctionError, match="unknown function"):
        registry.apply("nosuch", "x", [])


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ('%{"brain.nii.gz"|rmext}', "brain.nii"),
        ('%{"brain"|rmext}', "brain"),
        ('%{"brain.nii.gz"|ext}', "gz"),
        ('%{"/a/b/c.txt"|basename}', "c.txt"),
        ('%{"/a/b/c.txt"|dirname}', "/a/b"),
        ('%{"a.b.c"|replace(., -)}', "a-b-c"),
        ('%{"a1b22c"|re([0-9]+, #)}', "a#b#c"),
        ('%{"MiXed"|lower}', "mixed"),
        ('%{"  x  "|strip}', "x"),
        ('%{"xxhixx"|strip(x)}', "hi"),
        ('%{"7"|pad(4)}', "0007"),
        ('%{"7"|pad(3, _)}', "__7"),
        ('%{"abcdef"|slice(3)}', "abc"),
        ('%{"abcdef"|slice(1, 4)}', "bcd"),
        ('%{"Linux"|mask(l****)}', "linux"),
        ('%{"Linux"|mask(L**X)}', "LinXx"),
        ('%{"2026-10-13T21:40:12.118000-04:00"|strftime(%Y%m%d-%H%M)}', "20261013-2140"),
    ],
)
def test_builtinFunctions(template: str, expected: str) -> None:
    assert Pftag()(template).result == expected


def test_sha256() -> None:
    assert Pftag()('%{"x"|sha256(8)}').result == hashlib.sha256(b"x").hexdigest()[:8]


def test_strftime_rejectsNonTimestamp() -> None:
    result = Pftag()('%{"yesterday"|strftime(%Y)}')
    assert not result.status
    assert "ISO 8601" in result.errors[0]


def test_dcmname_stableAndSeeded() -> None:
    pytest.importorskip("faker")
    tagger: Pftag = Pftag()
    byValue: str = tagger('%{"Subject12345"|dcmname}').result
    assert tagger('%{"Subject12345"|dcmname}').result == byValue
    assert re.fullmatch(r"[A-Z' -]+\^[A-Z' -]+", byValue)
    seeded: str = tagger('%{"anything"|dcmname(study-1)}').result
    assert tagger('%{"else"|dcmname(study-1)}^ANON').result == seeded + "^ANON"
