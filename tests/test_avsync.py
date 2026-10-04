"""A/V sync tests on synthetic wav files (no network, no paid calls)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from slopcore_factory.avsync import AvsyncResult, check_clip, decode_mono, slice_seconds, summarise

SR = 16000


def _write(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    sf.write(str(path), samples.astype(np.float32), sr)


def test_decode_and_slice(tmp_path: Path) -> None:
    samples = (np.arange(SR, dtype=np.float32) / SR) - 0.5
    path = tmp_path / "a.wav"
    _write(path, samples)
    decoded = decode_mono(path)
    assert len(decoded) == SR
    chunk = slice_seconds(decoded, SR, 0.5, 0.25)
    assert len(chunk) == int(0.25 * SR)


def test_check_clip_detects_drift(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    reference = rng.standard_normal(SR * 8).astype(np.float32)
    ref_path = tmp_path / "ref.wav"
    _write(ref_path, reference)

    clip = reference[SR * 4 : SR * 12].copy()
    cut = SR * 3
    clip[cut:] = rng.standard_normal(len(clip) - cut).astype(np.float32) * np.std(reference)
    clip_path = tmp_path / "clip.wav"
    _write(clip_path, clip)

    result = check_clip(clip_path, ref_path, song_t0=4.0, duration=8.0)
    assert result.divergence is not None
    assert 2.0 <= result.divergence <= 3.5


def test_check_clip_in_sync(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    reference = rng.standard_normal(SR * 6).astype(np.float32)
    ref_path = tmp_path / "ref.wav"
    _write(ref_path, reference)
    clip_path = tmp_path / "clip.wav"
    _write(clip_path, reference[SR : SR * 5].copy())

    result = check_clip(clip_path, ref_path, song_t0=1.0, duration=4.0)
    assert result.in_sync


def test_summarise() -> None:
    results = [
        AvsyncResult("a", None, 4.0),
        AvsyncResult("b", 2.0, 5.0),
    ]
    text = summarise(results)
    assert "1/2 clips in sync" in text
