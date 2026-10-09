"""Doctor preflight tests."""

from __future__ import annotations

import pytest

from slopcore_factory.doctor import Check, checks, report, require_tools
from slopcore_factory.errors import SlopcoreFactoryError


def test_checks_covers_the_tools_and_extras() -> None:
    rows = checks()
    names = {row.name for row in rows}
    assert "python" in names
    assert {"ffmpeg", "ffprobe", "node", "npx"} <= names
    assert any(row.required for row in rows)
    assert all(row.detail for row in rows)  # every row says something useful


def test_report_marks_missing_rows() -> None:
    rows = [
        Check("ffmpeg", True, "/usr/bin/ffmpeg", required=True),
        Check("opencv (match)", False, "pip install '.[match]'"),
    ]
    text = report(rows)
    assert text.startswith("ok")
    assert "MISS" in text
    assert "pip install '.[match]'" in text


def test_require_tools_raises_for_a_missing_tool() -> None:
    require_tools(("python",))  # present, so no raise
    with pytest.raises(SlopcoreFactoryError):
        require_tools(("definitely-not-a-tool",))
