"""YOLO detections drawn over each shot (the surveillance motif).

For every shot with a background, a few frames are sampled, YOLO runs on them,
and the top detections (normalised to the frame) are stored on the shot. The
composition draws each one as a thin white box with a label, timed to its
sample. Results are cached per shot so a rebuild is cheap.

YOLO is imported lazily: the rest of the factory never depends on it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .blueprint import Blueprint
from .interfaces import CommandRunner
from .logging_setup import get_logger

log = get_logger("detect")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MODEL_NAME = "yolo11n.pt"
SAMPLE_STEP = 1.6  # seconds between sampled frames
MAX_PER_FRAME = 3
CONF = 0.35


def apply(blueprint: Blueprint, out_dir: Path, runner: CommandRunner) -> dict[str, list[dict]]:
    """Detect objects in every shot's background and store the boxes on the shot."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = {
        clip.clip: Path(clip.path)
        for clip in blueprint.seedance
        if clip.path and Path(clip.path).exists()
    }
    model = None
    done: dict[str, list[dict]] = {}
    for shot in blueprint.shots:
        source = Path(shot.media) if shot.media else clips.get(shot.seedance_clip or "")
        if source is None or not source.exists():
            continue
        cache = out_dir / f"{shot.id}.json"
        if cache.exists():
            boxes = json.loads(cache.read_text(encoding="utf-8"))
        else:
            model = model or _load_model(out_dir)
            boxes = detect_file(source, runner, model, out_dir / f"{shot.id}-frames")
            cache.write_text(json.dumps(boxes, indent=2), encoding="utf-8")
        shot.detections = boxes
        done[shot.id] = boxes
    if done:
        log.info("detected objects in %d shot(s)", len(done))
    return done


def _load_model(cache_dir: Path):  # pragma: no cover - heavy import
    import os

    os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(cache_dir) / "ultralytics"))
    from ultralytics import YOLO

    return YOLO(MODEL_NAME)


def sample_frames(source: Path, runner: CommandRunner, frames_dir: Path) -> list[float]:
    """Write sample frames to ``frames_dir`` and return their shot-local times."""
    frames_dir = Path(frames_dir)
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in IMAGE_SUFFIXES:
        shutil.copy2(source, frames_dir / "001.png")
        return [0.0]
    result = runner.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            f"fps=1/{SAMPLE_STEP}",
            str(frames_dir / "%03d.png"),
        ],
        timeout=60 * 10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"frame sampling failed: {(result.stderr or '')[:200]}")
    count = len(sorted(frames_dir.glob("*.png")))
    return [round(index * SAMPLE_STEP, 3) for index in range(count)]


def detect_file(source: Path, runner: CommandRunner, model, frames_dir: Path) -> list[dict]:  # noqa: ANN001 - model is an ultralytics YOLO
    """Run YOLO over sampled frames and return normalised boxes with times."""
    times = sample_frames(source, runner, frames_dir)
    images = [str(p) for p in sorted(Path(frames_dir).glob("*.png"))]
    if not images:
        return []
    results = model.predict(images, verbose=False, conf=CONF)
    boxes: list[dict] = []
    for time, result in zip(times, results, strict=False):
        height, width = result.orig_shape
        ranked = sorted(result.boxes, key=lambda box: float(box.conf), reverse=True)
        for det in ranked[:MAX_PER_FRAME]:
            x1, y1, x2, y2 = (float(value) for value in det.xyxy[0])
            boxes.append(
                {
                    "t": time,
                    "x": round(x1 / width * 100, 2),
                    "y": round(y1 / height * 100, 2),
                    "w": round((x2 - x1) / width * 100, 2),
                    "h": round((y2 - y1) / height * 100, 2),
                    "label": f"{model.names[int(det.cls)]} {float(det.conf):.2f}",
                }
            )
    return boxes
