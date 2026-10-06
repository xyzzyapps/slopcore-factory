"""Storyboard markdown tests: the plan is strict, clean markdown."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.blueprint import Blueprint, Chapter, SeedanceClip, Shot, ShotType
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
                framing="medium",
                motion_tier="seedance",
                seedance_clip="c01",
                treatment="slow",
                type=[ShotType(0, "subtitle", text="I'm all yours", position="lower", offset=3.0)],
            )
        ],
        seedance=[SeedanceClip("c01", 6.04, prompt="a | pipe", sing=False)],
    )


def test_plan_is_strict_markdown() -> None:
    text = render(_blueprint())
    assert text.startswith("# All Yours")
    assert "&#" not in text  # no HTML entities
    assert "\n\n\n" not in text  # no blank-line noise
    assert "| canvas | 1280x720 |" in text
    assert "| sh01 | 0.000 | 10.000 | ch-love | medium | seedance | c01 | slow |  |  |" in text
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
    assert parsed.shots[0].type[0].offset == 3.0
    assert parsed.seedance[0].prompt == "a | pipe"  # the escaped pipe round-trips
    assert [cue.index for cue in cues] == [0]
    assert cues[0].start == 0.5
    # the section is not in the markdown; it is recovered from lyrics.md at load time
    assert cues[0].section == ""


def test_settings_of_reads_the_settings_table() -> None:
    settings = settings_of(render(_blueprint(), dry_run=True))
    assert settings["canvas"] == "1280x720"
    assert settings["dry_run"] == "true"
