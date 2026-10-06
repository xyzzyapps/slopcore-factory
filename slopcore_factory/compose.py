"""Compose a HyperFrames project from a storyboard.

This slice is deliberately dumb: it turns the model into plain data structures
and lets Jinja templates do every bit of HTML and JavaScript. No markup or script
is assembled as a Python string here.

Templates live in ``slopcore_factory/templates``:

* ``index.html.j2``          — the root composition
* ``frame.html.j2``          — one sub-composition (includes the partials)
* ``partials/media.html.j2`` — the looping background tiles
* ``partials/group.html.j2`` — the lyric / held-message groups
* ``partials/timeline.js.j2``— the GSAP timeline
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from . import scenes
from .errors import ComposeError
from .interfaces import CommandRunner
from .logging_setup import get_logger
from .media import probe_duration
from .models import FactorySpec, Frame, Group, Storyboard, Theme, Transcript
from .theme import font_css, resolve_font_path

log = get_logger("compose")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
LOOP_OFFSETS = (0.0, 1.75, 3.5, 5.25)
DEFAULT_HOOK_SECTIONS = {"chorus"}
MAX_HOOK_WORDS = 4
# Positions that render with the default line/word placement (no CSS override).
DEFAULT_POSITIONS = {"", "lower"}


@dataclass
class MediaClip:
    """A background asset copied into the generated project."""

    source: Path
    rel: str
    duration: float
    is_image: bool


def build_environment() -> Environment:
    """Jinja environment with autoescaping on (templates may inject text)."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )


def compose_project(
    spec: FactorySpec,
    storyboard: Storyboard,
    theme: Theme,
    transcript: Transcript,
    runner: CommandRunner,
    project_dir: Path | None = None,
    overlay: bool = False,
) -> dict:
    """Write the whole project and return a manifest dict.

    ``overlay`` writes a lyrics-only, transparent variant (no media, scrim or
    grain) so it can be rendered as an alpha layer for an NLE.
    """
    project = Path(project_dir or spec.out_dir)
    frames_dir = project / "compositions" / "frames"
    assets = project / "assets"
    fonts_dir = assets / "fonts"
    clips_dir = assets / "clips"
    for directory in (frames_dir, fonts_dir, clips_dir, project / "data"):
        directory.mkdir(parents=True, exist_ok=True)

    _copy_fonts(theme, fonts_dir)
    audio_rel = "" if overlay else _copy_audio(spec, assets)
    clip_map: dict[Path, MediaClip] = {} if overlay else _copy_clips(storyboard, clips_dir, runner)

    env = build_environment()
    frame_template = env.get_template("frame.html.j2")
    index_template = env.get_template("index.html.j2")

    hook_sections = {s.lower() for s in spec.extra.get("hook_sections", DEFAULT_HOOK_SECTIONS)}
    accent = storyboard.accent_word
    song_dir = Path(spec.lyrics_path).parent
    scenes_out = project / "scenes"
    scenes_out.mkdir(parents=True, exist_ok=True)

    frame_files: list[Path] = []
    for frame in storyboard.frames:
        # An overlay is text only: no media, no scenes, no scrim or grain.
        scene_ctx: list[dict] = []
        if not overlay:
            for scene in frame.scenes:
                if scene.kind == "custom":
                    scene.markup = scenes.load_custom_markup(scene, song_dir)
                    source = song_dir / scene.module if scene.module else None
                    if source and source.exists():
                        shutil.copy2(source, scenes_out / source.name)
                scene_ctx.append(scenes.scene_data(scene, frame, accent))
        rendered = frame_template.render(
            composition_id=frame.id,
            duration=f"{frame.duration:.3f}",
            width=storyboard.width,
            height=storyboard.height,
            theme=theme,
            fonts_css=font_css(theme),
            media=[] if overlay else _media_data(frame, clip_map),
            overlay=overlay,
            scenes=scene_ctx,
            groups=[_group_data(group, accent, hook_sections) for group in frame.groups],
            events=_timeline_data(frame),
        )
        path = frames_dir / f"{frame.id}.html"
        path.write_text(rendered, encoding="utf-8")
        frame_files.append(path)

    index_path = project / "index.html"
    index_path.write_text(
        index_template.render(
            title=storyboard.title,
            language=spec.language,
            width=storyboard.width,
            height=storyboard.height,
            duration=f"{storyboard.duration:.3f}",
            overlay=overlay,
            audio_rel=audio_rel,
            frames=[
                {
                    "id": f.id,
                    "file": f"{f.id}.html",
                    "start": f"{f.start:.3f}",
                    "duration": f"{f.duration:.3f}",
                }
                for f in storyboard.frames
            ],
        ),
        encoding="utf-8",
    )

    _write_project_files(
        project,
        spec,
        storyboard,
        transcript,
        audio_rel,
        clip_map,
    )
    log.info("composed project: %s (%d frames)", project, len(storyboard.frames))

    return {
        "project": str(project),
        "index": str(index_path),
        "frames": [str(p) for p in frame_files],
        "audio": audio_rel,
        "clips": [clip.rel for clip in clip_map.values()],
        "duration": storyboard.duration,
        "frame_count": len(storyboard.frames),
    }


