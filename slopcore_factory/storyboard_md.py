"""The storyboard markdown: one strict-markdown plan for a song.

The plan is the human-readable *and* machine-executable storyboard. It carries
everything a run needs — settings, chapters, shots, the lyric lines with their
times and placement, and the prompts that are sent to the servers (the song style
and the per-clip prompts).

It lives beside ``lyrics.md`` as ``storyboard.md``. On Windows this is the same
filename as the old ``STORYBOARD.md`` dump, so it replaces that file in place.

``render`` / ``plan_text`` / ``write_plan`` write the plan; ``parse`` / ``load_plan``
read it back, so editing the markdown IS editing the plan. The pipeline's ``plan``
stage prefers ``storyboard.md`` over ``blueprint.yaml``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .blueprint import (
    BLUEPRINT_VERSION,
    Animation,
    AnimationScene,
    AssetNeeds,
    Blueprint,
    Budgets,
    Chapter,
    Character,
    LipsyncWindow,
    Plate,
    SeedanceClip,
    Shot,
    ShotType,
    load_blueprint,
    save_blueprint,
)
from .errors import ConfigError
from .models import Cue, FactorySpec, LyricsDoc

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
PLAN_FILENAME = "storyboard.md"


def _environment() -> Environment:
    """A markdown environment: no autoescaping, block tags trimmed."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _cell(value: object) -> str:
    """A markdown table cell: collapse newlines and escape pipes."""
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def plan_path(song_dir: Path) -> Path:
    """Where the plan lives: beside the lyrics."""
    return Path(song_dir) / PLAN_FILENAME


def render(
    blueprint: Blueprint,
    cues: list[Cue] | None = None,
    song_style: str = "",
    dry_run: bool | None = None,
) -> str:
    """Render the plan as strict markdown."""
    template = _environment().get_template("storyboard.plan.md.j2")
    return template.render(**_plan_data(blueprint, cues, song_style, dry_run))


def plan_text(spec: FactorySpec, work_dir: Path) -> str:
    """Render the plan for a spec: the current storyboard, else the blueprint + cues."""
    from .lyrics import parse_lyrics

    lyrics_path = Path(spec.lyrics_path)
    lyrics = parse_lyrics(lyrics_path) if lyrics_path.exists() else None
    plan = load_plan(lyrics_path.parent, Path(work_dir), lyrics)
    if plan is not None:
        blueprint, cues = plan
        if not blueprint.meta.get("song_backend"):
            blueprint.meta["song_backend"] = str(
                spec.extra.get("song_backend") or ("suno" if spec.generate_song else "supplied")
            )
    else:
        blueprint_path = Path(work_dir) / "blueprint.yaml"
        if not blueprint_path.exists():
            raise ConfigError(f"no plan to render a storyboard from: {blueprint_path}")
        blueprint = load_blueprint(blueprint_path)
        cues = None
        cues_path = Path(work_dir) / "cues.json"
        if cues_path.exists():
            from .serde import cues_from_list

            cues = cues_from_list(json.loads(cues_path.read_text(encoding="utf-8")))
    return render(
        blueprint,
        cues,
        song_style=song_style_for(spec),
        dry_run=bool(spec.extra.get("dry_run")),
    )


def write_plan(spec: FactorySpec, work_dir: Path) -> Path:
    """Write the plan beside the lyrics and return its path."""
    path = plan_path(Path(spec.lyrics_path).parent)
    path.write_text(plan_text(spec, work_dir), encoding="utf-8")
    return path


def song_style_for(spec: FactorySpec) -> str:
    """The song style sent to the server: the style file, else ``extra['style']``."""
    if spec.suno_style_path and Path(spec.suno_style_path).exists():
        return Path(spec.suno_style_path).read_text(encoding="utf-8").strip()
    return str(spec.extra.get("style", "") or "").strip()


