"""Per-shot media treatments.

A shot is filled by its background clip. When the clip is shorter than the shot,
the composer tiles it, which reads as a repeat. A treatment rewrites the clip
once (with ffmpeg) so it fills the shot with no visible loop:

* ``slow``     — stretch the clip (``setpts``); factor auto-fits the shot.
* ``pingpong`` — forward then reversed.
* ``hold``     — trim ``treatment_value`` seconds, then freeze the last frame.
* ``stutter``  — drop to a low frame rate, then stretch to fill.

The treated file is written under the work dir and recorded on ``Shot.media``;
the compiler prefers it over the raw clip. Local and free.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .blueprint import Blueprint
from .errors import SlopcoreFactoryError
from .interfaces import CommandRunner
from .logging_setup import get_logger
from .media import probe_duration

log = get_logger("treat")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def apply(
    blueprint: Blueprint,
    out_dir: Path,
    runner: CommandRunner,
    only: str | None = None,
) -> dict[str, Path]:
    """Build treated media for every shot whose treatment is not ``loop``.

    ``only`` restricts the run to a single shot id (the REPL's ``treat <shot>``).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = {
        clip.clip: Path(clip.path)
        for clip in blueprint.seedance
        if clip.path and Path(clip.path).exists()
    }
    done: dict[str, Path] = {}
    for shot in blueprint.shots:
        if only and shot.id != only:
            continue
        if shot.treatment in ("", "loop"):
            continue
        source = clips.get(shot.seedance_clip) if shot.seedance_clip else None
        if source is None or source.suffix.lower() in IMAGE_SUFFIXES:
            log.warning("%s: no clip for treatment %s", shot.id, shot.treatment)
            continue
        dest = out_dir / f"{shot.id}-{shot.treatment}.mp4"
        if not dest.exists():
            _render(source, dest, shot, runner)
        shot.media = dest.as_posix()
        done[shot.id] = dest
    if done:
        log.info("treated %d shot(s)", len(done))
    return done


def _render(source: Path, dest: Path, shot, runner: CommandRunner) -> None:
    """Write one treated clip (video only; the song is separate)."""
    duration = probe_duration(source, runner)
    if duration <= 0:
        raise SlopcoreFactoryError(f"treatment source has zero duration: {source}")

    args = [shutil.which("ffmpeg") or "ffmpeg", "-y", "-loglevel", "error", "-i", str(source)]
    if shot.treatment == "slow":
        factor = shot.treatment_value or max(1.0, shot.duration / duration)
        if factor > 1.1:
            # interpolate frames so the stretched motion is smooth, not duplicated
            interp = max(60, int(round(30 * factor)))
            args += [
                "-vf",
                f"minterpolate=fps={interp}:mi_mode=mci:mc_mode=aobmc:"
                f"me_mode=bidir:vsbmc=1,setpts={factor:.4f}*PTS",
            ]
        else:
            args += ["-vf", f"setpts={factor:.4f}*PTS"]
    elif shot.treatment == "pingpong":
        args += [
            "-filter_complex",
            "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1[v]",
            "-map",
            "[v]",
        ]
    elif shot.treatment == "hold":
        keep = max(0.2, duration - shot.treatment_value) if shot.treatment_value else duration
        pad = max(0.0, shot.duration - keep)
        args += [
            "-vf",
            f"trim=end={keep:.3f},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={pad:.3f}",
        ]
    elif shot.treatment == "stutter":
        factor = shot.treatment_value or max(1.0, shot.duration / duration)
        args += ["-vf", f"fps=12,setpts={factor:.4f}*PTS"]
    else:
        raise SlopcoreFactoryError(f"unknown treatment: {shot.treatment}")
    args += ["-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(dest)]

    result = runner.run(args, timeout=60 * 10)
    if result.returncode != 0:
        raise SlopcoreFactoryError(f"ffmpeg treatment failed: {(result.stderr or '')[:300]}")
    log.info("treated %s -> %s (%s)", source.name, dest.name, shot.treatment)
