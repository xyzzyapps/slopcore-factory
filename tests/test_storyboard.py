"""Storyboard planner tests."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.lyrics import parse_lyrics
from slopcore_factory.models import Cue, FactorySpec
from slopcore_factory.storyboard import plan_storyboard


def _make_cues(doc, step: float = 2.0) -> list[Cue]:
    cues: list[Cue] = []
    t = 0.5
    for line in doc.lines:
        cues.append(Cue(line.text, t, t + 1.2, line.section, line.index))
        t += step
    return cues


def _spec(tmp_path: Path, lyrics_file: Path, background: Path | None = None) -> FactorySpec:
    return FactorySpec(
        song_id="test",
        title="TEST SONG",
        lyrics_path=lyrics_file,
        out_dir=tmp_path / "project",
        backgrounds=[background] if background else [],
        split_target=5.0,
        split_min=3.0,
        split_max=8.0,
    )


def test_frames_cover_the_whole_song(tmp_path: Path, lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _make_cues(doc)
    duration = cues[-1].end + 3.0
    sb = plan_storyboard(_spec(tmp_path, lyrics_file), doc, cues, duration)
    assert sb.frames[0].start == 0.0
    assert abs(sum(frame.duration for frame in sb.frames) - duration) < 0.01


def test_frames_are_contiguous(tmp_path: Path, lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _make_cues(doc)
    sb = plan_storyboard(_spec(tmp_path, lyrics_file), doc, cues, cues[-1].end + 2.0)
    for a, b in zip(sb.frames, sb.frames[1:], strict=False):
        assert abs((a.start + a.duration) - b.start) < 0.01


def test_groups_stay_inside_their_frame(tmp_path: Path, lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _make_cues(doc)
    sb = plan_storyboard(_spec(tmp_path, lyrics_file), doc, cues, cues[-1].end + 2.0)
    for frame in sb.frames:
        assert frame.groups
        for group in frame.groups:
            assert group.start >= frame.start - 0.001
            assert group.start + group.duration <= frame.start + frame.duration + 0.001


def test_accent_word_is_the_hook(tmp_path: Path, lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _make_cues(doc)
    sb = plan_storyboard(_spec(tmp_path, lyrics_file), doc, cues, cues[-1].end + 2.0)
    assert sb.accent_word == "continue"


def test_intro_becomes_held_message(tmp_path: Path, lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _make_cues(doc)
    sb = plan_storyboard(_spec(tmp_path, lyrics_file), doc, cues, cues[-1].end + 2.0)
    first = sb.frames[0]
    assert any(group.kind == "held_message" for group in first.groups)


def test_no_frame_exceeds_max(tmp_path: Path, lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    # one long section -> a single run that must be split into frames
    cues = [Cue(f"line {i}", 0.5 + i * 2.0, 1.5 + i * 2.0, "Verse 1", i) for i in range(40)]
    sb = plan_storyboard(_spec(tmp_path, lyrics_file), doc, cues, cues[-1].end + 2.0)
    assert len(sb.frames) > 1
    # frames are cut at cue boundaries, so they may overshoot the soft maximum
    # by up to one cue gap (2 s in this fixture)
    for frame in sb.frames:
        assert frame.duration <= 8.0 + 2.0 + 0.01


def test_backgrounds_cycle(tmp_path: Path, lyrics_file: Path, fake_clip: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _make_cues(doc)
    sb = plan_storyboard(
        _spec(tmp_path, lyrics_file, fake_clip), doc, cues, cues[-1].end + 2.0, [fake_clip]
    )
    assert all(frame.background == fake_clip for frame in sb.frames)
