"""Blueprint -> render plan compiler tests."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.blueprint import Blueprint, Shot, ShotType
from slopcore_factory.compiler import blueprint_to_storyboard
from slopcore_factory.lyrics import parse_lyrics
from slopcore_factory.models import Cue


def _cues(doc, step: float = 2.0) -> list[Cue]:
    cues: list[Cue] = []
    t = 0.5
    for line in doc.lines:
        cues.append(Cue(line.text, t, t + 1.2, line.section, line.index))
        t += step
    return cues


def test_compiles_frames_from_shots(lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _cues(doc)
    blueprint = Blueprint(
        title="t",
        duration=20.0,
        shots=[
            Shot(
                id="s1",
                t0=0.0,
                t1=10.0,
                section="verse",
                type=[ShotType(0, "subtitle"), ShotType(1, "subtitle")],
            ),
            Shot(
                id="s2",
                t0=10.0,
                t1=20.0,
                section="chorus",
                type=[ShotType(2, "masthead")],
            ),
        ],
    )
    storyboard = blueprint_to_storyboard(blueprint, cues, doc)

    assert [frame.id for frame in storyboard.frames] == ["s1", "s2"]
    assert storyboard.duration == 20.0
    assert storyboard.frames[0].groups
    assert storyboard.frames[0].groups[0].cues[0].index == 0
    assert storyboard.accent_word == "continue"
    assert sum(frame.duration for frame in storyboard.frames) == 20.0


def test_group_ids_are_css_safe(lyrics_file: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _cues(doc)
    blueprint = Blueprint(
        title="t",
        duration=10.0,
        shots=[
            Shot(id="01-f1", t0=0.0, t1=10.0, type=[ShotType(0, "subtitle")]),
        ],
    )
    storyboard = blueprint_to_storyboard(blueprint, cues, doc)
    group_id = storyboard.frames[0].groups[0].id
    assert not group_id[0].isdigit()
    assert group_id.startswith("f1-g")


def test_compiles_background_from_clip(lyrics_file: Path, tmp_path: Path) -> None:
    from slopcore_factory.blueprint import SeedanceClip

    doc = parse_lyrics(lyrics_file)
    cues = _cues(doc)
    clip_file = tmp_path / "ls01.mp4"
    clip_file.write_bytes(b"x")
    blueprint = Blueprint(
        title="t",
        duration=10.0,
        shots=[
            Shot(
                id="s1",
                t0=0.0,
                t1=10.0,
                motion_tier="seedance",
                seedance_clip="ls01",
                type=[ShotType(0, "subtitle")],
            )
        ],
        seedance=[SeedanceClip("ls01", 5.0, path=str(clip_file))],
    )
    storyboard = blueprint_to_storyboard(blueprint, cues, doc)
    assert storyboard.frames[0].background == clip_file


def test_compiles_scene_from_animation(lyrics_file: Path) -> None:
    from slopcore_factory.blueprint import Animation

    doc = parse_lyrics(lyrics_file)
    cues = _cues(doc)
    blueprint = Blueprint(
        title="t",
        duration=10.0,
        shots=[
            Shot(
                id="s1",
                t0=0.0,
                t1=10.0,
                type=[ShotType(0, "subtitle")],
                animation=Animation(scene="bars"),
            )
        ],
    )
    storyboard = blueprint_to_storyboard(blueprint, cues, doc)
    scenes = storyboard.frames[0].scenes
    assert scenes and scenes[0].kind == "bars"
    assert not scenes[0].id[0].isdigit()


def test_fallback_background_is_used(lyrics_file: Path, tmp_path: Path) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _cues(doc)
    fallback = tmp_path / "bg.mp4"
    fallback.write_bytes(b"x")
    blueprint = Blueprint(
        title="t",
        duration=10.0,
        shots=[Shot(id="s1", t0=0.0, t1=10.0, type=[ShotType(0, "subtitle")])],
    )
    storyboard = blueprint_to_storyboard(blueprint, cues, doc, fallback_backgrounds=[fallback])
    assert storyboard.frames[0].background == fallback
