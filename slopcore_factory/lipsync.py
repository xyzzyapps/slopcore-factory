"""Lipsync planning and drift detection.

Two jobs, both local and free:

1. **Plan windows.** Cut the sung stretches into 4-8 s windows that start in a
   gap between words (never mid-word), quote the exact words sung inside them,
   and alternate framing. These become the audio-conditioned Seedance clips.
2. **Detect drift.** Given a clip's returned soundtrack and the reference vocal,
   find the point where they diverge, so the edit can cut on the word gap before
   it and a cover clip can take over. This is measured, not eyeballed.

No fallback model is planned: the strategy is measure -> cut -> cover.
"""

from __future__ import annotations

import numpy as np

from .audio import Gap, gap_at, last_gap_before
from .blueprint import Blueprint, Character, LipsyncWindow, SeedanceClip
from .budget import apply_estimate
from .logging_setup import get_logger
from .models import Word

log = get_logger("lipsync")

FRAMINGS = ("CU", "MCU", "MS", "profile", "over-shoulder")
CLIP_MIN = 4.0
CLIP_MAX = 8.0
MIN_COVER = 0.5


# ---------------------------------------------------------------------------
# Window planning
# ---------------------------------------------------------------------------


def plan_windows(
    words: list[Word],
    duration: float,
    gaps: list[Gap],
    clip_min: float = CLIP_MIN,
    clip_max: float = CLIP_MAX,
    max_clips: int = 240,
    framings: tuple[str, ...] = FRAMINGS,
) -> list[LipsyncWindow]:
    """Chain audio-conditioned singing windows across the song."""
    ordered = sorted(words, key=lambda w: w.start)
    if not ordered or duration <= 0:
        return []

    windows: list[LipsyncWindow] = []
    t = 0.0
    guard = 0
    while t < duration - 0.05 and len(windows) < max_clips and guard < max_clips * 4:
        guard += 1
        gap = gap_at(t, gaps)
        if gap is None:
            nxt = next_gap_after(t, gaps)
            if nxt is None:
                break
            t = nxt.middle

        end = _choose_end(t, duration, gaps, clip_min, clip_max)
        inside = [w for w in ordered if w.start >= t - 1e-6 and w.end <= end + 1e-6]
        if inside:
            windows.append(
                LipsyncWindow(
                    clip=f"ls{len(windows) + 1:02d}",
                    song_t0=round(t, 3),
                    duration=round(end - t, 3),
                    words=" ".join(w.word for w in inside),
                    framing=framings[len(windows) % len(framings)],
                )
            )
        if end <= t + 1e-3:
            break
        t = end

    log.info(
        "planned %d lipsync windows (%.1fs sung)", len(windows), sum(w.duration for w in windows)
    )
    return windows


def next_gap_after(t: float, gaps: list[Gap], epsilon: float = 0.01) -> Gap | None:
    for gap in gaps:
        if gap.middle >= t - epsilon:
            return gap
    return None


def _choose_end(t: float, duration: float, gaps: list[Gap], lo: float, hi: float) -> float:
    """The latest gap boundary within the window's length budget."""
    lo_t = t + lo
    hi_t = min(t + hi, duration)
    candidates: list[float] = []
    gap_candidates: list[float] = []
    for gap in gaps:
        for value in (gap.start, gap.middle, gap.end):
            if lo_t - 1e-6 <= value <= hi_t + 1e-6:
                candidates.append(value)
                gap_candidates.append(value)
    candidates.append(hi_t)
    pool = gap_candidates or candidates
    return round(max(pool), 3) if pool else round(hi_t, 3)


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------


def clip_prompt(window: LipsyncWindow, character: Character | None, style: str = "") -> str:
    """The audio-conditioned Seedance prompt for one window."""
    parts = [
        f"@Image1 sings @Audio1. She lip-syncs to @Audio1 exactly, every word in time: "
        f'"{window.words}".'
    ]
    if character and character.canon:
        parts.append(character.canon)
    if window.framing:
        parts.append(f"{window.framing}.")
    parts.append("Locked camera, no cuts, no head turns.")
    if style:
        parts.append(style)
    return " ".join(parts)


def plan_clips(
    windows: list[LipsyncWindow],
    character: Character | None = None,
    plate: str = "hero",
    style: str = "",
) -> list[SeedanceClip]:
    """Turn windows into Seedance clip entries."""
    return [
        SeedanceClip(
            clip=window.clip,
            duration=window.duration,
            prompt=clip_prompt(window, character, style),
            plate=plate,
            song_t0=window.song_t0,
            words=window.words,
            sing=True,
        )
        for window in windows
    ]


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


