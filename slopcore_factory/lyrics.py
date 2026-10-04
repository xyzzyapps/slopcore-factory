"""Parse a lyrics document into sections and lines.

Accepts the same shape used by ``please-continue-video/lyrics.md``: optional
``---`` YAML front-matter, a ``# Title`` heading, prose, and a fenced code block
holding ``[Section]`` headers and lyric lines.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import parse_front_matter
from .errors import LyricsParseError
from .logging_setup import get_logger
from .models import LyricLine, LyricsDoc, LyricSection

log = get_logger("lyrics")

_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_SECTION_RE = re.compile(r"^\[(.+?)\]$")
_HEADING_RE = re.compile(r"^#\s+(.*)$")


def extract_fence(text: str) -> str | None:
    """Return the first fenced code block, or ``None``."""
    match = _FENCE_RE.search(text)
    return match.group(1) if match else None


def extract_title(text: str, fallback: str) -> str:
    """First ``# Heading`` outside nothing fancy; falls back to the stem."""
    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            title = match.group(1).strip()
            title = title.split("—")[0].split(" - ")[0].strip()
            return title or fallback
    return fallback


def _section_name(raw: str) -> str:
    """``Intro - spoken, close`` -> ``Intro``."""
    head = re.split(r"[-,]", raw, maxsplit=1)[0]
    return head.strip() or raw.strip()


def _clean_line(raw: str) -> str:
    return " ".join(raw.split())


def parse_lyrics(path: Path) -> LyricsDoc:
    """Parse a lyrics file into a :class:`~slopcore_factory.models.LyricsDoc`."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    block = extract_fence(body) or body

    title = str(meta.get("title") or extract_title(text, path.stem))

    sections: list[LyricSection] = []
    current = LyricSection("verse")
    index = 0
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _SECTION_RE.match(line)
        if match:
            if current.lines:
                sections.append(current)
            current = LyricSection(_section_name(match.group(1)))
            continue
        cleaned = _clean_line(line)
        if not cleaned:
            continue
        current.lines.append(LyricLine(text=cleaned, section=current.name, index=index))
        index += 1

    if current.lines:
        sections.append(current)

    if not sections:
        raise LyricsParseError(f"no lyric lines found in {path}")

    doc = LyricsDoc(title=title, sections=sections, raw=text, meta=meta, source=path)
    log.info(
        "parsed %s: %d sections, %d lines, title=%r",
        path.name,
        len(sections),
        len(doc.lines),
        doc.title,
    )
    return doc
