"""Locate the in-tree ``slopcore-hf`` library without hard-coding a drive path.

The factory reuses the tested EvoLink client / config / ledger from
``slopcore-hf`` instead of vendoring a copy. The library sits as a sibling of
this project inside the workspace, so we resolve it relative to this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../slopcore-factory
WORKSPACE_ROOT = PROJECT_ROOT.parent  # .../moh
SLOPCORE_SRC = WORKSPACE_ROOT / "slopcore-hf" / "src"


def add_slopcore_to_path() -> Path:
    """Put ``slopcore-hf/src`` on ``sys.path`` and return it."""
    if SLOPCORE_SRC.is_dir() and str(SLOPCORE_SRC) not in sys.path:
        sys.path.insert(0, str(SLOPCORE_SRC))
    return SLOPCORE_SRC
