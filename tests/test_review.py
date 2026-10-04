"""Review loop: sample times from shots and a written report."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.blueprint import Blueprint, Shot, ShotType, save_blueprint
from slopcore_factory.config import build_spec
from slopcore_factory.locator import ServiceLocator
from slopcore_factory.workflows import review


class FakeRenderer:
    def __init__(self) -> None:
        self.times: list[float] = []

    def snapshot(self, project, times):  # noqa: ANN001
        self.times = list(times)
        return []


def test_review_samples_shot_midpoints(tmp_path: Path, lyrics_file: Path) -> None:
    spec = build_spec(lyrics_file, tmp_path / "project")
    work = tmp_path / "work"
    work.mkdir()
    blueprint = Blueprint(
        title="t",
        duration=20.0,
        shots=[
            Shot(id="s1", t0=0.0, t1=10.0, type=[ShotType(0, "subtitle")]),
            Shot(id="s2", t0=10.0, t1=20.0),
        ],
    )
    save_blueprint(blueprint, work / "blueprint.yaml")

    renderer = FakeRenderer()
    services = ServiceLocator()
    services.register_instance("renderer", renderer)

    times, _paths, report = review(spec, work, services)

    assert times == [5.0, 15.0]
    assert renderer.times == [5.0, 15.0]
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "s1" in text and "s2" in text
