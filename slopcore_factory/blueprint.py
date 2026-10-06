"""The blueprints: the machine-readable storyboard.

A :class:`Blueprint` is the creative source of truth for one video. It is what
the LLM (or the offline generator) writes, what the human edits, and what every
later stage consumes. It deliberately carries *everything* the reference
production tracked in ``shots.json``:

* chapters (the grade / accent / screen through-line),
* shots (tiling the song, with framing, action, camera, camera tier),
* lyric type placement (subtitle / coverline / masthead / mass),
* the Seedance clip list, including the audio-conditioned lipsync windows,
* assets: character canon, plate prompts, depth and tracking requests,
* animation: the named scenes per chapter (arbitrary motion graphics),
* the budget.

Nothing here knows about a particular song. Song-specific copy lives in the
artifact, never in this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .errors import ConfigError

BLUEPRINT_VERSION = 2
MOTION_TIERS = {"code", "plate25d", "seedance"}
TREATMENTS = {"loop", "slow", "pingpong", "hold", "stutter"}
TYPE_MODES = {"subtitle", "coverline", "masthead", "mass", "plate"}
POSITION_MODES = {"left", "right", "center", "lower", "upper", "bottom"}


@dataclass
class Character:
    """The recurring lead: a written canon plus reference images."""

    name: str = "lead"
    canon: str = ""
    reference_images: list[str] = field(default_factory=list)
    identity_notes: str = ""


@dataclass
class Chapter:
    """A coarse section of the video with a shared look."""

    id: str
    name: str
    t0: float
    t1: float
    grade: str = ""
    accent: str = ""
    screen: str = ""
    set: str = ""


@dataclass
class ShotType:
    """A lyric line placed on screen (the lyric-video contract)."""

    line: int
    mode: str = "subtitle"
    text: str = ""
    position: str = ""
    offset: float = 0.0  # seconds to shift this line later (negative = earlier)


@dataclass
class AssetNeeds:
    """Per-shot asset requests: the plate, its depth map, and any tracking."""

    plate: str = ""
    depth: bool = False
    tracking: list[str] = field(default_factory=list)


@dataclass
class Animation:
    """Arbitrary motion design for a shot: a named scene in the project."""

    scene: str = ""
    module: str = ""
    notes: str = ""


@dataclass
class Shot:
    """One shot: a time span with its footage, type, assets and animation."""

    id: str
    t0: float
    t1: float
    chapter: str = ""
    section: str = ""
    framing: str = ""
    action: str = ""
    camera: str = ""
    motion_tier: str = "code"  # code | plate25d | seedance
    lead_on_screen: bool = False
    seedance_clip: str | None = None
    media: str = ""  # explicit background override (image or treated clip)
    treatment: str = "loop"  # loop | slow | pingpong | hold | stutter
    treatment_value: float = 0.0  # slow factor / trim seconds (0 = auto)
    detections: list[dict] = field(default_factory=list)  # YOLO boxes, shot-local times
    lines: list[int] = field(default_factory=list)
    type: list[ShotType] = field(default_factory=list)
    chrome: str = ""
    accent: str = ""
    screen: str = ""
    lift: float = 0.0
    meme_visual: str = ""
    assets: AssetNeeds = field(default_factory=AssetNeeds)
    animation: Animation = field(default_factory=Animation)
    notes: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.t1 - self.t0)


@dataclass
class SeedanceClip:
    """A generated moving shot. Audio-conditioned when ``sing`` is true."""

    clip: str
    duration: float
    prompt: str = ""
    plate: str = ""
    shots: list[str] = field(default_factory=list)
    song_t0: float = 0.0
    words: str = ""
    sing: bool = False
    cover_of: str = ""
    path: str = ""  # local file once generated (or a dry-run placeholder)
    use_reference: bool = True  # send the character reference images with this clip


@dataclass
class Plate:
    """A still to generate (the plate every moving shot starts from)."""

    plate: str
    set: str = ""
    prompt: str = ""
    id_prompt: str = ""
    aspect: str = "16:9"
    depth: bool = False
    used_by: list[str] = field(default_factory=list)


@dataclass
class LipsyncWindow:
    """A window the lead visibly sings, to be audio-conditioned.

    Windows start in a word gap, never mid-word, and quote the exact words sung
    inside them so the generator can be checked against the real vocal.
    """

    clip: str
    song_t0: float
    duration: float
    words: str
    framing: str = ""
    cover_of: str = ""


@dataclass
class AnimationScene:
    """A named motion-design scene spanning a chapter's time range."""

    id: str
    chapter: str
    t0: float
    t1: float
    module: str = ""
    notes: str = ""