# ---------------------------------------------------------------------------
# Data builders (no markup, no script: templates own presentation)
# ---------------------------------------------------------------------------


def _tokens(text: str, accent: str | None = None) -> list[dict]:
    """Split text into plain/accent tokens for the accent span.

    Only the first occurrence is marked: a second accent span in the same line
    reads as overlapping text to the HyperFrames layout audit.
    """
    if not accent:
        return [{"text": text, "accent": False}]
    match = re.search(rf"\b{re.escape(accent)}\b", text, re.IGNORECASE)
    if not match:
        return [{"text": text, "accent": False}]
    tokens = [
        {"text": text[: match.start()], "accent": False},
        {"text": text[match.start() : match.end()], "accent": True},
        {"text": text[match.end() :], "accent": False},
    ]
    return [token for token in tokens if token["text"]]


def _group_data(group: Group, accent: str | None, hook_sections: set[str]) -> dict:
    elements: list[dict] = []
    if group.kind == "held_message":
        cue = group.cues[0]
        elements.append(
            {"id": f"{group.id}-mark", "css_class": "mark", "tokens": _tokens(cue.text, accent)}
        )
        if group.tag:
            elements.append(
                {"id": f"{group.id}-tag", "css_class": "tag", "tokens": _tokens(group.tag)}
            )
    else:
        for i, cue in enumerate(group.cues, start=1):
            is_hook = (
                cue.section.lower() in hook_sections and len(cue.text.split()) <= MAX_HOOK_WORDS
            )
            css_class = "word" if is_hook else "line"
            if cue.position and cue.position not in DEFAULT_POSITIONS:
                css_class = f"{css_class} pos-{cue.position}"
            elements.append(
                {
                    "id": f"{group.id}-l{i}",
                    "css_class": css_class,
                    "tokens": _tokens(cue.text, accent),
                }
            )
    return {"id": group.id, "kicker": group.kicker, "elements": elements}


def _media_data(frame: Frame, clip_map: dict[Path, MediaClip]) -> list[dict]:
    clip = clip_map.get(frame.background) if frame.background else None
    if clip is None:
        return []
    # ids must not start with a digit: ``#01-f1-loop-1`` is not a valid selector.
    short = frame.id.split("-")[-1]
    if clip.is_image:
        return [
            {
                "id": f"{short}-bg",
                "src": clip.rel,
                "start": "0.000",
                "duration": f"{frame.duration:.3f}",
                "media_start": None,
                "is_image": True,
            }
        ]

    tiles: list[dict] = []
    start = 0.0
    index = 0
    while start < frame.duration - 0.05 and index < 64:
        offset = LOOP_OFFSETS[index % len(LOOP_OFFSETS)]
        length = min(clip.duration - offset, frame.duration - start)
        if length <= 0.05:
            offset = 0.0
            length = min(clip.duration, frame.duration - start)
        if length <= 0.05:
            break
        tiles.append(
            {
                "id": f"{short}-loop-{index + 1}",
                "src": clip.rel,
                "start": f"{start:.3f}",
                "duration": f"{length:.3f}",
                "media_start": f"{offset:.2f}",
                "is_image": False,
            }
        )
        start += length
        index += 1
    return tiles


def _timeline_data(frame: Frame) -> list[dict]:
    """A flat list of GSAP operations; the template turns them into script."""
    events: list[dict] = []
    for group in frame.groups:
        g_start = _local(group.start, frame)
        g_end = _local(group.start + group.duration, frame)
        if g_end <= g_start:
            g_end = min(frame.duration, g_start + 0.6)
        events.append({"kind": "show_group", "target": group.id, "at": f"{g_start:.3f}"})

        if group.kind == "held_message":
            cue = group.cues[0]
            mark_at = _local(cue.start if cue.start >= group.start else group.start, frame)
            events.append(
                {"kind": "reveal_mark", "target": f"{group.id}-mark", "at": f"{mark_at:.3f}"}
            )
            if group.tag:
                tag_at = min(max(mark_at + 2.0, mark_at + 0.4), max(mark_at + 0.4, g_end - 0.8))
                events.append(
                    {"kind": "reveal_tag", "target": f"{group.id}-tag", "at": f"{tag_at:.3f}"}
                )
        else:
            for i, cue in enumerate(group.cues, start=1):
                reveal = _local(cue.start, frame)
                if i < len(group.cues):
                    hide = _local(group.cues[i].start, frame)
                else:
                    hide = g_end
                if hide <= reveal + 0.2:
                    hide = min(frame.duration, reveal + 0.6)
                # keep the fade shorter than the gap to the next line so two
                # lines are never visible at once (the layout audit flags that)
                fade = round(min(0.45, max(0.10, (hide - reveal) * 0.7)), 3)
                events.append(
                    {
                        "kind": "reveal_line",
                        "target": f"{group.id}-l{i}",
                        "at": f"{reveal:.3f}",
                        "hide_at": f"{hide:.3f}",
                        "duration": f"{fade:.3f}",
                    }
                )
        events.append({"kind": "hide_group", "target": group.id, "at": f"{g_end:.3f}"})
    return events


