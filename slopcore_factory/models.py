"""Data structures for slopcore-factory.

Model the data before the code (planning rule): every stage of the pipeline
reads and writes one of these plain dataclasses, so the stages stay decoupled
and independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Lyrics / transcript
# ---------------------------------------------------------------------------


@dataclass
class LyricLine:
    """A single lyric line belonging to a named section."""

    text: str
    section: str
    index: int  # global line index across the whole song
    start: float | None = None  # seconds, filled by the align stage
    end: float | None = None

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class LyricSection:
    """A block such as [Verse 1] or [Chorus] holding ordered lines."""

    name: str
    lines: list[LyricLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def word_count(self) -> int:
        return sum(line.word_count for line in self.lines)


@dataclass
class LyricsDoc:
    """A parsed lyrics document: title, optional front-matter, and sections."""

    title: str
    sections: list[LyricSection]
    raw: str = ""
    meta: dict = field(default_factory=dict)
    source: Path | None = None

    @property
    def lines(self) -> list[LyricLine]:
        return [line for section in self.sections for line in section.lines]

    @property
    def text(self) -> str:
        return "\n".join(section.text for section in self.sections)

    @property
    def hint(self) -> str:
        """A single-space one-line hint used to prime the transcriber."""
        return " ".join(" ".join(line.text.split()) for line in self.lines)


@dataclass
class Word:
    """A word with word-level timing from the transcriber."""

    word: str
    start: float
    end: float


@dataclass
class Transcript:
    """Word-level transcript of the audio track."""

    engine: str
    duration: float
    words: list[Word] = field(default_factory=list)


@dataclass
class Cue:
    """A lyric line aligned to the audio timeline."""

    text: str
    start: float
    end: float
    section: str
    index: int  # global line index, matches LyricLine.index
    words: list[Word] = field(default_factory=list)
    position: str = ""  # per-shot placement override (see blueprint POSITION_MODES)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


# ---------------------------------------------------------------------------
# Music grid
# ---------------------------------------------------------------------------


@dataclass
class BeatGrid:
    """Beat / downbeat timing grid for the track."""

    bpm: float
    duration: float
    beats: list[float] = field(default_factory=list)
    downbeats: list[float] = field(default_factory=list)

    @property
    def has_grid(self) -> bool:
        return bool(self.downbeats)


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


@dataclass
class Theme:
    """A visual preset: palette, type, fonts and treatment values."""

    name: str
    bg: str
    accent: str
    cream: str
    font_display: str
    font_body: str
    font_mono: str
    fonts: dict[str, Path] = field(default_factory=dict)
    grain_opacity: float = 0.06
    scrim_top: str = "rgba(17, 17, 17, 0)"
    scrim_bottom: str = "rgba(17, 17, 17, 0.72)"
    scrim_stop: str = "38%"
    line_size: float = 5.6  # cqw
    word_size: float = 12.0  # cqw
    letter_spacing: float = -0.02


# ---------------------------------------------------------------------------
# Storyboard
# ---------------------------------------------------------------------------


@dataclass
class Group:
    """A timed cluster of lyric lines (or a held message) inside a frame."""

    id: str
    kind: str  # "lyric_stack" | "held_message"
    start: float
    duration: float
    cues: list[Cue] = field(default_factory=list)
    kicker: str = ""
    mark: str | None = None
    tag: str | None = None


@dataclass
class Scene:
    """An arbitrary motion-design layer inside a frame.

    ``kind`` is a built-in scene name (``bars`` / ``marquee`` / ``scan``); when
    ``module`` is set the scene is a user-authored HTML fragment copied into the
    project's ``scenes/`` directory.
    """

    id: str
    kind: str = ""
    t0: float = 0.0
    t1: float = 0.0
    params: dict = field(default_factory=dict)
    module: str = ""
    markup: str = ""


@dataclass
class Frame:
    """A sub-composition spanning a slice of the timeline."""

    id: str
    index: int
    start: float
    duration: float
    groups: list[Group] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    background: Path | None = None
    kicker: str = ""


@dataclass
class Storyboard:
    """The full plan for one song: canvas + ordered frames."""

    composition_id: str
    title: str
    duration: float
    width: int
    height: int
    fps: int
    frames: list[Frame] = field(default_factory=list)
    beat_grid: BeatGrid | None = None
    accent_word: str | None = None  # most-common content word, highlighted in the type


# ---------------------------------------------------------------------------
# Factory spec / run bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class FactorySpec:
    """Everything a run needs. Built by :mod:`slopcore_factory.config`."""

    song_id: str
    title: str
    lyrics_path: Path
    out_dir: Path  # the generated HyperFrames project directory
    audio_path: Path | None = None
    transcript_path: Path | None = None
    backgrounds: list[Path] = field(default_factory=list)
    generate_song: bool = False
    generate_clips: bool = False
    duration: float | None = None
    width: int = 1280
    height: int = 720
    fps: int = 30
    language: str = "en"
    whisper_model: str = "small.en"
    hyperframes_version: str = "0.8.116"
    theme_name: str = "broadside"
    suno_style_path: Path | None = None
    suno_title: str | None = None
    vocal_gender: str = "f"
    split_target: float = 26.0
    split_min: float = 8.0
    split_max: float = 45.0
    extra: dict = field(default_factory=dict)


@dataclass
class Artifact:
    """A named output produced by a stage."""

    stage: str
    kind: str
    path: Path


@dataclass
class StageResult:
    """Outcome of one pipeline stage."""

    stage: str
    status: str  # PENDING | RUNNING | DONE | FAILED | SKIPPED
    detail: str = ""
    artifacts: list[Artifact] = field(default_factory=list)
    cache_key: str = ""
