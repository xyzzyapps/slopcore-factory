"""Background media: probe, loop prep, and a zero-cost fallback plate."""

from __future__ import annotations

import shutil
from pathlib import Path

from .errors import MediaError
from .interfaces import CommandRunner
from .logging_setup import get_logger
from .models import FactorySpec

log = get_logger("media")

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def _tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise MediaError(f"required tool not on PATH: {name}")
    return found


def probe_duration(path: Path, runner: CommandRunner) -> float:
    """Duration in seconds via ffprobe."""
    result = runner.run(
        [
            _tool("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ]
    )
    if result.returncode != 0:
        raise MediaError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise MediaError(f"could not parse duration for {path}") from exc


def discover_clips(base: Path) -> list[Path]:
    """Any video files under ``base/assets/clips`` (sorted, deterministic)."""
    clips_dir = Path(base) / "assets" / "clips"
    if not clips_dir.is_dir():
        return []
    return sorted(p for p in clips_dir.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES)


def synthesize_plate(
    work_dir: Path, width: int, height: int, runner: CommandRunner, seconds: int = 8
) -> Path:
    """Generate a dark, slowly-living fallback plate with ffmpeg (no network).

    A near-black field plus fine temporal noise and a soft vignette reads as a
    living background rather than a slideshow card, and costs nothing.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / "plate.mp4"
    if out.exists():
        return out
    vf = "noise=alls=6:allf=t,vignette=PI/5,format=yuv420p"
    result = runner.run(
        [
            _tool("ffmpeg"),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0d0d0f:s={width}x{height}:d={seconds}:r=30",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    if result.returncode != 0 or not out.exists():
        raise MediaError(f"plate generation failed: {result.stderr.strip()}")
    log.info("synthesized fallback plate: %s", out)
    return out


def prepare_background(spec: FactorySpec, work_dir: Path, runner: CommandRunner) -> list[Path]:
    """Return the background clip(s) to use, in priority order.

    1. Explicitly supplied paths.
    2. Video files discovered in the song folder's ``assets/clips``.
    3. A locally synthesized plate.
    """
    supplied = [Path(p) for p in spec.backgrounds if Path(p).exists()]
    if supplied:
        log.info("background: %d supplied clip(s)", len(supplied))
        return supplied

    discovered = discover_clips(spec.lyrics_path.parent)
    if discovered:
        log.info("background: %d discovered clip(s)", len(discovered))
        return discovered

    if spec.generate_clips:
        # The pipeline handles generated clips before calling here.
        raise MediaError("clip generation requested but no clips were produced")

    return [synthesize_plate(work_dir, spec.width, spec.height, runner)]
