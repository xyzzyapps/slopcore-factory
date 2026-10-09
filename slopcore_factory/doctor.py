"""Preflight: check the tools and optional extras the factory needs.

The tools (Python, ffmpeg/ffprobe, Node/npx) are required; everything else is an
optional extra or a sibling checkout, so a missing one only disables a feature.
"""

from __future__ import annotations

import importlib
import platform
import shutil
from dataclasses import dataclass

from .errors import SlopcoreFactoryError

TOOLS = ["ffmpeg", "ffprobe", "node", "npx"]
REQUIRED_TOOLS = ("ffmpeg", "ffprobe")
EXTRAS = [
    ("opencv (match)", "cv2", ".[match]"),
    ("librosa (beats)", "librosa", ".[beats]"),
    ("langchain (llm)", "langchain", ".[llm]"),
    ("ultralytics (yolo)", "ultralytics", "ultralytics"),
]


@dataclass
class Check:
    """One preflight result."""

    name: str
    ok: bool
    detail: str
    required: bool = False


def checks() -> list[Check]:
    """Every tool and extra, in display order (the required tools first)."""
    rows = [Check("python", True, platform.python_version(), required=True)]
    for tool in TOOLS:
        found = shutil.which(tool)
        rows.append(Check(tool, bool(found), found or "not found on PATH", required=True))
    for name, module, extra in EXTRAS:
        try:
            importlib.import_module(module)
            rows.append(Check(name, True, "importable"))
        except Exception:  # noqa: BLE001 - any import failure is a miss
            rows.append(Check(name, False, f"pip install '{extra}'"))
    demucs = shutil.which("demucs")
    rows.append(Check("demucs (vocal stem)", bool(demucs), demucs or "optional; full mix is used"))
    from .vendor import SLOPCORE_SRC  # noqa: PLC0415

    rows.append(Check("slopcore-hf (paid)", SLOPCORE_SRC.is_dir(), str(SLOPCORE_SRC)))
    return rows


def report(rows: list[Check]) -> str:
    """A plain, aligned table of the checks."""
    width = max(len(row.name) for row in rows)
    return "\n".join(
        f"{'ok  ' if row.ok else 'MISS'}  {row.name:<{width}}  {row.detail}" for row in rows
    )


def require_tools(names: tuple[str, ...] = REQUIRED_TOOLS) -> None:
    """Raise a ``SlopcoreFactoryError`` naming any missing required tool."""
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        raise SlopcoreFactoryError(
            "missing required tool(s): "
            + ", ".join(missing)
            + " — install them and open a new terminal"
        )
