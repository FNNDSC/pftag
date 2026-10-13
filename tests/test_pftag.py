"""Tests for the pftag engine: tokenizer, lookups, functions, chains, escapes."""

from __future__ import annotations

import hashlib
import re

import pytest

from pftag.functions import FunctionError, FunctionRegistry
from pftag.models import TagOptions
from pftag.pftag import CORE_TAGS, Pftag, coreTag_value


def tagger_make(**lookups: dict[str, str]) -> Pftag:
    return Pftag(TagOptions(lookups=dict(lookups)))


def test_coreTags_resolve() -> None:
    tagger: Pftag = Pftag()
    for name in CORE_TAGS:
        assert tagger(f"%{name}").result == coreTag_value(name) or name == "timestamp"
    assert re.match(r"\d{4}-\d{2}-\d{2}T", tagger("%timestamp").result)


def test_plainTag_runsIntoText() -> None:
    tagger: Pftag = tagger_make(run={"subject": "sub-01"})
    assert tagger("%subject-report.txt").result == "sub-01-report.txt"
    assert tagger("a%subjectb").result == "asub-01b"


def test_longestNameWins() -> None:
    tagger: Pftag = tagger_make(run={"in": "SHORT", "inputWorkingDir": "/in/a"})
    assert tagger("%inputWorkingDir/x").result == "/in/a/x"
    assert tagger("%in/x").result == "SHORT/x"


def test_lookupOverridesCore() -> None:
    assert tagger_make(mine={"os": "custom"})("%os").result == "custom"


def test_unknownTag_leftVerbatim() -> None:
    result = Pftag()("hello %nobody and %also_md5_ here")
    assert result.status
    assert result.result == "hello %nobody and %also_md5_ here"
    assert result.unknownTags == ["nobody", "also"]
    assert result.tagsFound == ["nobody", "also"]


def test_unknownTag_strictFails() -> None:
    result = Pftag(TagOptions(strict=True))("%nobody")
    assert not result.status
    assert result.errors == ["unknown tag %nobody"]


def test_bareMarker_isLiteral() -> None:
    assert Pftag()("100% done, 50%").result == "100% done, 50%"


def test_escapedMarker_isLiteral() -> None:
    tagger: Pftag = Pftag()
    assert tagger(r"\%platform").result == "%platform"
    assert tagger(r"a\_b").result == "a_b"


def test_function_single() -> None:
    assert Pftag()("%literal_upper_").result == "LITERAL"


def test_function_withArgsAndTrailingText() -> None:
    tagger: Pftag = tagger_make(run={"file": "brain.nii.gz"})
    assert tagger("%file_rmext_.txt").result == "brain.nii.txt"
    assert tagger("%file_rmext,rmext_").result == "brain"


def test_function_chain() -> None:
    expected: str = hashlib.md5(b"HELLO").hexdigest()[:6]
    assert Pftag()("%literal_echo|hello,upper,md5|6_").result == expected


def test_function_escapedArgument() -> None:
    assert Pftag()(r"%literal_echo|a\,b\|c\_d_").result == "a,b|c_d"


def test_function_unknownFailsAndLeavesTag() -> None:
    result = Pftag()("x %literal_nosuch_ y")
    assert not result.status
    assert result.result == "x %literal_nosuch_ y"
    assert "unknown function 'nosuch'" in result.errors[0]


def test_function_badArgsFail() -> None:
    result = Pftag()("%literal_md5|many_")
    assert not result.status
    assert "integer" in result.errors[0]


def test_function_unterminatedChainIsPlainTag() -> None:
    assert Pftag()("%literal_md5").result == "literal_md5"


def test_functionsApplied_recorded() -> None:
    result = Pftag()("%literal_echo|x,upper_ %platform_lower_")
    assert result.functionsApplied == ["echo|x", "upper", "lower"]


def test_markers_configurable() -> None:
    options: TagOptions = TagOptions(tagMarker="@", funcMarker="[", funcArgMarker=",", funcSep="|")
    tagger: Pftag = Pftag(options)
    assert tagger("@literal[echo,hi|upper[ 100% _ok").result == "HI 100% _ok"


def test_markers_mustBeSingleAndDistinct() -> None:
    with pytest.raises(ValueError, match="one character"):
        TagOptions(tagMarker="%%")
    with pytest.raises(ValueError, match="differ"):
        TagOptions(funcMarker="|")


def test_lookup_rejectsNamesWithMarkers() -> None:
    with pytest.raises(ValueError, match="marker"):
        tagger_make(bad={"a_b": "x"})


def test_lookupsFromJson_bothShapes() -> None:
    tagger: Pftag = Pftag()
    tagger.lookups_addFromJson('{"s": {"user": "chris"}}')
    tagger.lookups_addFromJson('[{"t": {"pw": "secret"}}]')
    assert tagger("%user:%pw_md5|4_").result == f"chris:{hashlib.md5(b'secret').hexdigest()[:4]}"
    assert set(tagger.lookupNames) == {"core", "s", "t"}


def test_lookupsFromJson_rejectsBadShapes() -> None:
    tagger: Pftag = Pftag()
    for bad in ("not json", "[1]", '{"s": "flat"}'):
        with pytest.raises(ValueError):
            tagger.lookups_addFromJson(bad)


def test_pfdoRun_usage() -> None:
    tagger: Pftag = tagger_make(
        pfdo={
            "inputWorkingDir": "/in/sub-01",
            "outputWorkingDir": "/out/sub-01",
            "inputWorkingFile": "T1.nii.gz",
        }
    )
    command = tagger(
        "convert %inputWorkingDir/%inputWorkingFile %outputWorkingDir/%inputWorkingFile_rmext_.jpg"
    )
    assert command.result == "convert /in/sub-01/T1.nii.gz /out/sub-01/T1.nii.jpg"


def test_registry_custom() -> None:
    registry: FunctionRegistry = FunctionRegistry()
    registry.add("shout", lambda value, args: value.upper() + "!")
    assert Pftag(registry=registry)("%literal_shout_").result == "LITERAL!"
    assert "shout" in registry.names()
    with pytest.raises(FunctionError):
        registry.apply("nosuch", "x", [])


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("%literal_strmsk|l****_", "literal"),
        ("%literal_strmsk|L**X_", "LitXral"),
        ("%literal_chrplc|l|L_", "LiteraL"),
        ("%literal_chrplc|re:[aeiou]|*_", "l*t*r*l"),
        ("%literal_strrepl|t|T_", "liTeral"),
        ("%literal_echo|a.b.c,rmext_", "a.b"),
        ("%literal_echo|noext,rmext_", "noext"),
        ("%literal_echo|MiXed,lower_", "mixed"),
    ],
)
def test_builtinFunctions(template: str, expected: str) -> None:
    assert Pftag()(template).result == expected


def test_dcmname_seededAndTailed() -> None:
    tagger: Pftag = Pftag()
    first: str = tagger("%literal_dcmname|foobar_").result
    assert tagger("%literal_dcmname|foobar_").result == first
    assert re.fullmatch(r"[A-Z' -]+\^[A-Z' -]+", first)
    assert tagger("%literal_dcmname|foobar|^ANON_").result == first + "^ANON"
    assert tagger("%literal_name|foobar_").result == first
