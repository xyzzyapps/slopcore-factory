"""Built-in scene tests (deterministic, frame-local)."""

from __future__ import annotations

from slopcore_factory.models import Frame, Scene
from slopcore_factory.scenes import is_builtin, registry, scene_data


def _frame() -> Frame:
    return Frame(id="f1", index=1, start=10.0, duration=20.0)


def test_bars_scene_is_frame_local() -> None:
    scene = Scene(id="f1-scene", kind="bars", t0=12.0, t1=18.0)
    data = scene_data(scene, _frame(), "continue")
    assert data["kind"] == "bars"
    assert data["bars"] == 28
    event = data["events"][0]
    assert event["kind"] == "scene_bars"
    assert event["at"] == 2.0  # 12 - 10


def test_marquee_uses_words_and_span() -> None:
    scene = Scene(id="f1-scene", kind="marquee", t0=10.0, t1=16.0, params={"words": ["a", "b"]})
    data = scene_data(scene, _frame(), "continue")
    assert data["words"] == ["a", "b"]
    event = data["events"][0]
    assert event["kind"] == "scene_marquee"
    assert event["at"] == 0.0
    assert event["duration"] == 6.0


def test_scan_and_custom() -> None:
    scan = Scene(id="x", kind="scan", t0=0.0, t1=5.0)
    assert scene_data(scan, _frame())["events"][0]["kind"] == "scene_scan"

    custom = Scene(id="y", kind="custom", markup="<b>hi</b>")
    assert scene_data(custom, _frame())["markup"] == "<b>hi</b>"


def test_registry_lists_kinds() -> None:
    frame = _frame()
    frame.scenes = [Scene(id="s", kind="bars"), Scene(id="t", kind="scan")]
    reg = registry([frame])
    assert {entry["kind"] for entry in reg} == {"bars", "scan"}
    assert all(entry["builtin"] for entry in reg)
    assert is_builtin("bars") and not is_builtin("custom")
