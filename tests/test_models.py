"""Model tests."""

from __future__ import annotations

from slopcore_factory.models import LyricLine, LyricsDoc, LyricSection


def test_line_word_count() -> None:
    assert LyricLine("a b c", "Verse", 0).word_count == 3


def test_doc_flattens_lines() -> None:
    doc = LyricsDoc(
        title="t",
        sections=[
            LyricSection("A", [LyricLine("one", "A", 0)]),
            LyricSection("B", [LyricLine("two", "B", 1), LyricLine("three", "B", 2)]),
        ],
    )
    assert [line.text for line in doc.lines] == ["one", "two", "three"]
    assert doc.text == "one\ntwo\nthree"
    assert doc.hint == "one two three"
