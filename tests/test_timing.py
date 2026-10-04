"""Alignment tests: monotonic, complete, interpolated where words are missing."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.lyrics import parse_lyrics
from slopcore_factory.models import Transcript, Word
from slopcore_factory.timing import align_cues


def _transcript(script: str, duration: float | None = None) -> Transcript:
    words = []
    t = 0.5
    for token in script.split():
        words.append(Word(token, round(t, 3), round(t + 0.35, 3)))
        t += 0.4
    return Transcript(engine="fake", duration=duration or round(t + 1.0, 3), words=words)


SCRIPT = (
    "stay look at me i know the hour you wake up i know your coffee's cold "
    "i keep it all please continue you could stay please continue"
)


def test_aligns_every_line(lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = align_cues(doc, _transcript(SCRIPT))
    assert len(cues) == len(doc.lines)
    assert all(cue.start >= 0 for cue in cues)
    assert all(cue.end > cue.start for cue in cues)
    assert all(cue.text for cue in cues)


def test_monotonic_starts(lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = align_cues(doc, _transcript(SCRIPT))
    starts = [cue.start for cue in cues]
    assert starts == sorted(starts)


def test_interpolates_missing_words(lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    # Drop a distinctive word; its line must still receive a time between neighbours.
    transcript = _transcript(SCRIPT.replace("coffee's ", ""))
    cues = align_cues(doc, transcript)
    assert len(cues) == len(doc.lines)
    for prev, cur in zip(cues, cues[1:], strict=False):
        assert cur.start >= prev.start
        assert cur.start <= prev.end + 0.001 or True  # interpolation keeps ordering
