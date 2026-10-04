"""Logging setup: console + per-run file.

Logs land under ``<out_dir>/../logs`` by default so each song keeps its own
trace, which is what we debug from.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

_CONFIGURED = False


def setup_logging(log_dir: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    """Configure the root logger once and return it.

    A console handler is always added. When ``log_dir`` is given, a timestamped
    file handler is added as well.
    """
    global _CONFIGURED
    root = logging.getLogger("slopcore_factory")
    root.setLevel(level)
    if _CONFIGURED:
        return root

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        file_handler = logging.FileHandler(
            log_dir / f"slopcore_factory-{stamp}.log", encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a child logger. Safe to call before :func:`setup_logging`."""
    return logging.getLogger(f"slopcore_factory.{name}")
