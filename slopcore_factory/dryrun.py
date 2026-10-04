"""Dry-run providers: the whole pipeline with zero spend.

When dry-run is on, every paid provider is replaced by a local one:

* :class:`DryRunSongProvider` writes a placeholder audio track (ffmpeg sine),
* :class:`DryRunTranscriber` spreads the lyric words evenly over the duration,
* :class:`DryRunClipProvider` writes a placeholder clip per Seedance entry.

Nothing here touches the network, so the entire chain (song -> align -> blueprint
-> lipsync -> clips -> avsync -> build -> render) can be exercised for free.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .blueprint import SeedanceClip
from .logging_setup import get_logger
from .models import FactorySpec, LyricsDoc, Transcript, Word

log = get_logger("dryrun")

ENV_FLAG = "SLOPCORE_FACTORY_DRY_RUN"


def is_dry_run(spec: FactorySpec) -> bool:
    """True when dry-run is requested by flag or environment."""
    return bool(spec.extra.get("dry_run")) or os.environ.get(ENV_FLAG) == "1"


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


class DryRunSongProvider:
    """A placeholder audio track of the requested length."""

    def acquire(self, spec: FactorySpec, lyrics: LyricsDoc) -> Path:
        duration = float(spec.duration or 180.0)
        assets = Path(spec.out_dir) / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        dest = assets / "bgm.wav"
        subprocess.run(
            [
                _ffmpeg(),
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=110:duration={duration}",
                "-c:a",
                "pcm_s16le",
                str(dest),
            ],
            check=True,
        )
        (assets / "song_takes.json").write_text(
            json.dumps(
                {
                    "dry_run": True,
                    "chosen": 1,
                    "takes": [{"take": 1, "path": dest.relative_to(assets.parent).as_posix()}],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log.info("dry-run song: %s (%.1fs)", dest, duration)
        return dest


class DryRunTranscriber:
    """Evenly spaced word timings derived from the lyrics (no whisper)."""

    def transcribe(self, audio: Path, lyrics: LyricsDoc, duration: float) -> Transcript:
        tokens: list[str] = []
        for line in lyrics.lines:
            tokens.extend(line.text.split())
        total = float(duration or 180.0)
        if not tokens:
            return Transcript(engine="dry-run", duration=total, words=[])
        step = total / (len(tokens) + 1)
        words: list[Word] = []
        t = step
        for token in tokens:
            words.append(Word(token, round(t, 3), round(t + 0.3, 3)))
            t += step
        log.info("dry-run transcript: %d words over %.1fs", len(words), total)
        return Transcript(engine="dry-run", duration=round(total, 3), words=words)


class DryRunClipProvider:
    """A placeholder clip per Seedance entry (a silent colour card)."""

    def generate(self, entry: SeedanceClip, out_dir: Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{entry.clip}.mp4"
        subprocess.run(
            [
                _ffmpeg(),
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x101014:s=854x480:d={max(0.5, entry.duration):.3f}:r=30",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(dest),
            ],
            check=True,
        )
        log.info("dry-run clip %s: %s (%.2fs)", entry.clip, dest, entry.duration)
        return dest