@dataclass
class Budgets:
    """Planned spend. ``cap_usd`` is the hard ceiling enforced at submit time."""

    cap_usd: float = 0.0
    seedance_seconds: float = 0.0
    seedance_quality: str = "720p"
    seedance_usd: float = 0.0
    suno_usd: float = 0.0
    images_usd: float = 0.0
    total_usd: float = 0.0
    retry_buffer: float = 1.35  # planning multiplier; 1.0 = one-shot, no retry budget


@dataclass
class Blueprint:
    """The full storyboard for one video."""

    title: str
    duration: float
    lyrics_path: str = ""
    audio: str = ""
    width: int = 1280
    height: int = 720
    fps: int = 30
    theme: str = "broadside"
    version: int = BLUEPRINT_VERSION
    character: Character = field(default_factory=Character)
    chapters: list[Chapter] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    seedance: list[SeedanceClip] = field(default_factory=list)
    plates: list[Plate] = field(default_factory=list)
    lipsync: list[LipsyncWindow] = field(default_factory=list)
    animation: list[AnimationScene] = field(default_factory=list)
    budgets: Budgets = field(default_factory=Budgets)
    meta: dict = field(default_factory=dict)

    # -- derived ---------------------------------------------------------

    @property
    def sung_seconds(self) -> float:
        return round(sum(window.duration for window in self.lipsync), 3)

    def chapter_ids(self) -> list[str]:
        return [chapter.id for chapter in self.chapters]

    def shot_ids(self) -> list[str]:
        return [shot.id for shot in self.shots]


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def to_dict(blueprint: Blueprint) -> dict:
    return asdict(blueprint)


def _character(data: dict | None) -> Character:
    return Character(
        **{k: v for k, v in (data or {}).items() if k in Character.__dataclass_fields__}
    )


def _chapter(data: dict) -> Chapter:
    return Chapter(**{k: v for k, v in data.items() if k in Chapter.__dataclass_fields__})


def _shot_type(data: dict) -> ShotType:
    return ShotType(**{k: v for k, v in data.items() if k in ShotType.__dataclass_fields__})


def _assets(data: dict | None) -> AssetNeeds:
    return AssetNeeds(
        **{k: v for k, v in (data or {}).items() if k in AssetNeeds.__dataclass_fields__}
    )


def _animation(data: dict | None) -> Animation:
    return Animation(
        **{k: v for k, v in (data or {}).items() if k in Animation.__dataclass_fields__}
    )


def _shot(data: dict) -> Shot:
    payload = {k: v for k, v in data.items() if k in Shot.__dataclass_fields__}
    payload["type"] = [_shot_type(t) for t in data.get("type", [])]
    payload["assets"] = _assets(data.get("assets"))
    payload["animation"] = _animation(data.get("animation"))
    return Shot(**payload)


def _seedance(data: dict) -> SeedanceClip:
    return SeedanceClip(**{k: v for k, v in data.items() if k in SeedanceClip.__dataclass_fields__})


def _plate(data: dict) -> Plate:
    return Plate(**{k: v for k, v in data.items() if k in Plate.__dataclass_fields__})


def _lipsync(data: dict) -> LipsyncWindow:
    return LipsyncWindow(
        **{k: v for k, v in data.items() if k in LipsyncWindow.__dataclass_fields__}
    )


def _scene(data: dict) -> AnimationScene:
    return AnimationScene(
        **{k: v for k, v in data.items() if k in AnimationScene.__dataclass_fields__}
    )


def _budgets(data: dict | None) -> Budgets:
    return Budgets(**{k: v for k, v in (data or {}).items() if k in Budgets.__dataclass_fields__})


