"""Dry-run providers: the pipeline with zero spend (ffmpeg required)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from slopcore_factory.blueprint import SeedanceClip
from slopcore_factory.config import build_spec
from slopcore_factory.dryrun import (
    DryRunClipProvider,
    DryRunSongProvider,
    DryRunTranscriber,
    is_dry_run,
)
from slopcore_factory.lyrics import parse_lyrics

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required")


def test_dryrun_song_transcript_and_clip(tmp_path: Path, lyrics_file: Path) -> None:
    spec = build_spec(lyrics_file, tmp_path / "project", duration=5.0)
    doc = parse_lyrics(lyrics_file)

    audio = DryRunSongProvider().acquire(spec, doc)
    assert audio.exists()

    transcript = DryRunTranscriber().transcribe(audio, doc, 5.0)
    assert len(transcript.words) == len(doc.hint.split())
    assert transcript.duration == 5.0

    clip = DryRunClipProvider().generate(SeedanceClip("ls01", 2.0), tmp_path / "clips")
    assert clip.exists() and clip.suffix == ".mp4"


def test_is_dry_run_by_env(monkeypatch, tmp_path: Path, lyrics_file: Path) -> None:
    spec = build_spec(lyrics_file, tmp_path / "p")
    monkeypatch.setenv("SLOPCORE_FACTORY_DRY_RUN", "1")
    assert is_dry_run(spec)


def test_is_dry_run_by_spec(tmp_path: Path, lyrics_file: Path) -> None:
    spec = build_spec(lyrics_file, tmp_path / "p", overrides={"dry_run": True})
    assert is_dry_run(spec)
