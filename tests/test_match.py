"""Render -> clip matching tests (no real video needed)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from slopcore_factory.match import Segment, candidate_clips, scene_cuts, to_otio


class FakeRunner:
    """Answers ffmpeg with a canned stderr (the scene metadata)."""

    def __init__(self, stderr: str = "") -> None:
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def run(self, args, cwd=None, timeout=None):  # noqa: ANN001
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr=self.stderr)


def test_scene_cuts_parses_and_merges(tmp_path: Path) -> None:
    stderr = (
        "[Parsed_metadata_1 @ 0x0] frame:0 pts:0 pts_time:12.2333\n"
        "[Parsed_metadata_1 @ 0x0] frame:1 pts:0 pts_time:16.9333\n"
        "[Parsed_metadata_1 @ 0x0] frame:2 pts:0 pts_time:124.433\n"
        "[Parsed_metadata_1 @ 0x0] frame:3 pts:0 pts_time:124.5\n"
    )
    cuts = scene_cuts(tmp_path / "v.mp4", FakeRunner(stderr))
    assert cuts == [12.2333, 16.9333, 124.433]  # the 0.067 s double merges


def test_candidate_clips_skips_composer_copies(tmp_path: Path) -> None:
    for name in ["c01.mp4", "ls1.mp4", "clip1.mp4", "clip17.jpg", "notes.txt"]:
        (tmp_path / name).write_bytes(b"x")
    candidates = candidate_clips(tmp_path)
    assert "c01" in candidates
    assert "ls1" in candidates
    assert "clip1" not in candidates  # a renumbered video copy
    assert "clip17.jpg" in candidates  # a still copy is a real source
    assert len(candidates) == 3


def test_to_otio_builds_tracks_and_retimes(tmp_path: Path) -> None:
    source = tmp_path / "c01.mp4"
    source.write_bytes(b"x")
    segments = [
        Segment(1, 0.0, 12.0, "c01", str(source), 0.9, 0.7, source_seconds=6.0, speed=0.5),
        Segment(2, 12.0, 16.0, "c01", str(source), 0.9, 0.7, source_seconds=6.0, speed=1.0),
    ]
    timeline = to_otio(segments, fps=30, song=tmp_path / "bgm.mp3", name="t")
    tracks = timeline["tracks"]["children"]
    v1 = tracks[0]["children"]
    assert len(v1) == 2
    assert v1[0]["effects"][0]["time_scalar"] == 0.5  # 6 s source in a 12 s slot
    assert "effects" not in v1[1]  # 4 s slot, 6 s source -> trimmed, no retime
    assert [t["name"] for t in tracks] == ["V1 CLIPS", "A1 SONG"]
    assert tracks[1]["kind"] == "Audio"
    assert timeline["metadata"]["slopcore"]["segments"] == 2
