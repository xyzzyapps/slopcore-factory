"""Planner: turn aligned cues into a full storyboard.

The plan is deliberately simple and deterministic:

* consecutive cues of the same section form a run;
* runs are packed into frames up to a target length, split when they exceed the
  maximum, and short frames are merged back;
* inside a frame, lines are clustered into groups (max six lines, or a break on
  a silence longer than 3.5 s);
* very short sections (intro / outro / spoken) become held-message cards
  instead of a lyric stack.

All storyboard times are absolute (seconds from the top of the song); the
compose slice converts them to frame-local time.
"""

from __future__ import annotations

import re
from collections import Counter

from .logging_setup import get_logger
from .models import Cue, FactorySpec, Frame, Group, LyricsDoc, Storyboard

log = get_logger("storyboard")

# Section-name heuristics only; they carry no song-specific copy. A storyboard
# may override them through ``spec.extra`` (see FactorySpec).
HELD_SECTIONS = {"intro", "outro", "sleep", "spoken"}

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "then",
    "than",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "for",
    "with",
    "from",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "am",
    "do",
    "does",
    "did",
    "have",
    "has",
    "had",
    "i",
    "you",
    "we",
    "they",
    "he",
    "she",
    "it",
    "me",
    "my",
    "your",
    "our",
    "their",
    "his",
    "her",
    "this",
    "that",
    "these",
    "those",
    "so",
    "not",
    "no",
    "yes",
    "all",
    "up",
    "down",
    "out",
    "you're",
    "i'm",
    "i'll",
    "don't",
    "go",
    "off",
    "can",
    "could",
    "would",
    "will",
    "just",
    "what",
    "when",
    "who",
    "more",
}


def plan_storyboard(
    spec: FactorySpec,
    lyrics: LyricsDoc,
    cues: list[Cue],
    duration: float,
    backgrounds: list | None = None,
    beat_grid=None,
    taglines: dict | None = None,
) -> Storyboard:
    """Build the storyboard for one song.

    ``taglines`` maps a section name (lower-case) to the short tag shown under a
    held-message card; it is song copy and therefore comes from the storyboard,
    never from this module.
    """
    cues = sorted(cues, key=lambda c: c.start)
    if not cues:
        raise ValueError("cannot plan a storyboard without cues")

    taglines = taglines or {}
    cuts = _frame_cuts(cues, duration, spec.split_target, spec.split_min, spec.split_max)
    frames: list[Frame] = []
    bg_list = list(backgrounds or [])

    for index, (start, end, chunk) in enumerate(cuts, start=1):
        frame_id = f"{index:02d}-f{index}"
        short = f"f{index}"
        section = _dominant_section(chunk)
        kicker = f"no. {index:02d} / {_section_label(section)}"
        groups = _groups_for_frame(frame_id, short, start, end, chunk, kicker, taglines)
        frames.append(
            Frame(
                id=frame_id,
                index=index,
                start=round(start, 3),
                duration=round(max(0.1, end - start), 3),
                groups=groups,
                background=bg_list[(index - 1) % len(bg_list)] if bg_list else None,
                kicker=kicker,
            )
        )

    storyboard = Storyboard(
        composition_id="main",
        title=spec.title,
        duration=round(duration, 3),
        width=spec.width,
        height=spec.height,
        fps=spec.fps,
        frames=frames,
        beat_grid=beat_grid,
        accent_word=_accent_word(lyrics),
    )
    log.info(
        "planned %d frames over %.3fs (accent=%r)",
        len(frames),
        storyboard.duration,
        storyboard.accent_word,
    )
    return storyboard


# ---------------------------------------------------------------------------
# Frame boundaries
# ---------------------------------------------------------------------------


