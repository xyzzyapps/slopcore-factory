"""Storyboard (blueprint) generation.

Two paths:

* :func:`generate_offline` — deterministic, free, always available. It reuses the
  tested planner and emits a valid lyric-video blueprint.
* :func:`generate_with_llm` — asks a LangChain chat model for a full blueprint
  (chapters, shots, type modes, camera, clip picks, assets, animation, lipsync),
  validates it, and retries once with the validator's complaints. This is the
  small version of the reference production's multi-director workflow.

The LLM never sees or invents song facts beyond the lyrics it is given; the
prompt tells it to derive everything from the lyrics and the brief.
"""

from __future__ import annotations

import json
import re

import yaml

from .blueprint import (
    Animation,
    AnimationScene,
    Blueprint,
    Chapter,
    Shot,
    ShotType,
    from_dict,
    validate_blueprint,
)
from .budget import apply_estimate
from .errors import BlueprintError, LLMError
from .logging_setup import get_logger
from .models import Cue, FactorySpec, LyricsDoc
from .storyboard import plan_storyboard

log = get_logger("blueprint_gen")

HOOK_SECTIONS = {"chorus", "final chorus", "drop"}
MAX_HOOK_WORDS = 4


def _default_scene(frame) -> str:
    """Pick a built-in motion layer for a frame: bars on hooks, scan elsewhere."""
    hook = any(cue.section.lower() in HOOK_SECTIONS for group in frame.groups for cue in group.cues)
    return "bars" if hook else "scan"


def generate_offline(
    spec: FactorySpec,
    lyrics: LyricsDoc,
    cues: list[Cue],
    duration: float,
    theme_name: str = "broadside",
) -> Blueprint:
    """Build a valid lyric-video blueprint with no external calls."""
    plan = plan_storyboard(spec, lyrics, cues, duration, taglines={})
    blueprint = Blueprint(
        title=lyrics.title,
        duration=round(duration, 3),
        lyrics_path=str(spec.lyrics_path),
        audio=str(spec.audio_path or ""),
        width=spec.width,
        height=spec.height,
        fps=spec.fps,
        theme=theme_name,
    )

    for frame in plan.frames:
        blueprint.chapters.append(
            Chapter(
                id=frame.id,
                name=frame.kicker,
                t0=round(frame.start, 3),
                t1=round(frame.start + frame.duration, 3),
                set="",
            )
        )
        entries: list[ShotType] = []
        for group in frame.groups:
            for cue in group.cues:
                mode = (
                    "masthead"
                    if cue.section.lower() in HOOK_SECTIONS
                    and len(cue.text.split()) <= MAX_HOOK_WORDS
                    else "subtitle"
                )
                entries.append(ShotType(line=cue.index, mode=mode, text=cue.text, position="lower"))
        blueprint.shots.append(
            Shot(
                id=frame.id,
                t0=round(frame.start, 3),
                t1=round(frame.start + frame.duration, 3),
                chapter=frame.id,
                section=frame.kicker,
                framing="medium",
                action="lyric stack",
                camera="locked",
                motion_tier="code",
                lines=[cue.index for group in frame.groups for cue in group.cues],
                type=entries,
                chrome=frame.kicker,
                animation=Animation(scene=_default_scene(frame)),
            )
        )
        blueprint.animation.append(
            AnimationScene(
                id=f"scene-{frame.id}",
                chapter=frame.id,
                t0=round(frame.start, 3),
                t1=round(frame.start + frame.duration, 3),
                notes="default lyric motion",
            )
        )

    apply_estimate(blueprint)
    problems = validate_blueprint(blueprint)
    if problems:
        raise BlueprintError("offline blueprint invalid: " + "; ".join(problems))
    return blueprint


def generate(
    spec: FactorySpec,
    lyrics: LyricsDoc,
    cues: list[Cue],
    duration: float,
    theme_name: str = "broadside",
    use_llm: bool = False,
    brief: str = "",
) -> Blueprint:
    """Generate a blueprint, via the LLM when asked and configured."""
    if use_llm:
        from .llm import get_llm

        llm = get_llm()
        if llm is None:
            raise LLMError(
                "no LLM configured; set SLOPCORE_FACTORY_LLM (e.g. anthropic:claude-sonnet-4-5)"
            )
        return generate_with_llm(llm, spec, lyrics, cues, duration, theme_name, brief)
    return generate_offline(spec, lyrics, cues, duration, theme_name)


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------

