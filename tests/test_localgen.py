"""Local song backend tests (a fake wrapper command, no model, no API)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from slopcore_factory.config import build_spec
from slopcore_factory.errors import SongGenerationError
from slopcore_factory.localgen import AceStepSongProvider, YuESongProvider
from slopcore_factory.lyrics import parse_lyrics

WRAPPER = """\
import json, sys
args = sys.argv[1:]
request = args[args.index("--request") + 1]
out = args[args.index("--out") + 1]
data = json.load(open(request, encoding="utf-8"))
open(out, "wb").write(b"RIFF" + data["lyrics"].encode()[:16])
print("ok")
"""


@pytest.fixture
def wrapper(tmp_path: Path) -> str:
    path = tmp_path / "wrapper.py"
    path.write_text(WRAPPER, encoding="utf-8")
    return f"{sys.executable} {path}"


def test_yue_backend_runs_wrapper(tmp_path: Path, lyrics_file: Path, wrapper: str) -> None:
    spec = build_spec(lyrics_file, tmp_path / "project", duration=12.0)
    doc = parse_lyrics(lyrics_file)
    provider = YuESongProvider(command=wrapper)
    out = provider.acquire(spec, doc)
    assert out.exists()
    assert out.name == "bgm-yue.wav"
    request = json.loads((tmp_path / "project" / "data" / "song_request.json").read_text())
    assert request["backend"] == "yue"
    assert request["duration"] == 12.0
    assert "Stay." in request["lyrics"]


def test_ace_step_backend_name(tmp_path: Path, lyrics_file: Path, wrapper: str) -> None:
    spec = build_spec(lyrics_file, tmp_path / "project", duration=12.0)
    doc = parse_lyrics(lyrics_file)
    out = AceStepSongProvider(command=wrapper).acquire(spec, doc)
    assert out.name == "bgm-ace_step.wav"


def test_backend_without_command_raises(tmp_path: Path, lyrics_file: Path, monkeypatch) -> None:
    monkeypatch.delenv("SLOPCORE_YUE_CMD", raising=False)
    spec = build_spec(lyrics_file, tmp_path / "project")
    doc = parse_lyrics(lyrics_file)
    with pytest.raises(SongGenerationError):
        YuESongProvider().acquire(spec, doc)


def test_backend_from_env(tmp_path: Path, lyrics_file: Path, wrapper: str, monkeypatch) -> None:
    monkeypatch.setenv("SLOPCORE_ACE_STEP_CMD", wrapper)
    spec = build_spec(lyrics_file, tmp_path / "project", duration=8.0)
    doc = parse_lyrics(lyrics_file)
    assert AceStepSongProvider().available()
    assert AceStepSongProvider().acquire(spec, doc).exists()
