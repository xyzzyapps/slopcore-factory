"""Animation scenes: arbitrary motion design layered into a frame.

A scene is a decorative layer inside a frame (bars pulsing on a fixed rhythm, a
slow marquee of words, drifting scan lines). Built-in scenes are pure functions
of time expressed as GSAP tweens, so they stay seek-safe and deterministic.

A scene may instead point at a user-authored ``module`` (an HTML fragment); the
factory copies it into the project's ``scenes/`` directory and inlines it. That
is the escape hatch for genuinely arbitrary animation: the file owns its own
markup and any CSS/JS, and is listed in the scene registry.
"""

from __future__ import annotations

import random
from pathlib import Path

from .logging_setup import get_logger
from .models import Frame, Scene

log = get_logger("scenes")

BUILTINS = {"bars", "marquee", "scan", "blocks", "yolo"}


def is_builtin(kind: str) -> bool:
    return kind in BUILTINS


def scene_data(scene: Scene, frame: Frame, accent_word: str | None = None) -> dict:
    """DOM + timeline data for one scene, with times made frame-local."""
    start = round(max(0.0, min(frame.duration, scene.t0 - frame.start)), 3)
    end = round(max(start, min(frame.duration, scene.t1 - frame.start)), 3)
    data: dict = {"id": scene.id, "kind": scene.kind, "events": []}

    if scene.kind == "bars":
        data["bars"] = int(scene.params.get("bars", 28))
        data["events"].append({"kind": "scene_bars", "target": f"#{scene.id} .bar", "at": start})
    elif scene.kind == "marquee":
        words = scene.params.get("words") or [accent_word or "please continue"]
        data["words"] = [str(word) for word in words]
        data["events"].append(
            {
                "kind": "scene_marquee",
                "target": f"#{scene.id} .track",
                "at": start,
                "duration": round(max(6.0, end - start), 3),
            }
        )
    elif scene.kind == "scan":
        data["events"].append({"kind": "scene_scan", "target": f"#{scene.id}", "at": start})
    elif scene.kind == "blocks":
        # sparse detection-style boxes: thin white borders, YOLO-ish
        rng = random.Random(scene.id)
        count = int(scene.params.get("count", 4))
        data["rects"] = [
            {
                "left": round(rng.uniform(6, 62), 2),
                "top": round(rng.uniform(8, 52), 2),
                "w": round(rng.uniform(12, 30), 2),
                "h": round(rng.uniform(18, 38), 2),
                "label": f"AI {rng.uniform(0.71, 0.98):.2f}",
            }
            for _ in range(count)
        ]
        data["events"].append({"kind": "scene_blocks", "target": f"#{scene.id} .box", "at": start})
    elif scene.kind == "yolo":
        boxes = scene.params.get("boxes") or []
        data["boxes"] = []
        for index, box in enumerate(boxes, start=1):
            at = round(max(start, min(end, start + float(box.get("t", 0.0)))), 3)
            hide = round(min(end, at + 1.7), 3)
            data["boxes"].append({"id": f"{scene.id}-b{index}", **box})
            data["events"].append(
                {
                    "kind": "scene_yolo_box",
                    "target": f"#{scene.id}-b{index}",
                    "at": at,
                    "hide_at": hide,
                }
            )
    elif scene.kind == "custom":
        data["markup"] = scene.markup
    return data


def load_custom_markup(scene: Scene, song_dir: Path) -> str:
    """Read a user-authored scene fragment, or ``""`` when it is missing."""
    if not scene.module:
        return ""
    path = Path(song_dir) / scene.module
    if not path.exists():
        log.warning("custom scene not found: %s", path)
        return ""
    return path.read_text(encoding="utf-8")


def registry(frames: list[Frame]) -> list[dict]:
    """A machine-readable list of the scenes used in the project."""
    seen: dict[str, dict] = {}
    for frame in frames:
        for scene in frame.scenes:
            entry = seen.setdefault(
                scene.kind,
                {"kind": scene.kind, "builtin": is_builtin(scene.kind), "shots": []},
            )
            if frame.id not in entry["shots"]:
                entry["shots"].append(frame.id)
    return [seen[key] for key in sorted(seen)]