def _envelope(samples: np.ndarray, sr: int, hop: float) -> np.ndarray:
    hop_n = max(1, int(sr * hop))
    frames = max(1, len(samples) // hop_n)
    trimmed = samples[: frames * hop_n].reshape(frames, hop_n)
    return np.sqrt(np.mean(trimmed.astype(np.float64) ** 2, axis=1) + 1e-9)


def detect_divergence(
    reference: np.ndarray,
    returned: np.ndarray,
    sr: int,
    hop: float = 0.02,
    window: float = 1.0,
    threshold: float = 0.6,
) -> float | None:
    """First time (seconds) the returned soundtrack stops matching the reference.

    Compares short-time energy envelopes with a sliding correlation; returns
    ``None`` when they stay aligned for the whole clip.
    """
    if reference.size == 0 or returned.size == 0:
        return None
    ref = _envelope(np.asarray(reference), sr, hop)
    ret = _envelope(np.asarray(returned), sr, hop)
    n = min(len(ref), len(ret))
    if n < 4:
        return None
    ref, ret = ref[:n], ret[:n]
    width = max(2, int(window / hop))
    step = max(1, width // 4)

    for i in range(0, max(1, n - width), step):
        a = ref[i : i + width]
        b = ret[i : i + width]
        if a.size < 2 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
            continue
        corr = float(np.corrcoef(a, b)[0, 1])
        if corr < threshold:
            return round(i * hop, 3)
    return None


# ---------------------------------------------------------------------------
# Covers
# ---------------------------------------------------------------------------


def plan_cover(
    window: LipsyncWindow, divergence_t: float, words: list[Word], gaps: list[Gap]
) -> LipsyncWindow | None:
    """A cover window that resumes at the last word gap before the drift."""
    gap = gap_at(divergence_t, gaps) or last_gap_before(divergence_t, gaps)
    start = gap.start if gap else divergence_t
    end = window.song_t0 + window.duration
    if start <= window.song_t0 + 0.1:
        start = window.song_t0 + window.duration / 2.0
    if end - start < MIN_COVER:
        return None
    inside = [w for w in words if w.start >= start - 1e-6 and w.end <= end + 1e-6]
    return LipsyncWindow(
        clip=f"{window.clip}-c1",
        song_t0=round(start, 3),
        duration=round(end - start, 3),
        words=" ".join(w.word for w in inside),
        framing=window.framing,
        cover_of=window.clip,
    )


# ---------------------------------------------------------------------------
# Blueprint attachment
# ---------------------------------------------------------------------------


def attach_to_blueprint(
    blueprint: Blueprint, windows: list[LipsyncWindow], clips: list[SeedanceClip] | None = None
) -> Blueprint:
    """Write the planned windows/clips into the blueprint and re-estimate."""
    blueprint.lipsync = list(windows)
    blueprint.seedance = list(
        clips if clips is not None else plan_clips(windows, blueprint.character)
    )
    for shot in blueprint.shots:
        best: LipsyncWindow | None = None
        best_overlap = 0.0
        for window in windows:
            overlap = max(
                0.0,
                min(shot.t1, window.song_t0 + window.duration) - max(shot.t0, window.song_t0),
            )
            if overlap > best_overlap:
                best_overlap, best = overlap, window
        if best is not None and best_overlap > 0.05:
            shot.motion_tier = "seedance"
            shot.seedance_clip = best.clip
    apply_estimate(blueprint)
    return blueprint


def add_covers(
    blueprint: Blueprint, divergences: dict[str, float], words: list[Word], gaps: list[Gap]
) -> list[LipsyncWindow]:
    """Add a cover window for every clip whose sync drifted, then re-estimate.

    ``divergences`` maps a clip id to the measured drift time (seconds).
    """
    existing = {window.clip for window in blueprint.lipsync}
    covers: list[LipsyncWindow] = []
    for window in list(blueprint.lipsync):
        drift = divergences.get(window.clip)
        if drift is None:
            continue
        cover = plan_cover(window, drift, words, gaps)
        if cover is None or cover.clip in existing:
            continue
        covers.append(cover)
        blueprint.lipsync.append(cover)
        existing.add(cover.clip)

    if covers:
        blueprint.seedance.extend(plan_clips(covers, blueprint.character))
    apply_estimate(blueprint)
    log.info("added %d cover window(s)", len(covers))
    return covers
