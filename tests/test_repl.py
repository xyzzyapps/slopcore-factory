"""REPL smoke tests (no pipeline, no network)."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.config import build_spec
from slopcore_factory.locator import ServiceLocator
from slopcore_factory.repl import Repl


def _repl(tmp_path: Path, lyrics_file: Path) -> Repl:
    spec = build_spec(lyrics_file, tmp_path / "project")
    return Repl(spec, tmp_path / "work", ServiceLocator())


def test_lyrics_and_quit(tmp_path: Path, lyrics_file: Path) -> None:
    repl = _repl(tmp_path, lyrics_file)
    assert not repl.onecmd("lyrics")
    assert repl.onecmd("quit") is True


def test_unknown_command_does_not_crash(tmp_path: Path, lyrics_file: Path) -> None:
    repl = _repl(tmp_path, lyrics_file)
    repl.onecmd("definitely-not-a-command")


def test_takes_without_manifest(tmp_path: Path, lyrics_file: Path) -> None:
    repl = _repl(tmp_path, lyrics_file)
    repl.onecmd("takes")  # prints a message, must not raise
