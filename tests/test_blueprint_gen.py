"""Blueprint generation tests (offline path + prompt plumbing)."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.blueprint import validate_blueprint
from slopcore_factory.blueprint_gen import build_prompt, extract_yaml, generate_offline
from slopcore_factory.config import build_spec
from slopcore_factory.lyrics import parse_lyrics
from slopcore_factory.models import Cue


def _cues(doc, step: float = 2.0) -> list[Cue]:
    cues: list[Cue] = []
    t = 0.5
    for line in doc.lines:
        cues.append(Cue(line.text, t, t + 1.2, line.section, line.index))
        t += step
    return cues


def test_offline_blueprint_is_valid(tmp_path: Path, lyrics_file: Path) -> None:
    spec = build_spec(lyrics_file, tmp_path / "project")
    doc = parse_lyrics(lyrics_file)
    cues = _cues(doc)
    duration = cues[-1].end + 2.0

    bp = generate_offline(spec, doc, cues, duration)
    assert validate_blueprint(bp) == []
    assert bp.shots
    assert bp.shots[0].t0 == 0.0
    assert abs(bp.shots[-1].t1 - duration) < 0.05
    assert any(shot.type for shot in bp.shots)  # lyric lines are placed as type
    assert bp.budgets.total_usd > 0  # the song alone has a cost


def test_extract_yaml_tolerates_fences() -> None:
    assert extract_yaml("```yaml\ntitle: x\n```") == "title: x"
    assert extract_yaml("title: y") == "title: y"


def test_build_prompt_contains_lyrics_and_schema(tmp_path: Path, lyrics_file: Path) -> None:
    spec = build_spec(lyrics_file, tmp_path / "project")
    doc = parse_lyrics(lyrics_file)
    cues = _cues(doc)
    prompt = build_prompt(spec, doc, cues, cues[-1].end + 2.0, "a brief")
    assert "TEST SONG" in prompt
    assert "shots:" in prompt
    assert "lipsync:" in prompt
    assert "a brief" in prompt