def _local(absolute: float, frame: Frame) -> float:
    return round(max(0.0, min(frame.duration, absolute - frame.start)), 3)


def _scenes_readme(used: list[dict]) -> str:
    lines = [
        "# Scenes",
        "",
        "Motion-design layers used by this composition. Built-in scenes are drawn by",
        "the factory; drop a custom HTML fragment here and reference it from a shot's",
        "`animation.module` to own the animation yourself.",
        "",
        "| kind | builtin | shots |",
        "|---|---|---|",
    ]
    for entry in used:
        lines.append(
            f"| {entry['kind']} | {'yes' if entry['builtin'] else 'no'} | "
            f"{', '.join(entry['shots'])} |"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Asset copying
# ---------------------------------------------------------------------------


def _copy_fonts(theme: Theme, fonts_dir: Path) -> None:
    for filename in theme.fonts.values():
        source = resolve_font_path(theme, filename)
        if not source.exists():
            raise ComposeError(f"missing theme font: {source}")
        shutil.copy2(source, fonts_dir / filename)


def _copy_audio(spec: FactorySpec, assets: Path) -> str:
    if not spec.audio_path or not Path(spec.audio_path).exists():
        raise ComposeError("cannot compose without an audio track")
    source = Path(spec.audio_path)
    dest = assets / f"bgm{source.suffix.lower()}"
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    return dest.relative_to(assets.parent).as_posix()


def _copy_clips(
    storyboard: Storyboard, clips_dir: Path, runner: CommandRunner
) -> dict[Path, MediaClip]:
    """Copy each unique frame background into ``assets/clips`` once."""
    clip_map: dict[Path, MediaClip] = {}
    seen: set[Path] = set()
    for frame in storyboard.frames:
        if not frame.background:
            continue
        source = Path(frame.background)
        if source in seen:
            continue
        seen.add(source)
        if not source.exists():
            raise ComposeError(f"background clip not found: {source}")
        name = f"clip{len(clip_map) + 1}{source.suffix.lower()}"
        dest = clips_dir / name
        if source.resolve() != dest.resolve():
            shutil.copy2(source, dest)
        is_image = source.suffix.lower() in IMAGE_SUFFIXES
        duration = 0.0 if is_image else probe_duration(dest, runner)
        if not is_image and duration <= 0:
            raise ComposeError(f"background clip has zero duration: {source}")
        clip_map[source] = MediaClip(
            source=source,
            rel=dest.relative_to(clips_dir.parent.parent).as_posix(),
            duration=duration,
            is_image=is_image,
        )
    return clip_map


# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------


def _write_project_files(
    project: Path,
    spec: FactorySpec,
    storyboard: Storyboard,
    transcript: Transcript,
    audio_rel: str,
    clip_map: dict[Path, MediaClip],
) -> None:
    version = spec.hyperframes_version
    (project / "meta.json").write_text(
        json.dumps(
            {
                "id": spec.song_id,
                "name": spec.song_id,
                "title": spec.title,
                "createdAt": datetime.now(UTC).isoformat(),
                "generator": "slopcore_factory",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (project / "hyperframes.json").write_text(
        json.dumps(
            {
                "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                "paths": {
                    "blocks": "compositions",
                    "components": "compositions/components",
                    "assets": "assets",
                },
                "media": {"autoProxy": True},
                "authoringSkill": "music-to-video",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (project / "package.json").write_text(
        json.dumps(
            {
                "name": spec.song_id,
                "private": True,
                "type": "module",
                "scripts": {
                    "dev": f"npx --yes hyperframes@{version} preview",
                    "check": f"npx --yes hyperframes@{version} check",
                    "render": f"npx --yes hyperframes@{version} render",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if spec.lyrics_path.exists():
        (project / "lyrics.md").write_text(
            spec.lyrics_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    (project / "transcript.json").write_text(
        json.dumps(
            {
                "engine": transcript.engine,
                "duration": transcript.duration,
                "words": [
                    {"word": w.word, "start": w.start, "end": w.end} for w in transcript.words
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    scenes_dir = project / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    used = scenes.registry(storyboard.frames)
    (scenes_dir / "registry.json").write_text(
        json.dumps({"scenes": used}, indent=2), encoding="utf-8"
    )
    (scenes_dir / "README.md").write_text(_scenes_readme(used), encoding="utf-8")

    (project / "build.json").write_text(
        json.dumps(
            {
                "song_id": spec.song_id,
                "title": spec.title,
                "duration": storyboard.duration,
                "width": storyboard.width,
                "height": storyboard.height,
                "fps": storyboard.fps,
                "theme": spec.theme_name,
                "accent_word": storyboard.accent_word,
                "audio": audio_rel,
                "clips": [
                    dict(source=str(c.source), rel=c.rel, duration=c.duration)
                    for c in clip_map.values()
                ],
                "frames": [
                    {
                        "id": f.id,
                        "start": f.start,
                        "duration": f.duration,
                        "groups": len(f.groups),
                        "kicker": f.kicker,
                    }
                    for f in storyboard.frames
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
