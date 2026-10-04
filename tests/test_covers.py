"""Cover planning from measured drift."""

from __future__ import annotations

from slopcore_factory.audio import find_gaps
from slopcore_factory.blueprint import Blueprint, SeedanceClip
from slopcore_factory.lipsync import add_covers, plan_windows
from slopcore_factory.models import Word


def _words(n: int, dur: float = 0.35, gap: float = 0.15) -> list[Word]:
    words: list[Word] = []
    t = 0.0
    for i in range(n):
        words.append(Word(f"w{i}", t, t + dur))
        t += dur + gap
    return words


def test_add_covers_appends_and_reestimates() -> None:
    words = _words(40)
    duration = words[-1].end + 1.0
    gaps = find_gaps(words, duration)
    windows = plan_windows(words, duration, gaps)

    blueprint = Blueprint(
        title="t",
        duration=duration,
        lipsync=list(windows),
        seedance=[SeedanceClip(w.clip, w.duration) for w in windows],
    )
    before = len(blueprint.seedance)

    drift = {windows[0].clip: windows[0].song_t0 + windows[0].duration / 2.0}
    covers = add_covers(blueprint, drift, words, gaps)

    assert covers
    assert covers[0].cover_of == windows[0].clip
    assert len(blueprint.seedance) == before + len(covers)
    assert blueprint.budgets.seedance_seconds > 0


def test_no_drift_adds_nothing() -> None:
    words = _words(20)
    duration = words[-1].end + 1.0
    gaps = find_gaps(words, duration)
    windows = plan_windows(words, duration, gaps)
    blueprint = Blueprint(title="t", duration=duration, lipsync=list(windows))
    assert add_covers(blueprint, {}, words, gaps) == []
