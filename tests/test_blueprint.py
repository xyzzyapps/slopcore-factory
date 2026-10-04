"""Blueprint schema tests: round-trip, tiling validation, ordering."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.blueprint import (
    Blueprint,
    Chapter,
    LipsyncWindow,
    SeedanceClip,
    Shot,
    ShotType,
    load_blueprint,
    save_blueprint,
    validate_blueprint,
)


def _blueprint() -> Blueprint:
    return Blueprint(
        title="t",
        duration=10.0,
        chapters=[Chapter(id="ch1", name="one", t0=0.0, t1=10.0)],
        shots=[
            Shot(id="s1", t0=0.0, t1=5.0, chapter="ch1", type=[ShotType(0, "subtitle", "hi")]),
            Shot(
                id="s2",
                t0=5.0,
                t1=10.0,
                chapter="ch1",
                motion_tier="seedance",
                seedance_clip="sd01",
            ),
        ],
        seedance=[SeedanceClip(clip="sd01", duration=5.0, sing=True, song_t0=5.0, words="hi")],
        lipsync=[LipsyncWindow(clip="sd01", song_t0=5.0, duration=5.0, words="hi")],
    )


def test_round_trip(tmp_path: Path) -> None:
    path = save_blueprint(_blueprint(), tmp_path / "bp.yaml")
    loaded = load_blueprint(path)
    assert loaded.title == "t"
    assert len(loaded.shots) == 2
    assert loaded.shots[0].type[0].text == "hi"
    assert loaded.lipsync[0].words == "hi"
    assert validate_blueprint(loaded) == []


def test_validation_flags_gap() -> None:
    bp = _blueprint()
    bp.shots[1].t0 = 6.0  # leaves a gap 5..6
    problems = validate_blueprint(bp)
    assert any("gap/overlap" in p for p in problems)


def test_validation_flags_bad_last_end() -> None:
    bp = _blueprint()
    bp.shots[1].t1 = 9.0
    problems = validate_blueprint(bp)
    assert any("last shot ends" in p for p in problems)


def test_validation_flags_unknown_clip() -> None:
    bp = _blueprint()
    bp.shots[1].seedance_clip = "missing"
    problems = validate_blueprint(bp)
    assert any("known clip" in p for p in problems)


def test_validation_flags_duplicate_ids() -> None:
    bp = _blueprint()
    bp.shots.append(Shot(id="s1", t0=10.0, t1=10.0))
    problems = validate_blueprint(bp)
    assert any("duplicate shot id" in p for p in problems)
