"""Per-shot media treatment tests (ffmpeg commands are captured, not run)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from slopcore_factory.blueprint import Blueprint, SeedanceClip, Shot
from slopcore_factory.treat import apply


class FakeRunner:
    """Records commands; answers ffprobe with a fixed duration."""

    def __init__(self, duration: float = 6.0) -> None:
        self.duration = duration
        self.calls: list[list[str]] = []

    def run(self, args, cwd=None, timeout=None):  # noqa: ANN001
        self.calls.append(list(args))
        if Path(args[0]).stem.lower() == "ffprobe":
            return subprocess.CompletedProcess(args, 0, stdout=f"{self.duration}\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def _blueprint(tmp_path: Path, treatment: str, value: float = 0.0) -> Blueprint:
    clip = tmp_path / "c01.mp4"
    clip.write_bytes(b"x")
    return Blueprint(
        title="t",
        duration=12.0,
        shots=[
            Shot(
                id="sh01",
                t0=0.0,
                t1=12.0,
                seedance_clip="c01",
                treatment=treatment,
                treatment_value=value,
            )
        ],
        seedance=[SeedanceClip("c01", 6.0, path=str(clip))],
    )


def _ffmpeg(runner: FakeRunner) -> list[str]:
    return next(call for call in runner.calls if Path(call[0]).stem.lower() == "ffmpeg")


def test_slow_stretches_to_fit_the_shot(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path, "slow")
    runner = FakeRunner()
    done = apply(blueprint, tmp_path / "out", runner)
    assert set(done) == {"sh01"}
    assert blueprint.shots[0].media.endswith("sh01-slow.mp4")
    assert "setpts=2.0000*PTS" in " ".join(_ffmpeg(runner))


def test_hold_trims_then_freezes(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path, "hold", value=1.0)
    runner = FakeRunner()
    apply(blueprint, tmp_path / "out", runner)
    joined = " ".join(_ffmpeg(runner))
    assert "trim=end=5.000" in joined
    assert "tpad=stop_mode=clone" in joined


def test_pingpong_concats_forward_and_reverse(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path, "pingpong")
    runner = FakeRunner()
    apply(blueprint, tmp_path / "out", runner)
    assert "reverse" in " ".join(_ffmpeg(runner))


def test_loop_is_left_alone(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path, "loop")
    runner = FakeRunner()
    assert apply(blueprint, tmp_path / "out", runner) == {}
    assert blueprint.shots[0].media == ""


def test_slow_interpolates_when_stretching(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path, "slow")
    runner = FakeRunner()
    apply(blueprint, tmp_path / "out", runner)
    joined = " ".join(_ffmpeg(runner))
    assert "minterpolate" in joined
    assert "mi_mode=mci" in joined


def test_stutter_drops_the_frame_rate(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path, "stutter")
    runner = FakeRunner()
    apply(blueprint, tmp_path / "out", runner)
    joined = " ".join(_ffmpeg(runner))
    assert "fps=12" in joined
    assert "setpts=2.0000*PTS" in joined


def test_only_restricts_to_one_shot(tmp_path: Path) -> None:
    clip = tmp_path / "c01.mp4"
    clip.write_bytes(b"x")
    blueprint = Blueprint(
        title="t",
        duration=24.0,
        shots=[
            Shot(id="sh01", t0=0.0, t1=12.0, seedance_clip="c01", treatment="slow"),
            Shot(id="sh02", t0=12.0, t1=24.0, seedance_clip="c01", treatment="slow"),
        ],
        seedance=[SeedanceClip("c01", 6.0, path=str(clip))],
    )
    runner = FakeRunner()
    done = apply(blueprint, tmp_path / "out", runner, only="sh02")
    assert set(done) == {"sh02"}
    assert blueprint.shots[0].media == ""
    assert blueprint.shots[1].media.endswith("sh02-slow.mp4")
