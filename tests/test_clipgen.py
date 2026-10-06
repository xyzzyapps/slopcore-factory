"""Clip generation against a mock provider (no spend)."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.blueprint import Blueprint, SeedanceClip
from slopcore_factory.clipgen import (
    SuppliedClipProvider,
    clip_payload,
    generate_seedance_clips,
    reference_images,
)


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


def test_reference_images_sorted_and_capped(tmp_path: Path) -> None:
    ref_dir = tmp_path / "song" / "assets" / "ref"
    ref_dir.mkdir(parents=True)
    for name in (
        "07-g.png",
        "03-c.png",
        "01-a.jpg",
        "05-e.png",
        "02-b.png",
        "06-f.png",
        "04-d.png",
        "notes.txt",
    ):
        (ref_dir / name).write_bytes(b"x")

    refs = reference_images(tmp_path / "song")
    assert [p.name for p in refs] == [
        "01-a.jpg",
        "02-b.png",
        "03-c.png",
        "04-d.png",
        "05-e.png",
        "06-f.png",
    ]


def test_reference_images_missing_dir(tmp_path: Path) -> None:
    assert reference_images(tmp_path / "nope") == []


def test_clip_payload_includes_references() -> None:
    entry = SeedanceClip("c01", 7.2, prompt="slow push-in")
    payload = clip_payload(entry, model="m", quality="480p", aspect="16:9", image_urls=["u1", "u2"])

    assert payload["duration"] == 7
    assert payload["quality"] == "480p"
    assert payload["image_urls"] == ["u1", "u2"]
    assert payload["generate_audio"] is False


def test_clip_payload_without_references() -> None:
    payload = clip_payload(SeedanceClip("c01", 6.0), model="m", quality="480p", aspect="16:9")
    assert "image_urls" not in payload


def test_clip_payload_skips_references_when_disabled() -> None:
    entry = SeedanceClip("c14b", 6.0, prompt="a figure in a scramble suit", use_reference=False)
    payload = clip_payload(entry, model="m", quality="480p", aspect="16:9", image_urls=["u1"])
    assert "image_urls" not in payload


def test_generate_seedance_clips_reuses_existing_files(tmp_path: Path) -> None:
    blueprint = Blueprint(
        title="t",
        duration=20.0,
        seedance=[SeedanceClip("c01", 6.0), SeedanceClip("c02", 6.0)],
    )
    out = tmp_path / "clips"
    out.mkdir()
    (out / "c01.mp4").write_bytes(b"done")

    provider = MockProvider()
    paths = generate_seedance_clips(blueprint, provider, out)

    assert set(paths) == {"c01", "c02"}
    assert provider.calls == ["c02"]  # c01 was reused, not regenerated
    assert blueprint.seedance[0].path.endswith("c01.mp4")
