"""Song provider plumbing: the supersede reason reaches the paid submission."""

from __future__ import annotations

from pathlib import Path

from slopcore_factory.cli import _make_spec, build_parser
from slopcore_factory.config import build_spec


def test_supersede_reason_reaches_extra(lyrics_file: Path, tmp_path: Path) -> None:
    spec = build_spec(
        lyrics_file, tmp_path / "project", overrides={"supersede_reason": "retry after failure"}
    )
    assert spec.extra["supersede_reason"] == "retry after failure"


def test_cli_supersede_flag_maps_to_extra(lyrics_file: Path, tmp_path: Path) -> None:
    args = build_parser().parse_args(
        [
            "song",
            "--lyrics",
            str(lyrics_file),
            "--out",
            str(tmp_path / "project"),
            "--supersede-reason",
            "retry after failure",
        ]
    )
    spec = _make_spec(args)
    assert spec.extra["supersede_reason"] == "retry after failure"
