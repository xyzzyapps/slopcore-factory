"""Beat / downbeat grid estimation.

Optional. When ``librosa`` is installed we estimate a beat grid to inform frame
cuts; when it is not, we degrade to word-timing-only planning. An existing
``audiomap.json`` from the HyperFrames CLI is always preferred if present.
"""

from __future__ import annotations

import json
from pathlib import Path

from .logging_setup import get_logger
from .models import BeatGrid

log = get_logger("beats")


def load_audiomap(path: Path, duration: float) -> BeatGrid | None:
    """Read a HyperFrames ``audiomap.json`` if one exists."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("could not parse audiomap: %s", path)
        return None
    tempo = data.get("tempo", {})
    grid = data.get("grid", {})
    beats = [float(v) for v in grid.get("beats_sec", [])]
    downbeats = [float(v) for v in grid.get("downbeats_sec", [])]
    if not beats and not downbeats:
        return None
    return BeatGrid(
        bpm=float(tempo.get("bpm", 0.0)),
        duration=float(data.get("audio", {}).get("duration_sec", duration)),
        beats=beats,
        downbeats=downbeats,
    )


def estimate_beats(audio: Path, duration: float) -> BeatGrid:
    """Estimate beats with librosa; return an empty grid when unavailable."""
    try:  # pragma: no cover - optional heavy dependency
        import librosa
        import numpy as np
    except ImportError:
        log.info("librosa not installed; planning without a beat grid")
        return BeatGrid(bpm=0.0, duration=duration)

    try:  # pragma: no cover - requires real audio + librosa
        y, sr = librosa.load(str(audio), mono=True)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        beat_times = [round(float(t), 3) for t in librosa.frames_to_time(beat_frames, sr=sr)]
        downbeats = beat_times[::4]
        bpm = float(np.atleast_1d(tempo)[0])
        log.info("estimated %.1f bpm, %d beats", bpm, len(beat_times))
        return BeatGrid(bpm=bpm, duration=duration, beats=beat_times, downbeats=downbeats)
    except Exception as exc:  # noqa: BLE001 - never block a run on beat detection
        log.warning("beat estimation failed (%s); continuing without a grid", exc)
        return BeatGrid(bpm=0.0, duration=duration)
