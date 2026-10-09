"""Storyboard markdown tests: the plan is strict, clean markdown and round-trips."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.blueprint import (
    Blueprint,
    Chapter,
    LipsyncWindow,
    SeedanceClip,
    Shot,
    ShotType,
)
from slopcore_factory.models import Cue
from slopcore_factory.storyboard_md import parse, plan_path, render, settings_of


def _blueprint() -> Blueprint:
    return Blueprint(
        title="All Yours",
        duration=10.0,
        lyrics_path="lyrics.md",
        audio="assets/bgm.mp3",
        chapters=[Chapter("ch-love", "love", 0.0, 10.0)],
        shots=[
            Shot(
                id="sh01",
                t0=0.0,
                t1=10.0,
                chapter="ch-love",
                section="verse",
                framing="medium",
                motion_tier="seedance",
                seedance_clip="c01",
                treatment="slow",
                treatment_value=2.5,
                chrome="no. 01",
                type=[ShotType(0, "subtitle", text="I'm all yours", position="lower", offset=3.0)],
            )
        ],
        seedance=[
            SeedanceClip(
                "c01",
                6.04,
                prompt="a | pipe",
                sing=False,
                song_t0=1.5,
                cover_of="c00",
                plate="p2",
                words="la la",
                path="songs/x/c01.mp4",
            )
        ],
    )


def test_plan_is_strict_markdown() -> None:
    text = render(_blueprint())
    assert text.startswith("# All Yours")
    assert "&#" not in text  # no HTML entities
    assert "\n\n\n" not in text  # no blank-line noise
    assert "| canvas | 1280x720 |" in text
    shots_row = "| sh01 | 0.000 | 10.000 | ch-love | verse | medium | seedance | c01 | slow |"
    assert shots_row + " 2.5 |  |  |  | no. 01 |" in text
    assert "| c01 | no | 6.04 | 1.500 | songs/x/c01.mp4 | c00 | p2 | yes | la la |" in text
    assert "| 0 |  | I'm all yours | subtitle | lower | 3 |" in text


def test_plan_includes_cue_times_and_prompts() -> None:
    cues = [Cue("I'm all yours", 12.24, 16.0, "Chorus", 0)]
    text = render(_blueprint(), cues, song_style="trip-hop torch", dry_run=True)
    assert "| 0 | 12.240 | I'm all yours | subtitle | lower | 3 |" in text
    assert "trip-hop torch" in text
    assert "| dry_run | true |" in text
    # a pipe inside a prompt must not break the table
    assert "a \\| pipe" in text


def test_plan_path_is_beside_the_lyrics() -> None:
    assert plan_path(Path("songs/all-yours")) == Path("songs/all-yours/storyboard.md")


def test_parse_round_trips_the_plan() -> None:
    blueprint = _blueprint()
    text = render(
        blueprint, [Cue("I'm all yours", 0.5, 2.0, "Chorus", 0)], song_style="s", dry_run=True
    )
    parsed, cues = parse(text)
    assert parsed.title == blueprint.title
    assert parsed.duration == blueprint.duration
    assert parsed.width == blueprint.width
    assert parsed.theme == blueprint.theme
    assert [s.id for s in parsed.shots] == ["sh01"]
    assert parsed.shots[0].seedance_clip == "c01"
    assert parsed.shots[0].treatment == "slow"
    assert parsed.shots[0].treatment_value == 2.5  # the `value` column round-trips
    assert parsed.shots[0].chrome == "no. 01"
    assert parsed.shots[0].section == "verse"
    assert parsed.shots[0].type[0].offset == 3.0
    clip = parsed.seedance[0]
    assert clip.prompt == "a | pipe"  # the escaped pipe round-trips
    assert clip.song_t0 == 1.5
    assert clip.path == "songs/x/c01.mp4"
    assert clip.cover_of == "c00"
    assert clip.plate == "p2"
    assert clip.words == "la la"
    assert [cue.index for cue in cues] == [0]
    assert cues[0].start == 0.5
    # the section is not in the markdown; it is recovered from lyrics.md at load time
    assert cues[0].section == ""


def test_clip_start_falls_back_to_the_lipsync_row() -> None:
    blueprint = _blueprint()
    blueprint.seedance[0].song_t0 = 0.0
    blueprint.lipsync = [LipsyncWindow(clip="c01", song_t0=42.0, duration=6.0, words="x")]
    parsed, _cues = parse(render(blueprint))
    assert parsed.seedance[0].song_t0 == 42.0  # inherited from the lipsync window


def test_settings_of_reads_the_settings_table() -> None:
    settings = settings_of(render(_blueprint(), dry_run=True))
    assert settings["canvas"] == "1280x720"
    assert settings["dry_run"] == "true"


def test_save_plan_writes_the_markdown_when_it_exists(tmp_path: Path) -> None:
    from slopcore_factory.storyboard_md import save_plan

    song = tmp_path / "song"
    song.mkdir()
    (song / "storyboard.md").write_text(render(_blueprint()), encoding="utf-8")
    blueprint = _blueprint()
    blueprint.title = "Edited"
    path = save_plan(blueprint, song, tmp_path / "work")
    assert path == song / "storyboard.md"
    assert "Edited" in path.read_text(encoding="utf-8")


def test_save_plan_falls_back_to_the_blueprint(tmp_path: Path) -> None:
    from slopcore_factory.storyboard_md import save_plan

    path = save_plan(_blueprint(), tmp_path / "song", tmp_path / "work")
    assert path == tmp_path / "work" / "blueprint.yaml"
    assert path.exists()


def test_apply_settings_applies_canvas_and_duration(lyrics_file: Path, tmp_path: Path) -> None:
    from slopcore_factory.config import build_spec
    from slopcore_factory.storyboard_md import apply_settings

    spec = build_spec(lyrics_file, tmp_path / "project")
    apply_settings(spec, {"canvas": "1920x1080", "fps": "24", "duration": "123.0"})
    assert (spec.width, spec.height) == (1920, 1080)
    assert spec.fps == 24
    assert spec.duration == 123.0
