"""JSON serialisation for the pipeline's intermediate artifacts.

Kept explicit (rather than ``asdict``) so the on-disk shape is stable and
readable when debugging a run.
"""

from __future__ import annotations

from .models import BeatGrid, Cue, Storyboard, Transcript, Word


def transcript_to_dict(transcript: Transcript) -> dict:
    return {
        "engine": transcript.engine,
        "duration": transcript.duration,
        "words": [{"word": w.word, "start": w.start, "end": w.end} for w in transcript.words],
    }


def transcript_from_dict(data: dict) -> Transcript:
    return Transcript(
        engine=data.get("engine", "unknown"),
        duration=float(data.get("duration", 0.0)),
        words=[Word(w["word"], float(w["start"]), float(w["end"])) for w in data.get("words", [])],
    )


def cues_to_list(cues: list[Cue]) -> list[dict]:
    return [
        {
            "text": c.text,
            "start": c.start,
            "end": c.end,
            "section": c.section,
            "index": c.index,
            "words": [{"word": w.word, "start": w.start, "end": w.end} for w in c.words],
        }
        for c in cues
    ]


def cues_from_list(data: list[dict]) -> list[Cue]:
    cues: list[Cue] = []
    for item in data:
        cues.append(
            Cue(
                text=item["text"],
                start=float(item["start"]),
                end=float(item["end"]),
                section=item.get("section", "verse"),
                index=int(item.get("index", 0)),
                words=[
                    Word(w["word"], float(w["start"]), float(w["end"]))
                    for w in item.get("words", [])
                ],
            )
        )
    return cues


def grid_to_dict(grid: BeatGrid) -> dict:
    return {
        "bpm": grid.bpm,
        "duration": grid.duration,
        "beats": grid.beats,
        "downbeats": grid.downbeats,
    }


def grid_from_dict(data: dict) -> BeatGrid:
    return BeatGrid(
        bpm=float(data.get("bpm", 0.0)),
        duration=float(data.get("duration", 0.0)),
        beats=[float(v) for v in data.get("beats", [])],
        downbeats=[float(v) for v in data.get("downbeats", [])],
    )


def storyboard_summary(storyboard: Storyboard) -> dict:
    return {
        "duration": storyboard.duration,
        "canvas": [storyboard.width, storyboard.height, storyboard.fps],
        "accent_word": storyboard.accent_word,
        "frames": [
            {
                "id": f.id,
                "start": f.start,
                "duration": f.duration,
                "groups": len(f.groups),
                "background": str(f.background) if f.background else None,
            }
            for f in storyboard.frames
        ],
    }
