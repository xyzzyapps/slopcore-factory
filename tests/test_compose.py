"""Compose tests: the generated project has the structure HyperFrames expects."""

from __future__ import annotations

import re
from pathlib import Path

from slopcore_factory.compose import compose_project
from slopcore_factory.lyrics import parse_lyrics
from slopcore_factory.models import Cue, FactorySpec, Transcript
from slopcore_factory.storyboard import plan_storyboard
from slopcore_factory.theme import load_theme


def _cues(doc, step: float = 2.0) -> list[Cue]:
    cues: list[Cue] = []
    t = 0.5
    for line in doc.lines:
        cues.append(Cue(line.text, t, t + 1.2, line.section, line.index))
        t += step
    return cues


def test_compose_writes_a_valid_project(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path, fake_clip: Path, fake_runner
) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _cues(doc)
    duration = cues[-1].end + 3.0
    spec = FactorySpec(
        song_id="test",
        title="TEST SONG",
        lyrics_path=lyrics_file,
        out_dir=tmp_path / "project",
        audio_path=fake_audio,
        backgrounds=[fake_clip],
        split_target=6.0,
        split_min=3.0,
        split_max=9.0,
    )
    storyboard = plan_storyboard(spec, doc, cues, duration, [fake_clip])
    manifest = compose_project(
        spec,
        storyboard,
        load_theme("broadside"),
        Transcript("fake", duration, []),
        fake_runner,
    )

    project = Path(manifest["project"])
    index = (project / "index.html").read_text(encoding="utf-8")
    assert 'data-composition-src="compositions/frames/01-f1.html"' in index
    assert 'src="assets/bgm.mp3"' in index
    assert f'data-duration="{duration:.3f}"' in index
    assert manifest["clips"] == ["assets/clips/clip1.mp4"]

    frame_html = (project / "compositions" / "frames" / "01-f1.html").read_text(encoding="utf-8")
    assert 'window.__timelines["01-f1"]' in frame_html
    assert 'class="clip media"' in frame_html
    assert 'class="grain"' in frame_html

    # the hook word ("continue") is highlighted somewhere across the frames
    frames_dir = project / "compositions" / "frames"
    frame_text = "\n".join(p.read_text(encoding="utf-8") for p in frames_dir.glob("*.html"))
    assert '<span class="accent">continue</span>' in frame_text

    # media tiles cover the frame span
    frame_duration = float(re.search(r'data-duration="([\d.]+)"', frame_html).group(1))
    media_durations = [
        float(value)
        for value in re.findall(
            r'<video class="clip media".*?data-duration="([\d.]+)"', frame_html, re.DOTALL
        )
    ]
    assert media_durations, "expected at least one media tile"
    assert abs(sum(media_durations) - frame_duration) < 0.25


def test_compose_writes_metadata(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path, fake_runner
) -> None:
    doc = parse_lyrics(lyrics_file)
    cues = _cues(doc)
    duration = cues[-1].end + 2.0
    spec = FactorySpec(
        song_id="test",
        title="TEST SONG",
        lyrics_path=lyrics_file,
        out_dir=tmp_path / "project",
        audio_path=fake_audio,
    )
    storyboard = plan_storyboard(spec, doc, cues, duration)
    compose_project(
        spec,
        storyboard,
        load_theme("broadside"),
        Transcript("fake", duration, []),
        fake_runner,
    )
    project = tmp_path / "project"
    for name in [
        "meta.json",
        "hyperframes.json",
        "package.json",
        "build.json",
        "transcript.json",
    ]:
        assert (project / name).exists(), f"missing {name}"


def test_compose_writes_scenes(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path, fake_runner
) -> None:
    from slopcore_factory.models import Frame, Scene, Storyboard

    frame = Frame(
        id="f1",
        index=1,
        start=0.0,
        duration=10.0,
        scenes=[Scene(id="f1-scene", kind="bars", t0=0.0, t1=10.0)],
        kicker="no. 01",
    )
    storyboard = Storyboard(
        composition_id="main",
        title="t",
        duration=10.0,
        width=1280,
        height=720,
        fps=30,
        frames=[frame],
        accent_word="continue",
    )
    spec = FactorySpec(
        song_id="t",
        title="t",
        lyrics_path=lyrics_file,
        out_dir=tmp_path / "p",
        audio_path=fake_audio,
    )
    compose_project(
        spec, storyboard, load_theme("broadside"), Transcript("fake", 10.0, []), fake_runner
    )
    frame_html = (tmp_path / "p" / "compositions" / "frames" / "f1.html").read_text(
        encoding="utf-8"
    )
    assert "scene-bars" in frame_html
    assert "#f1-scene .bar" in frame_html  # the emitted tween target
    assert "scaleY" in frame_html
    assert (tmp_path / "p" / "scenes" / "registry.json").exists()


def test_overlay_is_text_only(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path, fake_clip: Path, fake_runner
) -> None:
    from slopcore_factory.models import Frame, Group, Scene, Storyboard

    frame = Frame(
        id="f1",
        index=1,
        start=0.0,
        duration=10.0,
        groups=[
            Group(
                id="f1-g1",
                kind="lyric_stack",
                start=0.0,
                duration=10.0,
                cues=[Cue("hold on", 0.5, 2.0, "verse", 0, position="bottom")],
                kicker="SH01",
            )
        ],
        scenes=[
            Scene(id="f1-scene", kind="bars", t0=0.0, t1=10.0),
            Scene(id="f1-yolo", kind="yolo", t0=0.0, t1=10.0, params={"boxes": []}),
        ],
        background=fake_clip,
        kicker="SH01",
    )
    storyboard = Storyboard(
        composition_id="main",
        title="t",
        duration=10.0,
        width=1280,
        height=720,
        fps=30,
        frames=[frame],
        accent_word="continue",
    )
    spec = FactorySpec(
        song_id="t",
        title="t",
        lyrics_path=lyrics_file,
        out_dir=tmp_path / "ov",
        audio_path=fake_audio,
    )
    compose_project(
        spec,
        storyboard,
        load_theme("broadside"),
        Transcript("fake", 10.0, []),
        fake_runner,
        overlay=True,
    )
    frame_html = (tmp_path / "ov" / "compositions" / "frames" / "f1.html").read_text(
        encoding="utf-8"
    )
    index_html = (tmp_path / "ov" / "index.html").read_text(encoding="utf-8")
    # no scenes (bars/yolo), no media, no kicker, transparent background, no audio
    assert 'class="scene scene-bars"' not in frame_html
    assert 'class="scene scene-yolo"' not in frame_html
    assert 'class="clip media"' not in frame_html
    assert '<div class="kick">' not in frame_html
    assert "background: transparent" in frame_html
    assert "<audio" not in index_html
    # the per-line position override still applies in an overlay
    assert "pos-bottom" in frame_html