def _plan_data(
    blueprint: Blueprint,
    cues: list[Cue] | None,
    song_style: str,
    dry_run: bool | None,
) -> dict:
    cue_by_index = {cue.index: cue for cue in (cues or [])}
    budgets = blueprint.budgets

    settings: list[dict] = [
        {"key": "canvas", "value": f"{blueprint.width}x{blueprint.height}"},
        {"key": "fps", "value": blueprint.fps},
        {"key": "duration", "value": f"{blueprint.duration:.3f}"},
        {"key": "theme", "value": blueprint.theme},
        {"key": "lyrics", "value": _cell(blueprint.lyrics_path)},
        {"key": "audio", "value": _cell(blueprint.audio)},
        {"key": "budget_usd", "value": f"{budgets.cap_usd:.2f}"},
        {"key": "retry_buffer", "value": f"{budgets.retry_buffer:.2f}"},
        {"key": "seedance_quality", "value": budgets.seedance_quality},
        {"key": "version", "value": blueprint.version},
        {"key": "song_backend", "value": blueprint.meta.get("song_backend", "")},
        {
            "key": "generate_song",
            "value": "true" if blueprint.meta.get("generate_song") else "false",
        },
        {
            "key": "generate_clips",
            "value": "true" if blueprint.meta.get("generate_clips") else "false",
        },
    ]
    if dry_run is not None:
        settings.append({"key": "dry_run", "value": "true" if dry_run else "false"})

    character = [
        {"key": "name", "value": _cell(blueprint.character.name)},
        {"key": "canon", "value": _cell(blueprint.character.canon)},
        {"key": "identity_notes", "value": _cell(blueprint.character.identity_notes)},
        {
            "key": "reference_images",
            "value": _cell(", ".join(blueprint.character.reference_images)),
        },
    ]

    chapters = [
        {
            "id": c.id,
            "name": _cell(c.name),
            "t0": f"{c.t0:.3f}",
            "t1": f"{c.t1:.3f}",
            "grade": _cell(c.grade),
            "accent": _cell(c.accent),
            "screen": _cell(c.screen),
            "set": _cell(c.set),
        }
        for c in blueprint.chapters
    ]

    shots_sorted = sorted(blueprint.shots, key=lambda s: s.t0)
    shots = [
        {
            "id": s.id,
            "t0": f"{s.t0:.3f}",
            "t1": f"{s.t1:.3f}",
            "chapter": s.chapter,
            "section": _cell(s.section),
            "framing": _cell(s.framing),
            "action": _cell(s.action),
            "camera": _cell(s.camera),
            "tier": s.motion_tier,
            "clip": s.seedance_clip or "",
            "treatment": s.treatment,
            "value": f"{s.treatment_value:g}",
            "scene": _cell(s.animation.scene),
            "module": _cell(s.animation.module),
            "media": _cell(s.media),
            "chrome": _cell(s.chrome),
            "lift": f"{s.lift:g}",
            "meme": _cell(s.meme_visual),
        }
        for s in shots_sorted
    ]
    assets = [
        {
            "shot": s.id,
            "plate": _cell(s.assets.plate),
            "depth": "yes" if s.assets.depth else "no",
            "tracking": _cell(", ".join(s.assets.tracking)),
        }
        for s in shots_sorted
    ]

    lyrics = []
    for shot in shots_sorted:
        for entry in sorted(shot.type, key=lambda e: e.line):
            cue = cue_by_index.get(entry.line)
            lyrics.append(
                {
                    "line": entry.line,
                    "start": f"{cue.start:.3f}" if cue else "",
                    "text": _cell(entry.text),
                    "mode": entry.mode,
                    "position": entry.position,
                    "offset": f"{entry.offset:g}",
                }
            )

    clips = [
        {
            "clip": c.clip,
            "sing": "yes" if c.sing else "no",
            "duration": f"{c.duration:.2f}",
            "start": f"{c.song_t0:.3f}",
            "path": _cell(c.path),
            "cover": c.cover_of,
            "plate": _cell(c.plate),
            "reference": "yes" if c.use_reference else "no",
            "words": _cell(c.words),
            "prompt": _cell(c.prompt),
        }
        for c in blueprint.seedance
    ]

    lipsync = [
        {
            "clip": w.clip,
            "start": f"{w.song_t0:.3f}",
            "duration": f"{w.duration:.2f}",
            "words": _cell(w.words),
            "framing": _cell(w.framing),
        }
        for w in blueprint.lipsync
    ]

    animation = [
        {
            "id": a.id,
            "chapter": a.chapter,
            "t0": f"{a.t0:.3f}",
            "t1": f"{a.t1:.3f}",
            "module": _cell(a.module),
            "notes": _cell(a.notes),
        }
        for a in blueprint.animation
    ]

    plates = [
        {
            "plate": p.plate,
            "set": _cell(p.set),
            "aspect": p.aspect,
            "depth": "yes" if p.depth else "no",
            "prompt": _cell(p.prompt),
        }
        for p in blueprint.plates
    ]

    return {
        "title": blueprint.title,
        "settings": settings,
        "character": character,
        "chapters": chapters,
        "shots": shots,
        "assets": assets,
        "lyrics": lyrics,
        "song_style": blueprint.meta.get("song_style") or song_style,
        "clips": clips,
        "lipsync": lipsync,
        "animation": animation,
        "plates": plates,
    }


