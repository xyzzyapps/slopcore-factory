"""Interfaces (protocols) for slopcore-factory.

Every external capability is an interface so the pipeline can be exercised with
fakes: no network, no API keys, no GPU, no spend. Concrete implementations live
in the feature slices (``song.py``, ``timing.py``, ``media.py``, ``render.py``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import Cue, FactorySpec, LyricsDoc, Storyboard, Transcript


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
class SongProvider(Protocol):
    """Acquires the audio track: use a supplied file or generate one."""

    def acquire(self, spec: FactorySpec, lyrics: LyricsDoc) -> Path: ...


@runtime_checkable
class Transcriber(Protocol):
    """Produces word-level timings for the audio."""

    def transcribe(self, audio: Path, lyrics: LyricsDoc, duration: float) -> Transcript: ...


@runtime_checkable
class Aligner(Protocol):
    """Aligns lyric lines to a transcript, producing timed cues."""

    def align(self, lyrics: LyricsDoc, transcript: Transcript) -> list[Cue]: ...


@runtime_checkable
class ClipProvider(Protocol):
    """Produces the background clip(s) for a song."""

    def acquire(self, spec: FactorySpec) -> list[Path]: ...


@runtime_checkable
class Planner(Protocol):
    """Turns aligned cues into a full storyboard."""

    def plan(self, spec: FactorySpec, lyrics: LyricsDoc, cues: list[Cue]) -> Storyboard: ...


@runtime_checkable
class Renderer(Protocol):
    """Drives the HyperFrames CLI for a generated project."""

    def check(self, project: Path) -> tuple[int, str]: ...

    def snapshot(self, project: Path, times: list[float]) -> list[Path]: ...

    def render(self, project: Path, out: Path, fps: int) -> Path: ...
