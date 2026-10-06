"""Audio analysis: word gaps, vocal stem, and the derived timing map.

The prerequisite for lipsync is knowing the **gaps between words**: a lipsync
window may only start in a gap, never mid-word. This module computes those gaps
from the word timings, optionally separates the vocal stem (demucs, if present),
and persists the result so later stages do not recompute it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .errors import AudioError
from .logging_setup import get_logger
from .models import Transcript, Word

log = get_logger("audio")

MIN_GAP = 0.12  # shorter silences do not count as a gap


@dataclass
class Gap:
    """A silence between two words (or at the head/tail of the vocal)."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def middle(self) -> float:
        return (self.start + self.end) / 2


@dataclass
class AudioAnalysis:
    """Everything later stages need to know about the timing of the vocal."""

    duration: float
    word_count: int
    gaps: list[Gap] = field(default_factory=list)
    stem: str = ""
    has_stem: bool = False

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "word_count": self.word_count,
            "stem": self.stem,
            "has_stem": self.has_stem,
            "gaps": [{"start": g.start, "end": g.end} for g in self.gaps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> AudioAnalysis:
        return cls(
            duration=float(data.get("duration", 0.0)),
            word_count=int(data.get("word_count", 0)),
            stem=str(data.get("stem", "")),
            has_stem=bool(data.get("has_stem", False)),
            gaps=[Gap(float(g["start"]), float(g["end"])) for g in data.get("gaps", [])],
        )


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------


def find_gaps(words: list[Word], duration: float = 0.0, min_gap: float = MIN_GAP) -> list[Gap]:
    """Silences between consecutive words, plus head and tail gaps."""
    ordered = sorted(words, key=lambda w: w.start)
    if not ordered:
        return []

    gaps: list[Gap] = []
    if ordered[0].start >= min_gap:
        gaps.append(Gap(0.0, round(ordered[0].start, 3)))
    for a, b in zip(ordered, ordered[1:], strict=False):
        if b.start - a.end >= min_gap:
            gaps.append(Gap(round(a.end, 3), round(b.start, 3)))
    tail = duration or ordered[-1].end
    if tail - ordered[-1].end >= min_gap:
        gaps.append(Gap(round(ordered[-1].end, 3), round(tail, 3)))
    return gaps


def gap_at(t: float, gaps: list[Gap], epsilon: float = 0.01) -> Gap | None:
    """The gap containing ``t``, if any."""
    for gap in gaps:
        if gap.start - epsilon <= t <= gap.end + epsilon:
            return gap
    return None


def next_gap(t: float, gaps: list[Gap], epsilon: float = 0.01) -> Gap | None:
    """The first gap whose middle is at or after ``t``."""
    for gap in gaps:
        if gap.middle >= t - epsilon:
            return gap
    return None


def last_gap_before(t: float, gaps: list[Gap]) -> Gap | None:
    """The latest gap whose start is at or before ``t``."""
    best: Gap | None = None
    for gap in gaps:
        if gap.start <= t + 1e-6:
            best = gap
        else:
            break
    return best


# ---------------------------------------------------------------------------
# Vocal stem (optional)
# ---------------------------------------------------------------------------


def separate_vocals(audio: Path, out_dir: Path) -> Path:
    """Separate the vocal stem with demucs when it is installed.

    Returns the input unchanged when demucs is unavailable, so the pipeline can
    still run (the full mix is a usable reference for the avsync check).
    """
    audio = Path(audio)
    if shutil.which("demucs") is None:
        log.info("demucs not on PATH; using the full mix as the reference")
        return audio

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            shutil.which("demucs") or "demucs",
            "--two-stems=vocals",
            "-n",
            "htdemucs",
            "-o",
            str(out_dir),
            str(audio),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise AudioError(f"demucs failed: {(result.stderr or '').strip()[-400:]}")
    stem = out_dir / "htdemucs" / audio.stem / "vocals.wav"
    if not stem.exists():
        raise AudioError(f"demucs produced no vocals stem under {out_dir}")
    log.info("vocal stem: %s", stem)
    return stem


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze(
    audio: Path,
    transcript: Transcript,
    work_dir: Path | None = None,
    separate: bool = False,
) -> AudioAnalysis:
    """Build the analysis (gaps + optional stem) and persist it if asked."""
    audio = Path(audio)
    if not audio.exists():
        raise AudioError(f"audio not found: {audio}")

    duration = transcript.duration
    gaps = find_gaps(transcript.words, duration)
    stem_path = audio
    has_stem = False
    if separate and work_dir is not None:
        stem_path = separate_vocals(audio, Path(work_dir) / "stem")
        has_stem = stem_path != audio

    analysis = AudioAnalysis(
        duration=duration,
        word_count=len(transcript.words),
        gaps=gaps,
        stem=str(stem_path),
        has_stem=has_stem,
    )
    log.info(
        "analysis: %d words, %d gaps (median %.2fs)",
        analysis.word_count,
        len(gaps),
        sorted(g.duration for g in gaps)[len(gaps) // 2] if gaps else 0.0,
    )
    if work_dir is not None:
        path = Path(work_dir) / "analysis.json"
        path.write_text(json.dumps(analysis.to_dict(), indent=2), encoding="utf-8")
    return analysis


def load_analysis(path: Path) -> AudioAnalysis:
    return AudioAnalysis.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