# ---------------------------------------------------------------------------
# Loader: parse the plan back into the blueprint
# ---------------------------------------------------------------------------


def _sections(text: str) -> dict[str, list[str]]:
    """Split ``## x`` / ``### y`` sections (sub-sections keyed ``x/y``)."""
    out: dict[str, list[str]] = {}
    key = ""
    lines: list[str] = []

    def flush() -> None:
        if key:
            out[key] = lines

    for raw in text.splitlines():
        if raw.startswith("### "):
            flush()
            key = f"{key.split('/')[0]}/{raw[4:].strip()}"
            lines = []
        elif raw.startswith("## "):
            flush()
            key = raw[3:].strip()
            lines = []
        elif key:
            lines.append(raw)
    flush()
    return out


def _cells(line: str) -> list[str]:
    """Split a markdown table row into cells (``\\|`` is a literal pipe)."""
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [part.replace("\\|", "|").strip() for part in re.split(r"(?<!\\)\|", row)]


def _table(lines: list[str]) -> list[dict[str, str]]:
    """Parse a markdown table (header + separator + rows) into row dicts."""
    rows = [line for line in lines if line.strip().startswith("|")]
    if len(rows) < 3:
        return []
    header = _cells(rows[0])
    return [dict(zip(header, _cells(row), strict=False)) for row in rows[2:]]


