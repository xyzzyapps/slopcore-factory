"""Interfaces (protocols) for slopcore-factory.

The capabilities the pipeline needs from the outside world are protocols, so the
pipeline can be exercised with fakes: no network, no API keys, no GPU, no spend.
Concrete implementations live in the feature slices (``timing.py``,
``media.py``, ``render.py``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import Cue, LyricsDoc, Transcript


@runtime_checkable
class CommandRunner(Protocol):
    """Runs an external program and returns the completed process."""

    def run(
        self,
        args: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess: ...


@runtime_checkable
class Transcriber(Protocol):
    """Produces word-level timings for the audio."""

    def transcribe(self, audio: Path, lyrics: LyricsDoc, duration: float) -> Transcript: ...


@runtime_checkable
class Aligner(Protocol):
    """Aligns lyric lines to a transcript, producing timed cues."""

    def align(self, lyrics: LyricsDoc, transcript: Transcript) -> list[Cue]: ...
