"""Tests for the pftag command line."""

from __future__ import annotations

import json
import re

import pytest

from pftag import __version__
from pftag.__main__ import main, manual_build


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


def test_main_manPrintsFullManual_plainWhenPiped(capsys: pytest.CaptureFixture[str]) -> None:
    from pftag import __version__

    assert main(["--man"]) == 0
    text: str = capsys.readouterr().out
    for heading in (
        "NAME",
        "SYNOPSIS",
        "DESCRIPTION",
        "ARGUMENTS",
        "GRAMMAR",
        "TAGS",
        "FUNCTIONS",
        "EXAMPLES",
    ):
        assert re.search(rf"^    {heading}\s*$", text, re.M), heading
    assert "``" not in text and "\033" not in text
    assert f"version {__version__}" in text


def test_main_synopsisIsBrief(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--synopsis"]) == 0
    text: str = capsys.readouterr().out
    assert "SYNOPSIS" in text and "DESCRIPTION" not in text


def test_manual_colourised_page() -> None:
    from pftag.manual import BG_PAGE, FG_COMMAND, FG_FLAG, FG_HEADING, NO_COLOUR, manual_render

    manual = manual_build()
    page: str = manual_render(manual, shortOnly=False, colour=True, width=120)
    escape: re.Pattern[str] = re.compile(r"\033\[[0-9;]*m")
    lines: list[str] = page.splitlines()
    assert all(line.startswith(BG_PAGE) and line.endswith(NO_COLOUR) for line in lines)
    assert all(len(escape.sub("", line)) == 120 for line in lines)
    assert BG_PAGE + FG_HEADING + "    GRAMMAR" in page
    assert FG_COMMAND + "pftag" in page and FG_FLAG + "--tag" in page