SCHEMA_HINT = """\
Return ONE YAML document, no prose, with this shape (omit fields you cannot fill):

version: 2
title: <string>
duration: <seconds, number>
width: 1280
height: 720
fps: 30
theme: broadside
audio: <relative path>
character:
  name: lead
  canon: <written description used verbatim in every image/video prompt>
  reference_images: [<paths>]
  identity_notes: <how to keep the face consistent>
chapters:
  - {id: ch1, name: <string>, t0: <s>, t1: <s>, grade: <string>, accent: <hex>, screen: <string>, set: <string>}
shots:
  - id: s001
    t0: <s>
    t1: <s>
    chapter: ch1
    section: <lyric section>
    framing: <ECU|CU|MCU|MS|FS|WS|EWS>
    action: <what happens>
    camera: <move>
    motion_tier: <code|plate25d|seedance>
    lead_on_screen: <bool>
    seedance_clip: <clip id or null>
    lines: [<lyric line indices this shot covers>]
    type:
      - {line: <int>, mode: <subtitle|coverline|masthead|mass|plate>, text: <string>, position: <left|right|center|lower|upper>}
    chrome: <string>
    accent: <hex>
    screen: <string>
    lift: <0..1>
    meme_visual: <string>
    assets: {plate: <plate id or "">, depth: <bool>, tracking: [<strings>]}
    animation: {scene: <scene id>, module: <path>, notes: <string>}
    notes: <string>
seedance:
  - {clip: sd01, duration: <s>, prompt: <string>, plate: <plate id>, shots: [s001], song_t0: <s>, words: <exact sung words in the window>, sing: <bool>, cover_of: <clip id or "">}
plates:
  - {plate: <id>, set: <string>, prompt: <string>, id_prompt: <string>, aspect: "16:9", depth: <bool>, used_by: [s001]}
lipsync:
  - {clip: sd01, song_t0: <s>, duration: <s>, words: <exact words>, framing: <string>, cover_of: <clip id or "">}
animation:
  - {id: scene-ch1, chapter: ch1, t0: <s>, t1: <s>, module: <path>, notes: <string>}
budgets: {cap_usd: <number>, seedance_quality: 720p}
meta: {}
"""


def build_prompt(lyrics: LyricsDoc, cues: list[Cue], duration: float, brief: str) -> str:
    """The single-shot prompt: brief + lyrics + word timings + the schema."""
    lyric_block = lyrics.text
    timing = [
        {"line": cue.index, "text": cue.text, "start": cue.start, "end": cue.end} for cue in cues
    ]
    return (
        "You are the storyboard director for a music video.\n"
        "Board the ENTIRE song with no gaps: shots must tile 0..duration exactly, "
        "and every lyric line must appear in exactly one shot's `type` list.\n"
        "Derive everything from the lyrics, the brief and the timings below. Do not "
        "invent facts about the song; do not reference any other project.\n"
        "Place the lead on screen for at least 60% of the runtime when the brief asks "
        "for a performer. Use motion_tier 'seedance' only for shots that need moving "
        "footage or visible singing, and give each such shot a `seedance` clip. For "
        "every sung window the lead is on camera, add a `lipsync` entry whose clip "
        "matches, that starts in a gap between words, and whose `words` are the exact "
        "words sung in it.\n"
        "Keep the budget honest: seedance seconds should fit the cap.\n\n"
        f"TITLE: {lyrics.title}\n"
        f"BRIEF:\n{brief or '(none)'}\n\n"
        f"DURATION: {duration:.3f} s\n\n"
        f"LYRICS:\n{lyric_block}\n\n"
        f"WORD TIMINGS (line index, text, start, end):\n{json.dumps(timing)}\n\n"
        f"{SCHEMA_HINT}"
    )


def extract_yaml(text: str) -> str:
    """Pull a YAML document out of an LLM reply (tolerates code fences)."""
    fenced = re.search(r"```(?:ya?ml)?\n(.*?)```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def generate_with_llm(
    llm,
    spec: FactorySpec,
    lyrics: LyricsDoc,
    cues: list[Cue],
    duration: float,
    theme_name: str,
    brief: str = "",
) -> Blueprint:
    """Ask the model for a blueprint; validate and retry once on failure."""
    prompt = build_prompt(lyrics, cues, duration, brief)
    last_problems: list[str] = []
    for attempt in range(2):
        message = prompt
        if last_problems:
            message += (
                "\n\nYour previous attempt failed validation. Fix ALL of these and "
                "return the whole YAML again:\n- " + "\n- ".join(last_problems)
            )
        log.info("requesting blueprint from LLM (attempt %d)", attempt + 1)
        response = llm.invoke(message)
        text = getattr(response, "content", str(response))
        try:
            data = yaml.safe_load(extract_yaml(text)) or {}
            blueprint = from_dict(data)
        except Exception as exc:  # noqa: BLE001 - retry with the parse error
            last_problems = [f"could not parse YAML: {exc}"]
            continue

        # keep the canvas/theme authoritative from the spec
        blueprint.width = spec.width
        blueprint.height = spec.height
        blueprint.fps = spec.fps
        blueprint.theme = theme_name
        blueprint.duration = blueprint.duration or duration
        blueprint.audio = blueprint.audio or str(spec.audio_path or "")
        blueprint.lyrics_path = str(spec.lyrics_path)
        if not blueprint.budgets.cap_usd:
            blueprint.budgets.cap_usd = float(spec.extra.get("budget_usd", 0) or 0)
        apply_estimate(blueprint)

        problems = validate_blueprint(blueprint)
        if not problems:
            log.info("LLM blueprint valid: %d shots", len(blueprint.shots))
            return blueprint
        last_problems = problems
        log.warning("LLM blueprint invalid (%d problems), retrying", len(problems))

    raise BlueprintError(
        "LLM could not produce a valid blueprint:\n- " + "\n- ".join(last_problems)
    )


__all__ = [
    "generate",
    "generate_offline",
    "generate_with_llm",
    "build_prompt",
    "extract_yaml",
]