def from_dict(data: dict) -> Blueprint:
    """Build a blueprint from a plain dict (LLM output or YAML)."""
    return Blueprint(
        title=str(data.get("title", "untitled")),
        duration=float(data.get("duration", 0.0)),
        lyrics_path=str(data.get("lyrics_path", "")),
        audio=str(data.get("audio", "")),
        width=int(data.get("width", 1280)),
        height=int(data.get("height", 720)),
        fps=int(data.get("fps", 30)),
        theme=str(data.get("theme", "broadside")),
        version=int(data.get("version", BLUEPRINT_VERSION)),
        character=_character(data.get("character")),
        chapters=[_chapter(c) for c in data.get("chapters", [])],
        shots=[_shot(s) for s in data.get("shots", [])],
        seedance=[_seedance(s) for s in data.get("seedance", [])],
        plates=[_plate(p) for p in data.get("plates", [])],
        lipsync=[_lipsync(w) for w in data.get("lipsync", [])],
        animation=[_scene(s) for s in data.get("animation", [])],
        budgets=_budgets(data.get("budgets")),
        meta=dict(data.get("meta", {})),
    )


def save_blueprint(blueprint: Blueprint, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(to_dict(blueprint), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def load_blueprint(path: Path) -> Blueprint:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"blueprint not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"blueprint is not a mapping: {path}")
    return from_dict(data)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_blueprint(blueprint: Blueprint, tolerance: float = 0.02) -> list[str]:
    """Return a list of human-readable problems (empty means valid)."""
    problems: list[str] = []
    if blueprint.duration <= 0:
        problems.append("duration must be positive")
    if not blueprint.shots:
        problems.append("no shots")
        return problems

    # ids unique across the categories that reference each other
    for label, ids in (
        ("shot", blueprint.shot_ids()),
        ("chapter", blueprint.chapter_ids()),
        ("plate", [p.plate for p in blueprint.plates]),
        ("clip", [c.clip for c in blueprint.seedance]),
    ):
        seen = set()
        for value in ids:
            if value in seen:
                problems.append(f"duplicate {label} id: {value}")
            seen.add(value)

    # shots tile the timeline with no gaps or overlaps
    shots = sorted(blueprint.shots, key=lambda s: s.t0)
    if abs(shots[0].t0) > tolerance:
        problems.append(f"first shot starts at {shots[0].t0}, expected 0")
    for current, following in zip(shots, shots[1:], strict=False):
        if abs(following.t0 - current.t1) > tolerance:
            problems.append(
                f"gap/overlap between {current.id} (end {current.t1}) and "
                f"{following.id} (start {following.t0})"
            )
    if abs(shots[-1].t1 - blueprint.duration) > tolerance:
        problems.append(f"last shot ends at {shots[-1].t1}, expected {blueprint.duration}")

    # every shot's tier is known, and seedance shots name a clip
    clip_ids = {clip.clip for clip in blueprint.seedance}
    for shot in blueprint.shots:
        if shot.motion_tier not in MOTION_TIERS:
            problems.append(f"{shot.id}: unknown motion_tier {shot.motion_tier!r}")
        if shot.motion_tier == "seedance" and shot.seedance_clip not in clip_ids:
            problems.append(f"{shot.id}: seedance shot without a known clip")
        if shot.treatment not in TREATMENTS:
            problems.append(f"{shot.id}: unknown treatment {shot.treatment!r}")

    # type modes + positions
    for shot in blueprint.shots:
        for entry in shot.type:
            if entry.mode not in TYPE_MODES:
                problems.append(f"{shot.id}: unknown type mode {entry.mode!r}")
            if entry.position and entry.position not in POSITION_MODES:
                problems.append(f"{shot.id}: unknown type position {entry.position!r}")

    # lipsync windows are inside the song and lie on sung clips
    for window in blueprint.lipsync:
        if window.song_t0 < 0 or window.song_t0 + window.duration > blueprint.duration + tolerance:
            problems.append(f"lipsync {window.clip}: window outside the song")
        if window.clip not in clip_ids:
            problems.append(f"lipsync {window.clip}: no matching seedance clip")

    return problems
