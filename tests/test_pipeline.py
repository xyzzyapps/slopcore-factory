"""End-to-end pipeline tests using fakes (no network, no browser, no spend)."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FakeRenderer, FakeRunner, FakeTranscriber

from slopcore_factory.blueprint import Blueprint, SeedanceClip, Shot, ShotType, save_blueprint
from slopcore_factory.config import build_spec
from slopcore_factory.errors import SlopcoreFactoryError
from slopcore_factory.locator import ServiceLocator
from slopcore_factory.pipeline import Pipeline
from slopcore_factory.song import SuppliedSongProvider
from slopcore_factory.timing import LineAligner


def _services(runner, transcriber, renderer) -> ServiceLocator:
    services = ServiceLocator()
    services.register_instance("runner", runner)
    services.register_instance("aligner", LineAligner())
    services.register_instance("transcriber", transcriber)
    services.register_instance("song_provider", SuppliedSongProvider())
    services.register_instance("renderer", renderer)
    return services


def test_pipeline_runs_through_check(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path, fake_clip: Path
) -> None:
    spec = build_spec(
        lyrics_file, tmp_path / "project", audio_path=fake_audio, backgrounds=[fake_clip]
    )
    renderer = FakeRenderer()
    pipeline = Pipeline(
        spec, _services(FakeRunner(), FakeTranscriber(), renderer), tmp_path / "work"
    )
    results = pipeline.run(until="check", skip={"snapshot"})

    assert not pipeline.failed(), [(r.stage, r.status, r.detail) for r in results]
    statuses = {r.stage: r.status for r in results}
    assert statuses["song"] == "DONE"
    assert statuses["align"] == "DONE"
    assert statuses["build"] == "DONE"
    assert statuses["check"] == "DONE"
    assert (tmp_path / "project" / "index.html").exists()
    assert renderer.checked


def test_pipeline_renders(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path, fake_clip: Path
) -> None:
    spec = build_spec(
        lyrics_file, tmp_path / "project", audio_path=fake_audio, backgrounds=[fake_clip]
    )
    pipeline = Pipeline(
        spec, _services(FakeRunner(), FakeTranscriber(), FakeRenderer()), tmp_path / "work"
    )
    results = pipeline.run(until="render", skip={"snapshot"})

    assert not pipeline.failed(), [(r.stage, r.status, r.detail) for r in results]
    out = tmp_path / "renders" / f"{spec.out_dir.name}.mp4"
    assert out.exists()


def test_pipeline_fails_when_check_fails(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path, fake_clip: Path
) -> None:
    spec = build_spec(
        lyrics_file, tmp_path / "project", audio_path=fake_audio, backgrounds=[fake_clip]
    )
    renderer = FakeRenderer(check_code=1, check_output="2 error(s), 0 warning(s)\nCheck failed\n")
    renderer.parse_check = staticmethod(lambda _o: {"errors": 2, "warnings": 0, "passed": False})
    pipeline = Pipeline(
        spec, _services(FakeRunner(), FakeTranscriber(), renderer), tmp_path / "work"
    )
    results = pipeline.run(until="check", skip={"snapshot"})
    assert pipeline.failed()
    assert any(r.stage == "check" and r.status == "FAILED" for r in results)


def test_resume_uses_cache(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path, fake_clip: Path
) -> None:
    spec = build_spec(
        lyrics_file, tmp_path / "project", audio_path=fake_audio, backgrounds=[fake_clip]
    )
    transcriber = FakeTranscriber()
    pipeline = Pipeline(
        spec, _services(FakeRunner(), transcriber, FakeRenderer()), tmp_path / "work"
    )
    pipeline.run(until="align", skip={"snapshot"})

    # a second pipeline with a transcriber that would raise proves the cache is used
    class Boom:
        def transcribe(self, *args, **kwargs):
            raise AssertionError("transcriber should not run; cache should be fresh")

    second = Pipeline(spec, _services(FakeRunner(), Boom(), FakeRenderer()), tmp_path / "work")
    results = second.run(until="align", skip={"snapshot"})
    assert not second.failed(), [(r.stage, r.status, r.detail) for r in results]
    assert any(r.stage == "align" and r.detail == "cached" for r in results)


class FakeClipGenerator:
    """Stands in for the paid Seedance provider."""

    def generate(self, entry, out_dir):  # noqa: ANN001
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{entry.clip}.mp4"
        path.write_bytes(b"clip")
        return path


def test_media_generate_clips_uses_blueprint(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path
) -> None:
    spec = build_spec(lyrics_file, tmp_path / "project", audio_path=fake_audio)
    spec.generate_clips = True
    work = tmp_path / "work"
    work.mkdir()
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
        seedance=[SeedanceClip("ls01", 5.0)],
    )
    save_blueprint(blueprint, work / "blueprint.yaml")

    services = ServiceLocator()
    services.register_instance("runner", FakeRunner())
    services.register_instance("clip_generator", FakeClipGenerator())
    pipeline = Pipeline(spec, services, work)

    result = pipeline._do_media(force=True)
    assert result.status == "DONE"
    assert pipeline.backgrounds and pipeline.backgrounds[0].exists()


def test_media_generate_clips_needs_blueprint(
    tmp_path: Path, lyrics_file: Path, fake_audio: Path
) -> None:
    spec = build_spec(lyrics_file, tmp_path / "project", audio_path=fake_audio)
    spec.generate_clips = True
    services = ServiceLocator()
    services.register_instance("runner", FakeRunner())
    services.register_instance("clip_generator", FakeClipGenerator())
    pipeline = Pipeline(spec, services, tmp_path / "work")

    with pytest.raises(SlopcoreFactoryError):
        pipeline._do_media(force=True)
