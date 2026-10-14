"""Tests for the pftag command line."""

from __future__ import annotations

import json

import pytest

from pftag import __version__
from pftag.__main__ import main


def test_main_printsResult(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tag", 'x-%{"literal"|upper}-y 100%']) == 0
    assert capsys.readouterr().out == "x-LITERAL-y 100%\n"


def test_main_jsonResult(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tag", "%{date} %{nope} %timestamp", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unknownTags"] == ["nope"]
    assert payload["legacyTags"] == ["%timestamp"]
    assert payload["status"] is True


def test_main_strictExitsOne(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tag", "%{nope}", "--strict"]) == 1
    assert "unknown tag %{nope}" in capsys.readouterr().err
    assert main(["--tag", "%timestamp", "--strict"]) == 1
    assert "1.x tag" in capsys.readouterr().err


def test_main_lookupDictAdd(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--lookupDictAdd", '{"s": {"user": "chris"}}', "--tag", "hi %{user} %{s.user|upper}"]) == 0
    assert capsys.readouterr().out == "hi chris CHRIS\n"


def test_main_badLookupIsUsageError() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--lookupDictAdd", "nope", "--tag", "x"])
    assert exc.value.code == 2


def test_main_tagRequired() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_main_functionFailureExitsOne(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tag", "%{date|nosuch}"]) == 1
    assert "unknown function" in capsys.readouterr().err


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
    assert "%{inputWorkingFile|rmext}.jpg" in out
    assert main(["--synopsis"]) == 0
    assert "GRAMMAR" not in capsys.readouterr().out
