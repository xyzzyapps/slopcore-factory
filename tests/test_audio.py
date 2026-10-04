"""Audio analysis tests: gaps and persistence."""

from __future__ import annotations

from slopcore_factory.audio import AudioAnalysis, Gap, find_gaps, gap_at, last_gap_before, next_gap
from slopcore_factory.models import Word


def _word(start: float, end: float) -> Word:
    return Word("x", start, end)


def test_find_gaps_head_gap_tail() -> None:
    words = [_word(0.5, 0.9), _word(1.0, 1.4), _word(2.5, 3.0)]
    gaps = find_gaps(words, duration=4.0)
    assert [round(g.start, 2) for g in gaps] == [0.0, 1.4, 3.0]
    assert round(gaps[0].duration, 2) == 0.5


def test_gap_helpers() -> None:
    gaps = [Gap(1.0, 2.0), Gap(5.0, 6.0)]
    assert gap_at(1.5, gaps) is not None
    assert gap_at(3.0, gaps) is None
    assert next_gap(0.0, gaps).start == 1.0  # type: ignore[union-attr]
    assert last_gap_before(5.5, gaps).start == 5.0  # type: ignore[union-attr]
    assert last_gap_before(0.5, gaps) is None


def test_analysis_round_trip() -> None:
    analysis = AudioAnalysis(
        duration=10.0, word_count=3, gaps=[Gap(1.0, 2.0)], stem="x", has_stem=True
    )
    restored = AudioAnalysis.from_dict(analysis.to_dict())
    assert restored.word_count == 3
    assert restored.has_stem is True
    assert restored.gaps[0].duration == 1.0