def _frame_cuts(
    cues: list[Cue], duration: float, target: float, min_s: float, max_s: float
) -> list[tuple[float, float, list[Cue]]]:
    runs: list[list[Cue]] = []
    for cue in cues:
        if runs and runs[-1][-1].section == cue.section:
            runs[-1].append(cue)
        else:
            runs.append([cue])

    packed: list[tuple[float, float, list[Cue]]] = []
    cur: list[Cue] = []
    cur_start = 0.0
    for run in runs:
        if cur and ((run[0].start - cur_start) >= max_s or (cur[-1].start - cur_start) >= target):
            packed.append((cur_start, run[0].start, cur))
            cur = []
            cur_start = run[0].start
        cur.extend(run)
    if cur:
        packed.append((cur_start, duration, cur))

    # split runs that individually exceed the maximum
    final: list[tuple[float, float, list[Cue]]] = []
    for start, end, chunk in packed:
        if (end - start) <= max_s:
            final.append((start, end, chunk))
            continue
        seg_start = start
        seg: list[Cue] = []
        for cue in chunk:
            if seg and (cue.start - seg_start) >= max_s:
                final.append((seg_start, cue.start, seg))
                seg = []
                seg_start = cue.start
            seg.append(cue)
        if seg:
            final.append((seg_start, end, seg))

    # merge frames shorter than the minimum into the previous one
    merged: list[tuple[float, float, list[Cue]]] = []
    for start, end, chunk in final:
        if merged and (end - start) < min_s:
            p_start, _p_end, p_chunk = merged[-1]
            merged[-1] = (p_start, end, p_chunk + chunk)
        else:
            merged.append((start, end, chunk))
    if len(merged) > 1 and (merged[-1][1] - merged[-1][0]) < min_s:
        s, e, chunk = merged.pop()
        p_start, _p_end, p_chunk = merged[-1]
        merged[-1] = (p_start, e, p_chunk + chunk)

    # snap the last frame to the audio duration
    if merged:
        s, _e, chunk = merged[-1]
        merged[-1] = (s, duration, chunk)
    return merged


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def _groups_for_frame(
    frame_id: str,
    short: str,
    start: float,
    end: float,
    cues: list[Cue],
    kicker: str,
    taglines: dict,
) -> list[Group]:
    groups: list[Group] = []
    gi = 0
    i = 0
    n = len(cues)
    while i < n:
        j = i
        while j + 1 < n and cues[j + 1].section == cues[i].section:
            j += 1
        run = cues[i : j + 1]

        if _is_held(run):
            for k in range(i, j + 1):
                gi += 1
                g_start = max(start, cues[k].start)
                g_end = cues[k + 1].start if k + 1 < n else end
                groups.append(
                    Group(
                        id=f"{short}-g{gi}",
                        kind="held_message",
                        start=round(g_start, 3),
                        duration=round(max(2.0, g_end - g_start), 3),
                        cues=[cues[k]],
                        kicker=kicker,
                        mark=cues[k].text,
                        tag=taglines.get(cues[k].section.lower(), ""),
                    )
                )
        else:
            chunks: list[tuple[list[Cue], int]] = []
            chunk: list[Cue] = []
            last_pos = i
            for pos in range(i, j + 1):
                cue = cues[pos]
                if chunk and (len(chunk) >= 6 or cue.start - chunk[-1].end > 3.5):
                    chunks.append((chunk, last_pos))
                    chunk = []
                chunk.append(cue)
                last_pos = pos
            if chunk:
                chunks.append((chunk, last_pos))

            for chunk_cues, chunk_last in chunks:
                gi += 1
                g_start = max(start, chunk_cues[0].start - 0.12)
                g_end = cues[chunk_last + 1].start if chunk_last + 1 < n else end
                groups.append(
                    Group(
                        id=f"{short}-g{gi}",
                        kind="lyric_stack",
                        start=round(g_start, 3),
                        duration=round(max(1.5, g_end - g_start), 3),
                        cues=chunk_cues,
                        kicker=kicker,
                    )
                )
        i = j + 1
    return groups


def _is_held(run: list[Cue]) -> bool:
    """A run is a held-message card when it is a spoken section or very short."""
    if not run:
        return False
    section = run[0].section.lower()
    words = sum(len(cue.text.split()) for cue in run)
    longest = max(len(cue.text) for cue in run)
    return section in HELD_SECTIONS or (words <= 6 and longest <= 26)


def _dominant_section(cues: list[Cue]) -> str:
    return Counter(c.section for c in cues).most_common(1)[0][0] if cues else "verse"


def _section_label(section: str) -> str:
    label = re.sub(r"\s*\d+$", "", section).strip().lower()
    return label or "part"


# ---------------------------------------------------------------------------
# Accent word
# ---------------------------------------------------------------------------


def accent_word_for(lyrics: LyricsDoc) -> str | None:
    """The most-common content word, used to highlight the hook."""
    counts: Counter[str] = Counter()
    for line in lyrics.lines:
        for token in re.findall(r"[A-Za-z']+", line.text.lower()):
            word = token.strip("'")
            if len(word) >= 4 and word not in STOPWORDS:
                counts[word] += 1
    if not counts:
        return None
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return ranked[0][0]


# kept for the planner's internal call
_accent_word = accent_word_for
