"""Build a :class:`~slopcore_factory.models.FactorySpec` from inputs.

Sources, in precedence order: explicit CLI values, then a ``song.json`` file in
the song folder, then the lyrics front-matter, then defaults.

Front-matter is the same YAML block used by ``BRIEF.md`` in the original project
(``---`` fenced at the top of the lyrics file), so the two stay compatible.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .errors import ConfigError
from .models import FactorySpec

DEFAULTS = {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "language": "en",
    "whisper_model": "small.en",
    "hyperframes_version": "0.8.116",
    "theme": "broadside",
    "vocal_gender": "f",
    "split_target": 26.0,
    "split_min": 8.0,
    "split_max": 45.0,
}


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Split a leading ``---`` YAML block from the body.

    Returns ``(meta, body)``; ``meta`` is empty when there is no front-matter.
    """
    stripped = text.lstrip("\ufeff \t\r\n")
    if not stripped.startswith("---"):
        return {}, text
    lines = stripped.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    body = "\n".join(lines[end + 1 :])
    return meta, body


def _aspect_to_wh(aspect: str) -> tuple[int, int]:
    try:
        w, h = aspect.lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return DEFAULTS["width"], DEFAULTS["height"]


def build_spec(
    lyrics_path: Path,
    out_dir: Path,
    *,
    audio_path: Path | None = None,
    transcript_path: Path | None = None,
    backgrounds: list[Path] | None = None,
    generate_song: bool = False,
    generate_clips: bool = False,
    duration: float | None = None,
    title: str | None = None,
    overrides: dict | None = None,
) -> FactorySpec:
    """Assemble a spec from a lyrics file and explicit options."""
    lyrics_path = Path(lyrics_path)
    if not lyrics_path.exists():
        raise ConfigError(f"lyrics file not found: {lyrics_path}")

    meta: dict = {}
    cfg: dict = {}
    song_json = lyrics_path.parent / "song.json"
    if song_json.exists():
        cfg = yaml.safe_load(song_json.read_text(encoding="utf-8")) or {}

    from .lyrics import parse_lyrics  # local import avoids a cycle at module load

    doc = parse_lyrics(lyrics_path)
    meta = doc.meta
    merged = {**DEFAULTS, **meta, **cfg, **(overrides or {})}

    aspect = merged.get("aspect") or f"{DEFAULTS['width']}x{DEFAULTS['height']}"
    width, height = _aspect_to_wh(aspect)
    bg_list = [Path(p) for p in (backgrounds or [])]

    # Song-specific creative direction travels in ``extra`` (from song.json or
    # the lyrics front-matter); nothing here is hardcoded to a particular song.
    extra_keys = (
        "taglines",
        "hook_sections",
        "negative_tags",
        "style",
        "suno_take",
        "budget_usd",
        "brief",
        "dry_run",
        "song_backend",
        "song_command",
        "supersede_reason",
        "seed",
    )
    extra = {key: merged[key] for key in extra_keys if key in merged}

    resolved_title = title or merged.get("title") or doc.title or lyrics_path.stem
    song_id = merged.get("song_id") or _slug(resolved_title)

    return FactorySpec(
        song_id=song_id,
        title=resolved_title,
        lyrics_path=lyrics_path,
        out_dir=Path(out_dir),
        audio_path=Path(audio_path) if audio_path else _find_audio(lyrics_path.parent),
        transcript_path=(
            Path(transcript_path)
            if transcript_path
            else _first_existing(lyrics_path.parent, "transcript.json")
        ),
        backgrounds=bg_list,
        generate_song=generate_song,
        generate_clips=generate_clips,
        duration=duration if duration is not None else _maybe_float(merged.get("length_sec")),
        width=width,
        height=height,
        fps=int(merged.get("fps", DEFAULTS["fps"])),
        language=str(merged.get("language", DEFAULTS["language"])),
        whisper_model=str(merged.get("whisper_model", DEFAULTS["whisper_model"])),
        hyperframes_version=str(merged.get("hyperframes_version", DEFAULTS["hyperframes_version"])),
        theme_name=str(merged.get("theme", DEFAULTS["theme"])),
        suno_style_path=_first_existing(lyrics_path.parent, "prompts/suno-style.md"),
        suno_title=str(merged.get("suno_title") or resolved_title).upper(),
        vocal_gender=str(merged.get("vocal_gender", DEFAULTS["vocal_gender"])),
        split_target=float(merged.get("split_target", DEFAULTS["split_target"])),
        split_min=float(merged.get("split_min", DEFAULTS["split_min"])),
        split_max=float(merged.get("split_max", DEFAULTS["split_max"])),
        extra=extra,
    )


def _slug(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "song"


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).rstrip("s"))
    except ValueError:
        return None


def _first_existing(base: Path, *rels: str) -> Path | None:
    for rel in rels:
        candidate = base / rel
        if candidate.exists():
            return candidate
    return None


def _find_audio(base: Path) -> Path | None:
    for name in ("bgm.mp3", "song.mp3", "audio.mp3", "song.wav", "audio.wav"):
        candidate = base / "assets" / name
        if candidate.exists():
            return candidate
        candidate = base / name
        if candidate.exists():
            return candidate
    return None
