"""Word-level transcription and lyric alignment.

Two steps, two responsibilities:
1. :class:`WhisperTranscriber` produces word timings with faster-whisper,
   primed with the known lyrics so it does not wander.
2. :func:`align_cues` snaps each known lyric line onto its first matching word,
   filling any unmatched lines by interpolation so the timeline is always
   monotonic and complete.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from .errors import AlignmentError
from .interfaces import Aligner, Transcriber
from .logging_setup import get_logger
from .models import Cue, LyricsDoc, Transcript, Word

log = get_logger("timing")

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def normalize(token: str) -> str:
    """Lower-case and strip punctuation; empty string when nothing remains."""
    return " ".join(_TOKEN_RE.findall(token.lower()))


class WhisperTranscriber(Transcriber):
    """faster-whisper transcription with word timestamps."""

    def __init__(
        self,
        model_name: str = "small.en",
        language: str = "en",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self.model_name = model_name
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load(self):  # pragma: no cover - heavy import guarded for tests
        if self._model is None:
            from faster_whisper import WhisperModel

            log.info(
                "loading whisper model %s (%s/%s)", self.model_name, self.device, self.compute_type
            )
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(self, audio: Path, lyrics: LyricsDoc, duration: float) -> Transcript:
        from faster_whisper import decode_audio

        audio = Path(audio)
        if not audio.exists():
            raise AlignmentError(f"audio not found for transcription: {audio}")

        samples = decode_audio(str(audio), sampling_rate=16000)
        model = self._load()
        segments, info = model.transcribe(
            samples,
            language=self.language,
            word_timestamps=True,
            vad_filter=False,
            initial_prompt=lyrics.hint,
            temperature=0.0,
            beam_size=5,
        )

        words: list[Word] = []
        for segment in segments:
            for word in segment.words or []:
                token = word.word.strip()
                if token:
                    words.append(Word(token, round(word.start, 3), round(word.end, 3)))

        measured = round(len(samples) / 16000, 3)
        log.info("transcribed %s: %d words, %.3fs", audio.name, len(words), measured)
        return Transcript(
            engine=f"faster-whisper {self.model_name}", duration=measured, words=words
        )


class LineAligner(Aligner):
    """Snap lyric lines onto transcript words, monotonically."""

    def __init__(self, min_ratio: float = 0.6, window: int = 90, min_gap: float = 0.35) -> None:
        self.min_ratio = min_ratio
        self.window = window
        self.min_gap = min_gap

    def align(self, lyrics: LyricsDoc, transcript: Transcript) -> list[Cue]:
        return align_cues(
            lyrics,
            transcript,
            min_ratio=self.min_ratio,
            window=self.window,
            min_gap=self.min_gap,
        )


def load_transcript_file(path: Path) -> Transcript | None:
    """Read a transcript from disk, accepting either factory or whisper shape.

    Handles this package's ``{"engine","duration","words"}`` and the
    ``{"segments":[{"words":[...]}]}`` shape written by the original project's
    ``transcribe_all.py``. Returns ``None`` when no words can be read.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    words: list[Word] = []
    for entry in data.get("words", []) or []:
        words.append(Word(entry["word"], float(entry["start"]), float(entry["end"])))
    if not words:
        for segment in data.get("segments", []) or []:
            for entry in segment.get("words", []) or []:
                words.append(Word(entry["word"], float(entry["start"]), float(entry["end"])))
    if not words:
        return None

    duration = float(data.get("duration") or words[-1].end)
    return Transcript(engine=str(data.get("engine", "file")), duration=duration, words=words)


