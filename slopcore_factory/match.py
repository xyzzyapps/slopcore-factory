"""Match a finished render back to the clips it was cut from.

Reverse-engineer an edit: detect the scene cuts in a rendered video, match each
segment to the closest source clip by visual similarity, and (optionally) emit an
OpenTimelineIO timeline for an NLE.

The matching is *retime-blind*: a render's clips are usually stretched (slow /
optical-flow interpolate) or trimmed, so every sampled segment frame is compared
against every sampled clip frame and the best pair wins. Frames are preprocessed
(grayscale, top crop to dodge any lower-third text, high-pass to remove a scrim
gradient or grain, normalise) before the correlation.

OpenCV is imported lazily (``pip install .[match]``); the rest of the factory
never depends on it.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import SlopcoreFactoryError
from .interfaces import CommandRunner
from .logging_setup import get_logger
from .media import probe_duration

log = get_logger("match")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
FRAME_H, FRAME_W = 36, 64
SAMPLE_SECONDS = 0.4
MERGE_CUTS = 0.2  # cuts closer than this are one cut


@dataclass
class Segment:
    """One scene-cut segment of the render and the clip it matches."""

    index: int
    start: float
    end: float
    clip: str
    source: str
    score: float
    margin: float
    source_seconds: float = 0.0
    speed: float = 1.0  # source seconds / slot seconds (1.0 = trimmed, no retime)
    runner_up: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


# ---------------------------------------------------------------------------
# Cut detection + candidates
# ---------------------------------------------------------------------------


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def scene_cuts(video: Path, runner: CommandRunner, threshold: float = 0.12) -> list[float]:
    """Cut times (seconds) where the scene score exceeds ``threshold``."""
    args = [
        _ffmpeg(),
        "-hide_banner",
        "-i",
        str(video),
        "-vf",
        f"scale=480:-1,select='gt(scene,{threshold})',metadata=print",
        "-an",
        "-f",
        "null",
        "-",
    ]
    result = runner.run(args, timeout=60 * 30)
    text = (result.stderr or "") + (result.stdout or "")
    raw = sorted(float(m) for m in re.findall(r"pts_time:([0-9.]+)", text))
    cuts: list[float] = []
    for t in raw:
        if not cuts or t - cuts[-1] > MERGE_CUTS:
            cuts.append(t)
    log.info("scene cuts in %s: %d", Path(video).name, len(cuts))
    return cuts


def candidate_clips(*dirs: Path) -> dict[str, Path]:
    """Candidate sources: every video, plus every still.

    The composer renumbers its video copies ``clip1.mp4``, ``clip2.mp4`` ... which
    are duplicates of the sources, so those are skipped. Stills are never
    renumbered into duplicates of a video, and the composer's still copies
    (``clip17.jpg``) are sometimes the only surviving source for a still-backed
    shot, so every still is kept (keyed by filename).
    """
    out: dict[str, Path] = {}
    for directory in dirs:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            suffix = path.suffix.lower()
            if suffix in VIDEO_SUFFIXES:
                if re.fullmatch(r"clip\d+", path.stem):
                    continue  # a renumbered copy
                out.setdefault(path.stem, path)
            elif suffix in IMAGE_SUFFIXES:
                out.setdefault(path.name, path)  # a still is always a real source
    return out


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _opencv():  # noqa: ANN202 - (cv2, np) with a friendly error
    try:
        import cv2  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SlopcoreFactoryError(
            "matching needs OpenCV; install it with: pip install '.[match]'"
        ) from exc
    return cv2, np


def _prep(cv2, np, frame):  # noqa: ANN001, ANN202
    """Grayscale -> top crop -> small -> high-pass -> normalised."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = gray[: int(gray.shape[0] * 0.70), :]  # drop any lower-third text
    small = cv2.resize(gray, (FRAME_W, FRAME_H), interpolation=cv2.INTER_AREA).astype(np.float32)
    hp = small - cv2.GaussianBlur(small, (0, 0), 2.0)
    hp -= hp.mean()
    std = float(hp.std())
    return hp / std if std > 1e-6 else hp


