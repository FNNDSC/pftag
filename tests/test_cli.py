"""Tests for the pftag command line."""

from __future__ import annotations

import json

import pytest

from pftag import __version__
from pftag.__main__ import main


def test_main_printsResult(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tag", "x-%literal_upper_-y"]) == 0
    assert capsys.readouterr().out == "x-LITERAL-y\n"


def test_main_jsonResult(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tag", "%literal %nope", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "literal %nope"
    assert payload["unknownTags"] == ["nope"]


def test_main_strictUnknownExitsOne(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tag", "%nope", "--strict"]) == 1
    assert "unknown tag %nope" in capsys.readouterr().err


def test_main_lookupDictAdd(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--lookupDictAdd", '{"s": {"user": "chris"}}', "--tag", "hi %user"]) == 0
    assert capsys.readouterr().out == "hi chris\n"


def test_main_badLookupIsUsageError() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--lookupDictAdd", "nope", "--tag", "x"])
    assert exc.value.code == 2


def test_main_tagRequired() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_main_customMarkers(capsys: pytest.CaptureFixture[str]) -> None:
    code: int = main(
        [
            "--tagMarker",
            "@",
            "--funcMarker",
            "[",
            "--funcArgMarker",
            ",",
            "--funcSep",
            "|",
            "--tag",
            "@literal[upper[",
        ]
    )
    assert code == 0
    assert capsys.readouterr().out == "LITERAL\n"


def test_main_versionAndManual(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
    assert main(["--man"]) == 0
    out: str = capsys.readouterr().out
    for section in (
        "NAME",
        "SYNOPSIS",
        "DESCRIPTION",
        "ARGUMENTS",
        "GRAMMAR",
        "TAGS",
        "FUNCTIONS",
        "EXAMPLES",
    ):
        assert section in out
    assert __version__ in out
    assert main(["--synopsis"]) == 0
    assert "GRAMMAR" not in capsys.readouterr().out
