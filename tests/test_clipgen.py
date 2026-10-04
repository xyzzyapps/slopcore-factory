"""Clip generation against a mock provider (no spend)."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.blueprint import Blueprint, SeedanceClip
from slopcore_factory.clipgen import SuppliedClipProvider, generate_seedance_clips


class MockProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, entry: SeedanceClip, out_dir: Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{entry.clip}.mp4"
        path.write_bytes(b"mock")
        self.calls.append(entry.clip)
        return path


def test_generate_seedance_clips_records_paths(tmp_path: Path) -> None:
    blueprint = Blueprint(
        title="t",
        duration=20.0,
        seedance=[SeedanceClip("ls01", 5.0), SeedanceClip("ls02", 6.0)],
    )
    provider = MockProvider()
    paths = generate_seedance_clips(blueprint, provider, tmp_path / "clips")

    assert set(paths) == {"ls01", "ls02"}
    assert provider.calls == ["ls01", "ls02"]
    assert blueprint.seedance[0].path.endswith("ls01.mp4")
    assert paths["ls01"].exists()


def test_supplied_clip_provider(tmp_path: Path) -> None:
    song = tmp_path / "song"
    clips = song / "assets" / "clips"
    clips.mkdir(parents=True)
    supplied = clips / "ls01.mp4"
    supplied.write_bytes(b"x")

    provider = SuppliedClipProvider(song)
    assert provider.generate(SeedanceClip("ls01", 4.0), tmp_path / "out") == supplied
    assert provider.generate(SeedanceClip("ls99", 4.0), tmp_path / "out") is None


def test_generate_seedance_clips_skips_missing(tmp_path: Path) -> None:
    blueprint = Blueprint(
        title="t",
        duration=10.0,
        seedance=[SeedanceClip("ls01", 5.0), SeedanceClip("ls99", 5.0)],
    )
    song = tmp_path / "song"
    (song / "assets" / "clips").mkdir(parents=True)
    (song / "assets" / "clips" / "ls01.mp4").write_bytes(b"x")

    paths = generate_seedance_clips(blueprint, SuppliedClipProvider(song), tmp_path / "out")
    assert set(paths) == {"ls01"}
