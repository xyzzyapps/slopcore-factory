"""Lyrics parsing tests."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.lyrics import extract_fence, extract_title, parse_lyrics


def test_parses_sections_and_lines(lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    assert doc.title == "TEST SONG"
    assert [s.name for s in doc.sections] == ["Intro", "Verse 1", "Chorus"]
    assert [line.text for line in doc.sections[0].lines] == ["Stay.", "Look at me."]
    assert len(doc.lines) == 8
    assert doc.lines[0].index == 0
    assert doc.lines[-1].index == 7


def test_hint_is_single_line(lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    assert "\n" not in doc.hint
    assert doc.hint.startswith("Stay. Look at me.")


def test_prose_and_prose_only_fence_ignored() -> None:
    assert extract_fence("hello ```\ninside\n``` end") == "inside\n"
    assert extract_title("# Real Title\n", "fallback") == "Real Title"
    assert extract_title("no headings", "fallback") == "fallback"


def test_section_name_drops_qualifier(lyrics_file: Path) -> None:
    text = "```\n[Intro - spoken, close]\nStay.\n```"
    path = lyrics_file.parent / "s2.md"
    path.write_text(text, encoding="utf-8")
    doc = parse_lyrics(path)
    assert doc.sections[0].name == "Intro"
