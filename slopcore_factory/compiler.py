"""Compile a blueprint into the render plan the composer consumes.

The blueprint is the creative source of truth; the :class:`Storyboard` is the
concrete render plan (frames, groups, timed cues) that ``compose`` turns into
HyperFrames HTML. This module is the bridge, so ``build`` renders what the
storyboard says instead of what the deterministic planner would guess.

Frame boundaries and backgrounds come straight from the blueprint's shots;
lyric lines are timed from the aligned cues (the blueprint references lyric line
indices, the cues carry the seconds).
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from .blueprint import Blueprint, Shot, ShotType
from .logging_setup import get_logger
from .models import Cue, Frame, Group, LyricsDoc, Scene, Storyboard
from .scenes import is_builtin
from .storyboard import accent_word_for

log = get_logger("compiler")

MAX_GROUP_LINES = 6
GROUP_GAP = 3.5


def safe_id(value: str) -> str:
    """A CSS-selector-safe id: never starts with a digit."""
    match = re.search(r"[A-Za-z].*", value)
    base = match.group(0) if match else value
    base = re.sub(r"[^A-Za-z0-9_-]", "-", base)
    return base or "s"


def blueprint_to_storyboard(
    blueprint: Blueprint,
    cues: list[Cue],
    lyrics: LyricsDoc,
    fallback_backgrounds: list | None = None,
) -> Storyboard:
    """Map a blueprint + timed cues to a render plan.

    ``fallback_backgrounds`` are user-supplied clips used for shots that do not
    have a generated/supplied clip of their own, so a project always has footage
    when the user provided some.
    """
    cue_by_index = {cue.index: cue for cue in cues}
    clip_paths = {
        clip.clip: Path(clip.path)
        for clip in blueprint.seedance
        if clip.path and Path(clip.path).exists()
    }
    fallbacks = [Path(p) for p in (fallback_backgrounds or []) if Path(p).exists()]

    frames: list[Frame] = []
    for index, shot in enumerate(sorted(blueprint.shots, key=lambda s: s.t0), start=1):
        background = Path(shot.media) if shot.media else None
        if background is None and shot.seedance_clip:
            background = clip_paths.get(shot.seedance_clip)
        if background is None and fallbacks:
            background = fallbacks[(index - 1) % len(fallbacks)]
        frames.append(
            Frame(
                id=shot.id,
                index=index,
                start=shot.t0,
                duration=max(0.1, shot.t1 - shot.t0),
                groups=_groups_for_shot(shot, cue_by_index),
                scenes=_scenes_for_shot(shot),
                background=background,
                kicker=shot.chrome or shot.section,
            )
        )

    storyboard = Storyboard(
        composition_id="main",
        title=blueprint.title,
        duration=blueprint.duration,
        width=blueprint.width,
        height=blueprint.height,
        fps=blueprint.fps,
        frames=frames,
        accent_word=accent_word_for(lyrics),
    )
    log.info("compiled blueprint -> %d frames", len(frames))
    return storyboard


def _scenes_for_shot(shot: Shot) -> list[Scene]:
    anim = shot.animation
    short = safe_id(shot.id)
    scenes: list[Scene] = []
    if anim and anim.scene and is_builtin(anim.scene):
        scenes.append(Scene(id=f"{short}-scene", kind=anim.scene, t0=shot.t0, t1=shot.t1))
    elif anim and anim.module:
        scenes.append(
            Scene(id=f"{short}-scene", kind="custom", t0=shot.t0, t1=shot.t1, module=anim.module)
        )
    if shot.detections:
        scenes.append(
            Scene(
                id=f"{short}-yolo",
                kind="yolo",
                t0=shot.t0,
                t1=shot.t1,
                params={"boxes": shot.detections},
            )
        )
    return scenes


def _with_overrides(cue: Cue, entry: ShotType) -> Cue:
    """A cue copy carrying a shot line's overrides (the shared cue is kept)."""
    changes: dict = {}
    if entry.position and entry.position != cue.position:
        changes["position"] = entry.position
    if entry.offset:
        changes["start"] = round(cue.start + entry.offset, 3)
        changes["end"] = round(cue.end + entry.offset, 3)
        changes["words"] = [
            replace(
                word,
                start=round(word.start + entry.offset, 3),
                end=round(word.end + entry.offset, 3),
            )
            for word in cue.words
        ]
    if not changes:
        return cue
    return replace(cue, **changes)


def _groups_for_shot(shot: Shot, cue_by_index: dict[int, Cue]) -> list[Group]:
    cues = [
        _with_overrides(cue_by_index[entry.line], entry)
        for entry in sorted(shot.type, key=lambda e: e.line)
        if entry.line in cue_by_index
    ]
    if not cues:
        return []

    chunks: list[list[Cue]] = []
    chunk: list[Cue] = []
    for cue in cues:
        if chunk and (len(chunk) >= MAX_GROUP_LINES or cue.start - chunk[-1].end > GROUP_GAP):
            chunks.append(chunk)
            chunk = []
        chunk.append(cue)
    if chunk:
        chunks.append(chunk)

    starts = [round(max(shot.t0, ch[0].start - 0.12), 3) for ch in chunks]
    bounds = starts[1:] + [shot.t1]
    short = safe_id(shot.id)
    groups: list[Group] = []
    for i, (chunk_cues, start, end) in enumerate(
        zip(chunks, starts, bounds, strict=False), start=1
    ):
        groups.append(
            Group(
                id=f"{short}-g{i}",
                kind="lyric_stack",
                start=start,
                duration=round(max(1.0, end - start), 3),
                cues=chunk_cues,
                kicker=shot.chrome or shot.section,
            )
        )
    return groups
