"""Lipsync planning and drift-detection tests (no audio files, no spend)."""

from __future__ import annotations

import numpy as np

from slopcore_factory.audio import find_gaps
from slopcore_factory.blueprint import Character
from slopcore_factory.lipsync import (
    attach_to_blueprint,
    detect_divergence,
    plan_clips,
    plan_cover,
    plan_windows,
)
from slopcore_factory.models import Word


def _words(n: int, dur: float = 0.35, gap: float = 0.15) -> list[Word]:
    words: list[Word] = []
    t = 0.0
    for i in range(n):
        words.append(Word(f"w{i}", t, t + dur))
        t += dur + gap
    return words


def test_windows_start_in_gap_and_quote_words() -> None:
    words = _words(40)
    duration = words[-1].end + 1.0
    gaps = find_gaps(words, duration)
    windows = plan_windows(words, duration, gaps, clip_min=4.0, clip_max=8.0)

    assert windows
    for window in windows:
        in_gap = any(g.start - 1e-6 <= window.song_t0 <= g.end + 1e-6 for g in gaps)
        assert in_gap
        assert window.song_t0 + window.duration <= duration + 0.01
        inside = [
            w.word
            for w in words
            if w.start >= window.song_t0 - 1e-6 and w.end <= window.song_t0 + window.duration + 1e-6
        ]
        assert window.words == " ".join(inside)
        assert window.duration <= 8.0 + 0.01

    assert sum(w.duration for w in windows) > 10.0


def test_plan_clips_are_audio_conditioned() -> None:
    words = _words(30)
    duration = words[-1].end + 1.0
    gaps = find_gaps(words, duration)
    windows = plan_windows(words, duration, gaps)
    clips = plan_clips(windows, Character(canon="a woman in a black coat"), plate="hero")
    assert len(clips) == len(windows)
    assert all(clip.sing for clip in clips)
    assert "@Audio1" in clips[0].prompt
    assert clips[0].words == windows[0].words


def test_detect_divergence_finds_the_break() -> None:
    sr = 16000
    rng = np.random.default_rng(0)
    reference = rng.standard_normal(sr * 6).astype(np.float32)
    returned = reference.copy()
    cut = sr * 3
    returned[cut:] = rng.standard_normal(len(reference) - cut).astype(np.float32) * np.std(
        reference
    )

    point = detect_divergence(reference, returned, sr, threshold=0.6)
    assert point is not None
    # detection may lead the break by up to one correlation window (1 s),
    # which is the safe side: the edit cuts before the drift.
    assert 2.0 <= point <= 3.5


def test_detect_divergence_aligned_is_none() -> None:
    sr = 16000
    rng = np.random.default_rng(1)
    reference = rng.standard_normal(sr * 5).astype(np.float32)
    assert detect_divergence(reference, reference.copy(), sr) is None


def test_plan_cover_resumes_after_divergence() -> None:
    words = _words(24)
    duration = words[-1].end + 1.0
    gaps = find_gaps(words, duration)
    windows = plan_windows(words, duration, gaps)
    window = windows[0]
    cover = plan_cover(window, window.song_t0 + window.duration / 2.0, words, gaps)
    assert cover is not None
    assert cover.cover_of == window.clip
    assert cover.song_t0 > window.song_t0


def test_attach_to_blueprint_sets_tiers_and_budget() -> None:
    from slopcore_factory.blueprint import Blueprint, Shot

    words = _words(40)
    duration = words[-1].end + 1.0
    gaps = find_gaps(words, duration)
    windows = plan_windows(words, duration, gaps)

    blueprint = Blueprint(title="t", duration=duration, shots=[Shot(id="s1", t0=0.0, t1=duration)])
    attach_to_blueprint(blueprint, windows)
    assert blueprint.seedance
    assert blueprint.shots[0].motion_tier == "seedance"
    assert blueprint.budgets.seedance_seconds > 0