def align_cues(
    lyrics: LyricsDoc,
    transcript: Transcript,
    min_ratio: float = 0.6,
    window: int = 90,
    min_gap: float = 0.35,
) -> list[Cue]:
    """Align every lyric line to a start time.

    Unmatched lines are interpolated between their nearest resolved neighbours
    (weighted by character length) so cues are complete, ordered and within the
    audio duration.
    """
    lines = lyrics.lines
    if not lines:
        raise AlignmentError("no lyric lines to align")

    duration = transcript.duration or (transcript.words[-1].end if transcript.words else 0.0)
    tokens = [(normalize(w.word), w.start, w.end) for w in transcript.words]
    tokens = [t for t in tokens if t[0]]

    resolved: dict[int, float] = {}
    cursor = 0
    for line in lines:
        words = [normalize(t) for t in line.text.split() if normalize(t)]
        if not words or not tokens:
            continue
        first = words[0]
        end = min(len(tokens), cursor + window)
        best_index = -1
        best_score = 0.0
        for j in range(cursor, end):
            score = difflib.SequenceMatcher(None, first, tokens[j][0]).ratio()
            if score > best_score:
                best_score = score
                best_index = j
        if best_index >= 0 and best_score >= min_ratio:
            resolved[line.index] = tokens[best_index][1]
            cursor = best_index + 1

    if not resolved:
        raise AlignmentError(
            "no lyric line could be matched to the transcript; check the language/model"
        )

    starts = _interpolate(lines, resolved, duration, min_gap)

    cues: list[Cue] = []
    for i, line in enumerate(lines):
        start = starts[i]
        if i + 1 < len(lines):
            end_time = max(start + 0.4, starts[i + 1] - 0.05)
        else:
            end_time = min(duration, start + 2.5) if duration else start + 2.5
        span = [w for w in transcript.words if start - 0.05 <= w.start < end_time]
        cues.append(
            Cue(
                text=line.text,
                start=round(start, 3),
                end=round(end_time, 3),
                section=line.section,
                index=line.index,
                words=span,
            )
        )

    log.info("aligned %d/%d lines to word timings", len(resolved), len(lines))
    return cues


def _interpolate(
    lines: list, resolved: dict[int, float], duration: float, min_gap: float
) -> list[float]:
    """Return one start time per line, in order, within ``[0, duration]``."""
    n = len(lines)
    starts: list[float | None] = [resolved.get(line.index) for line in lines]
    known = [i for i in range(n) if starts[i] is not None]
    known.sort(key=lambda i: starts[i])  # ensure monotonic by value

    # Force monotonic ordering of the known anchors.
    last = -1.0
    for i in known:
        value = max(float(starts[i]), last + min_gap)  # type: ignore[arg-type]
        starts[i] = value
        last = value

    # Fill the head.
    first_known = known[0]
    for i in range(first_known):
        starts[i] = max(0.0, starts[first_known] - (first_known - i) * 0.6)  # type: ignore[operator]

    # Fill gaps between anchors by character weight.
    for a, b in zip(known, known[1:], strict=False):
        gap = starts[b] - starts[a]  # type: ignore[operator]
        weights = [max(1, len(lines[k].text)) for k in range(a, b + 1)]
        total = sum(weights)
        acc = 0
        for k in range(a, b + 1):
            if starts[k] is None:
                starts[k] = starts[a] + gap * (acc / total)  # type: ignore[operator]
            acc += weights[k - a]

    # Fill the tail.
    last_known = known[-1]
    tail_span = max(0.0, (duration or starts[last_known] + 2.0) - starts[last_known])  # type: ignore[operator]
    remaining = n - last_known - 1
    step = min(1.2, tail_span / (remaining + 1)) if remaining else 0.0
    for k in range(last_known + 1, n):
        starts[k] = starts[last_known] + step * (k - last_known)  # type: ignore[operator]

    # Guarantee strictly increasing and non-negative.
    out: list[float] = []
    prev = -min_gap
    for value in starts:
        v = max(0.0, float(value if value is not None else 0.0), prev + min_gap)
        if duration:
            v = min(v, max(0.0, duration - 0.1))
        out.append(round(v, 3))
        prev = v
    return out