def _read_frames(cv2, np, path: Path, step: float):  # noqa: ANN001, ANN202
    """Decode ``path`` into preprocessed frames, one every ``step`` seconds."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    every = max(1, round(step * fps))
    frames = []
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index % every == 0:
            frames.append(_prep(cv2, np, frame))
        index += 1
    cap.release()
    return frames


def _read_still(cv2, np, path: Path):  # noqa: ANN001, ANN202
    """Decode a still (webp included) with av."""
    import av  # noqa: PLC0415

    with av.open(str(path)) as container:
        frame = next(container.decode(video=0))
        return _prep(cv2, np, frame.to_ndarray(format="bgr24"))


def _score(np, segment, clip) -> float:  # noqa: ANN001
    """Mean over segment frames of the best correlation with any clip frame."""
    if not segment or not clip:
        return -1.0
    best = [max(float(np.mean(s * c)) for c in clip) for s in segment]
    return float(np.mean(best))


def match(
    video: Path,
    candidates: dict[str, Path],
    *,
    runner: CommandRunner,
    fps: int = 30,
    threshold: float = 0.12,
    sample: float = SAMPLE_SECONDS,
    duration: float | None = None,
) -> list[Segment]:
    """Cut ``video`` at its scene changes and match each segment to a clip."""
    cv2, np = _opencv()
    video = Path(video)
    duration = duration or probe_duration(video, runner)
    edges = [0.0, *scene_cuts(video, runner, threshold), duration]

    stills: dict[str, list] = {}
    clips: dict[str, list] = {}
    for name, path in candidates.items():
        if path.suffix.lower() in IMAGE_SUFFIXES:
            stills[name] = [_read_still(cv2, np, path)]
        else:
            clips[name] = _read_frames(cv2, np, path, sample)
    pool = {**clips, **stills}

    render = _read_frames(cv2, np, video, sample)
    segments: list[Segment] = []
    for i in range(len(edges) - 1):
        t0, t1 = edges[i], edges[i + 1]
        lo, hi = int(t0 / sample), max(int(t0 / sample) + 1, int(t1 / sample))
        frames = render[lo:hi]
        ranked = sorted(
            ((name, _score(np, frames, fs)) for name, fs in pool.items()), key=lambda kv: -kv[1]
        )
        if not ranked:
            continue
        (best, best_score), (runner_up, runner_score) = ranked[0], ranked[1]
        source = candidates[best]
        source_seconds = (
            0.0 if source.suffix.lower() in IMAGE_SUFFIXES else probe_duration(source, runner)
        )
        slot = max(0.0, t1 - t0)
        speed = 1.0
        if source_seconds and slot and source_seconds < slot:
            speed = round(source_seconds / slot, 6)
        segments.append(
            Segment(
                index=i + 1,
                start=round(t0, 3),
                end=round(t1, 3),
                clip=best,
                source=str(source),
                score=round(best_score, 4),
                margin=round(best_score - runner_score, 4),
                source_seconds=round(source_seconds, 3),
                speed=speed,
                runner_up=runner_up,
            )
        )
    log.info("matched %d segment(s) in %s", len(segments), video.name)
    return segments


# ---------------------------------------------------------------------------
# OpenTimelineIO
# ---------------------------------------------------------------------------


def _rt(frames: int, fps: int) -> dict:
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": frames}


def _timerange(start: int, duration: int, fps: int) -> dict:
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "start_time": _rt(start, fps),
        "duration": _rt(duration, fps),
    }


def _external(path: Path, frames: int, fps: int) -> dict:
    return {
        "OTIO_SCHEMA": "ExternalReference.1",
        "name": Path(path).name,
        "target_url": Path(path).resolve().as_uri(),
        "available_range": _timerange(0, frames, fps),
    }


def _track(name: str, kind: str, children: list[dict]) -> dict:
    return {
        "OTIO_SCHEMA": "Track.1",
        "name": name,
        "kind": kind,
        "metadata": {},
        "children": children,
    }


def to_otio(
    segments: list[Segment],
    *,
    fps: int = 30,
    lyrics: Path | None = None,
    song: Path | None = None,
    name: str = "timeline",
) -> dict:
    """An OTIO timeline: V1 the matched clips (exact cuts + retimes), V2 lyrics, A1 song."""
    children: list[dict] = []
    total = 0
    for segment in segments:
        start_frames = round(segment.start * fps)
        slot_frames = round(segment.end * fps) - start_frames
        total += slot_frames
        source = Path(segment.source)
        is_image = source.suffix.lower() in IMAGE_SUFFIXES
        source_frames = 0 if is_image else round(segment.source_seconds * fps)
        if is_image or source_frames <= 0 or source_frames >= slot_frames:
            span_frames, scalar = slot_frames, 1.0
        else:
            span_frames, scalar = source_frames, round(source_frames / slot_frames, 6)
        clip: dict = {
            "OTIO_SCHEMA": "Clip.1",
            "name": f"{segment.index:02d} {segment.clip}",
            "source_range": _timerange(0, span_frames, fps),
            "media_reference": _external(source, source_frames or slot_frames, fps),
            "metadata": {
                "slopcore": {
                    "segment": segment.index,
                    "match": segment.clip,
                    "score": segment.score,
                    "margin": segment.margin,
                }
            },
        }
        if abs(scalar - 1.0) > 1e-6:
            clip["effects"] = [
                {
                    "OTIO_SCHEMA": "LinearTimeWarp.1",
                    "name": "speed",
                    "effect_name": "LinearTimeWarp",
                    "time_scalar": scalar,
                    "metadata": {},
                }
            ]
        children.append(clip)

    tracks = [_track("V1 CLIPS", "Video", children)]
    if lyrics:
        tracks.append(
            _track(
                "V2 LYRICS",
                "Video",
                [
                    {
                        "OTIO_SCHEMA": "Clip.1",
                        "name": "lyrics",
                        "source_range": _timerange(0, total, fps),
                        "media_reference": _external(lyrics, total, fps),
                        "metadata": {},
                    }
                ],
            )
        )
    if song:
        tracks.append(
            _track(
                "A1 SONG",
                "Audio",
                [
                    {
                        "OTIO_SCHEMA": "Clip.1",
                        "name": "song",
                        "source_range": _timerange(0, total, fps),
                        "media_reference": _external(song, total, fps),
                        "metadata": {},
                    }
                ],
            )
        )
    return {
        "OTIO_SCHEMA": "Timeline.1",
        "name": name,
        "global_start_time": _rt(0, fps),
        "metadata": {"slopcore": {"fps": fps, "segments": len(segments)}},
        "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "metadata": {}, "children": tracks},
    }


def write_json(segments: list[Segment], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([segment.__dict__ for segment in segments], indent=2), encoding="utf-8"
    )
    return path


def write_otio(timeline: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    return path
