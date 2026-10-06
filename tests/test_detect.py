"""Detection tests with a fake model and runner (no ultralytics, no inference)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from slopcore_factory.detect import detect_file


class FakeBox:
    def __init__(self, xyxy, cls, conf):  # noqa: ANN001
        self.xyxy = [xyxy]
        self.cls = cls
        self.conf = conf


class FakeResult:
    def __init__(self, boxes, shape):  # noqa: ANN001
        self.boxes = boxes
        self.orig_shape = shape


class FakeModel:
    names = {0: "person", 2: "car"}

    def __init__(self) -> None:
        self.calls = 0

    def predict(self, images, verbose=False, conf=0.35):  # noqa: ANN001
        self.calls += 1
        return [FakeResult([FakeBox([10, 20, 110, 220], 0, 0.9)], (480, 640)) for _ in images]


class FakeRunner:
    """Emulates ffmpeg writing N sampled frames."""

    def __init__(self, frame_count: int = 3) -> None:
        self.frame_count = frame_count

    def run(self, args, cwd=None, timeout=None):  # noqa: ANN001
        template = Path(args[-1])
        template.parent.mkdir(parents=True, exist_ok=True)
        for index in range(1, self.frame_count + 1):
            (template.parent / f"{index:03d}.png").write_bytes(b"x")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def test_detect_file_normalises_boxes(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    boxes = detect_file(source, FakeRunner(), FakeModel(), tmp_path / "frames")

    assert len(boxes) == 3  # one per sampled frame
    first = boxes[0]
    assert first["x"] == round(10 / 640 * 100, 2)
    assert first["label"] == "person 0.90"
    assert first["t"] == 0.0
    assert boxes[-1]["t"] == 3.2