def _num(value: str | None, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _int(value: str | None, default: int = 0) -> int:
    return int(_num(value, default))


def _flag(value: str | None, default: bool = False) -> bool:
    text = str(value).strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _canvas(value: str) -> tuple[int, int]:
    match = re.match(r"\s*(\d+)\s*x\s*(\d+)", value or "")
    if not match:
        return 1280, 720
    return int(match.group(1)), int(match.group(2))


def settings_of(text: str) -> dict[str, str]:
    """The ``## settings`` table as a plain dict."""
    return {row["key"]: row["value"] for row in _table(_sections(text).get("settings", []))}


def parse(text: str, lyrics: LyricsDoc | None = None) -> tuple[Blueprint, list[Cue]]:
    """Parse a plan into ``(blueprint, cues)``. Editing the markdown IS the edit."""
    sections = _sections(text)
    settings = settings_of(text)
    width, height = _canvas(settings.get("canvas", "1280x720"))

    character_rows = {row["field"]: row["value"] for row in _table(sections.get("character", []))}
    character = Character(
        name=character_rows.get("name", "lead"),
        canon=character_rows.get("canon", ""),
        identity_notes=character_rows.get("identity_notes", ""),
        reference_images=[
            part.strip()
            for part in character_rows.get("reference_images", "").split(",")
            if part.strip()
        ],
    )

    chapters = [
        Chapter(
            id=row["id"],
            name=row.get("name", ""),
            t0=_num(row.get("start")),
            t1=_num(row.get("end")),
            grade=row.get("grade", ""),
            accent=row.get("accent", ""),
            screen=row.get("screen", ""),
            set=row.get("set", ""),
        )
        for row in _table(sections.get("chapters", []))
    ]

    shots: list[Shot] = []
    for row in _table(sections.get("shots", [])):
        shots.append(
            Shot(
                id=row["shot"],
                t0=_num(row.get("start")),
                t1=_num(row.get("end")),
                chapter=row.get("chapter", ""),
                section=row.get("section", ""),
                framing=row.get("framing", ""),
                action=row.get("action", ""),
                camera=row.get("camera", ""),
                motion_tier=row.get("tier", "code") or "code",
                seedance_clip=(row.get("clip") or None),
                treatment=row.get("treatment", "loop") or "loop",
                treatment_value=_num(row.get("value")),
                media=row.get("media", ""),
                chrome=row.get("chrome", ""),
                lift=_num(row.get("lift")),
                meme_visual=row.get("meme", ""),
                animation=Animation(scene=row.get("scene", ""), module=row.get("module", "")),
            )
        )
    shots.sort(key=lambda shot: shot.t0)
    asset_rows = {row["shot"]: row for row in _table(sections.get("shot assets", []))}
    for shot in shots:
        row = asset_rows.get(shot.id)
        if row:
            shot.assets = AssetNeeds(
                plate=row.get("plate", ""),
                depth=_flag(row.get("depth")),
                tracking=[
                    part.strip() for part in row.get("tracking", "").split(",") if part.strip()
                ],
            )

    lyric_rows = _table(sections.get("lyrics", []))
    for row in lyric_rows:
        index = _int(row.get("line"))
        shot = _shot_at(shots, _num(row.get("start")))
        if shot is None:
            continue
        shot.type.append(
            ShotType(
                line=index,
                mode=row.get("mode", "subtitle") or "subtitle",
                text=row.get("text", ""),
                position=row.get("position", ""),
                offset=_num(row.get("offset")),
            )
        )
        shot.lines.append(index)

    clips = [
        SeedanceClip(
            clip=row["clip"],
            duration=_num(row.get("duration")),
            prompt=row.get("prompt", ""),
            sing=_flag(row.get("sing")),
            song_t0=_num(row.get("start")),
            path=row.get("path", ""),
            cover_of=row.get("cover", ""),
            plate=row.get("plate", ""),
            words=row.get("words", ""),
            use_reference=_flag(row.get("reference") or "yes", True),
        )
        for row in _table(sections.get("prompts/clips", []))
    ]

    lipsync = [
        LipsyncWindow(
            clip=row["clip"],
            song_t0=_num(row.get("start")),
            duration=_num(row.get("duration")),
            words=row.get("words", ""),
            framing=row.get("framing", ""),
        )
        for row in _table(sections.get("lipsync", []))
    ]
    # a clip with no start inherits its lipsync window's start (avsync slices there)
    window_start = {window.clip: window.song_t0 for window in lipsync}
    for clip in clips:
        if not clip.song_t0 and clip.clip in window_start:
            clip.song_t0 = window_start[clip.clip]

    animation = [
        AnimationScene(
            id=row["id"],
            chapter=row.get("chapter", ""),
            t0=_num(row.get("start")),
            t1=_num(row.get("end")),
            module=row.get("module", ""),
            notes=row.get("notes", ""),
        )
        for row in _table(sections.get("animation", []))
    ]

    plates = [
        Plate(
            plate=row["plate"],
            set=row.get("set", ""),
            aspect=row.get("aspect", "16:9") or "16:9",
            depth=_flag(row.get("depth")),
            prompt=row.get("prompt", ""),
        )
        for row in _table(sections.get("plates", []))
    ]

    budgets = Budgets(
        cap_usd=_num(settings.get("budget_usd")),
        seedance_quality=settings.get("seedance_quality", "720p") or "720p",
        retry_buffer=_num(settings.get("retry_buffer"), 1.35),
    )

    blueprint = Blueprint(
        title=_title(text),
        duration=_num(settings.get("duration")),
        lyrics_path=settings.get("lyrics", ""),
        audio=settings.get("audio", ""),
        width=width,
        height=height,
        fps=_int(settings.get("fps"), 30),
        theme=settings.get("theme", "broadside") or "broadside",
        version=_int(settings.get("version"), BLUEPRINT_VERSION),
        character=character,
        chapters=chapters,
        shots=shots,
        seedance=clips,
        plates=plates,
        lipsync=lipsync,
        animation=animation,
        budgets=budgets,
        meta={
            "song_style": _song_block(sections),
            "song_backend": settings.get("song_backend", ""),
            "generate_song": _flag(settings.get("generate_song")),
            "generate_clips": _flag(settings.get("generate_clips")),
        },
    )
    return blueprint, _cues(lyric_rows, lyrics)


def _song_block(sections: dict[str, list[str]]) -> str:
    """The text inside the fenced block under ``### song``."""
    lines = sections.get("prompts/song", [])
    inside: list[str] = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            inside.append(line)
    return "\n".join(inside).strip()


def load_plan(
    song_dir: Path, work_dir: Path, lyrics: LyricsDoc | None = None
) -> tuple[Blueprint, list[Cue] | None] | None:
    """The plan: ``storyboard.md`` first, else the legacy ``blueprint.yaml``."""
    plan = plan_path(song_dir)
    if plan.exists():
        blueprint, cues = parse(plan.read_text(encoding="utf-8"), lyrics)
        _resolve_clip_paths(blueprint, Path(song_dir) / "assets" / "clips")
        return blueprint, cues
    legacy = Path(work_dir) / "blueprint.yaml"
    if legacy.exists():
        return load_blueprint(legacy), None
    return None


def apply_settings(spec: FactorySpec, settings: dict[str, str]) -> None:
    """Apply the plan's settings onto a spec (canvas, fps, theme, audio, budget, dry-run)."""
    if settings.get("canvas"):
        spec.width, spec.height = _canvas(settings["canvas"])
    if settings.get("fps"):
        spec.fps = _int(settings.get("fps"), spec.fps)
    if settings.get("theme"):
        spec.theme_name = settings["theme"]
    if settings.get("lyrics"):
        spec.lyrics_path = Path(settings["lyrics"])
    if settings.get("audio"):
        spec.audio_path = Path(settings["audio"])
    if settings.get("duration"):
        spec.duration = _num(settings.get("duration"))
    if settings.get("song_backend"):
        spec.extra["song_backend"] = settings["song_backend"]
    if "generate_song" in settings:
        spec.generate_song = _flag(settings.get("generate_song"))
    if "generate_clips" in settings:
        spec.generate_clips = _flag(settings.get("generate_clips"))
    if settings.get("budget_usd"):
        spec.extra["budget_usd"] = _num(settings.get("budget_usd"))
    if "dry_run" in settings:
        spec.extra["dry_run"] = _flag(settings.get("dry_run"))


def save_plan(
    blueprint: Blueprint,
    song_dir: Path,
    work_dir: Path,
    *,
    spec: FactorySpec | None = None,
    lyrics: LyricsDoc | None = None,
) -> Path:
    """Write the plan back: ``storyboard.md`` when it exists, else ``blueprint.yaml``.

    The later stages (lipsync, clips, covers, treat) mutate the blueprint; writing
    through here keeps the markdown the single live plan instead of leaving the
    edit in the yaml the loader no longer prefers.
    """
    plan = plan_path(song_dir)
    if plan.exists():
        existing = load_plan(song_dir, Path(work_dir), lyrics)
        cues = existing[1] if existing else None
        style = song_style_for(spec) if spec else str(blueprint.meta.get("song_style", ""))
        dry_run = bool(spec.extra.get("dry_run")) if spec else None
        plan.write_text(
            render(blueprint, cues, song_style=style, dry_run=dry_run), encoding="utf-8"
        )
        return plan
    legacy = Path(work_dir) / "blueprint.yaml"
    save_blueprint(blueprint, legacy)
    return legacy


def _title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "untitled"


def _resolve_clip_paths(blueprint: Blueprint, clips_dir: Path) -> None:
    """Fill a clip's ``path`` from ``assets/clips/<id>.<ext>`` when the plan omits it."""
    if not clips_dir.is_dir():
        return
    suffixes = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
    for clip in blueprint.seedance:
        if clip.path:
            continue
        names = sorted({clip.clip, re.sub(r"(\d+)", lambda m: str(int(m.group(1))), clip.clip)})
        for name in names:
            found = next(
                (p for p in sorted(clips_dir.glob(f"{name}.*")) if p.suffix.lower() in suffixes),
                None,
            )
            if found is not None:
                clip.path = str(found)
                break


def _shot_at(shots: list[Shot], start: float) -> Shot | None:
    for shot in shots:
        if shot.t0 - 1e-6 <= start < shot.t1 - 1e-6:
            return shot
    return None


def _cues(rows: list[dict[str, str]], lyrics: LyricsDoc | None) -> list[Cue]:
    sections = {line.index: line.section for line in lyrics.lines} if lyrics else {}
    ordered = sorted(rows, key=lambda row: _num(row.get("start")))
    cues: list[Cue] = []
    for i, row in enumerate(ordered):
        index = _int(row.get("line"))
        start = _num(row.get("start"))
        if i + 1 < len(ordered):
            end = _num(ordered[i + 1].get("start"))
        else:
            end = start + 2.0
        cues.append(
            Cue(
                text=row.get("text", ""),
                start=start,
                end=max(end, start + 0.2),
                section=sections.get(index, ""),
                index=index,
            )
        )
    return cues
