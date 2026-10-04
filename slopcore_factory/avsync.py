"""A/V sync check.

Compares a generated clip's own soundtrack against the reference vocal for its
window and reports the first drift point. Everything is local: ffmpeg decodes,
numpy correlates. No model, no network.

The reference may be the full mix (when no vocal stem is available); a separated
stem gives a cleaner comparison but is not required.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .blueprint import Blueprint
from .lipsync import detect_divergence
from .logging_setup import get_logger

log = get_logger("avsync")

SR = 16000


@dataclass
class AvsyncResult:
    """The sync verdict for one clip."""

    clip: str
    divergence: float | None
    checked_seconds: float

    @property
    def in_sync(self) -> bool:
        return self.divergence is None


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _resample(samples: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or len(samples) == 0:
        return samples.astype(np.float32)
    count = max(1, int(len(samples) * sr_out / sr_in))
    idx = np.linspace(0, len(samples) - 1, count)
    return np.interp(idx, np.arange(len(samples)), samples).astype(np.float32)


def decode_mono(path: Path, sr: int = SR) -> np.ndarray:
    """Decode any audio/video to mono float32 at ``sr`` (ffmpeg for non-wav)."""
    path = Path(path)
    if path.suffix.lower() == ".wav":
        data, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
        return _resample(data.mean(axis=1), file_sr, sr)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        try:
            subprocess.run(
                [
                    _ffmpeg(),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(path),
                    "-ac",
                    "1",
                    "-ar",
                    str(sr),
                    "-c:a",
                    "pcm_s16le",
                    str(wav),
                ],
                check=True,
            )
        except subprocess.CalledProcessError:
            log.warning("no audio stream in %s", path)
            return np.zeros(0, dtype=np.float32)
        data, _ = sf.read(str(wav), dtype="float32")
        return data.astype(np.float32)


def slice_seconds(samples: np.ndarray, sr: int, t0: float, duration: float) -> np.ndarray:
    a = max(0, int(t0 * sr))
    b = min(len(samples), int((t0 + duration) * sr))
    return samples[a:b]


def check_clip(
    clip_path: Path,
    reference_path: Path,
    song_t0: float,
    duration: float,
    sr: int = SR,
    threshold: float = 0.6,
) -> AvsyncResult:
    """Measure the drift point between a clip and the reference vocal slice."""
    reference = decode_mono(reference_path, sr)
    returned = decode_mono(clip_path, sr)
    ref_slice = slice_seconds(reference, sr, song_t0, duration)
    n = min(len(ref_slice), len(returned))
    if n == 0:
        return AvsyncResult(Path(clip_path).stem, None, 0.0)
    point = detect_divergence(ref_slice[:n], returned[:n], sr, threshold=threshold)
    return AvsyncResult(Path(clip_path).stem, point, round(n / sr, 3))


def check_blueprint(
    blueprint: Blueprint,
    reference_path: Path,
    clips_dir: Path | None = None,
    sr: int = SR,
    threshold: float = 0.6,
) -> list[AvsyncResult]:
    """Check every singing clip that has a local file."""
    results: list[AvsyncResult] = []
    for entry in blueprint.seedance:
        if not entry.sing:
            continue
        path = Path(entry.path) if entry.path else None
        if (path is None or not path.exists()) and clips_dir is not None:
            candidate = Path(clips_dir) / f"{entry.clip}.mp4"
            path = candidate if candidate.exists() else None
        if path is None or not path.exists():
            continue
        results.append(
            check_clip(path, reference_path, entry.song_t0, entry.duration, sr, threshold)
        )
    return results


def summarise(results: list[AvsyncResult]) -> str:
    if not results:
        return "no clips to check"
    checked = [r for r in results if r.checked_seconds > 0]
    in_sync = [r for r in checked if r.in_sync]
    sung = sum(r.checked_seconds for r in checked)
    text = (
        f"{len(in_sync)}/{len(checked)} clips in sync "
        f"({sung:.1f}s checked; {len(checked) - len(in_sync)} need a cover"
    )
    no_audio = len(results) - len(checked)
    if no_audio:
        text += f"; {no_audio} with no audio stream"
    return text + ")"
