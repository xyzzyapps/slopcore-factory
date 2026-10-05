"""Subprocess runner.

Thin wrapper over :mod:`subprocess` that logs every command line, so the traces
in the log file show exactly which external tool ran and with what arguments.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .logging_setup import get_logger

log = get_logger("process")


class SubprocessRunner:
    """Default :class:`~slopcore_factory.interfaces.CommandRunner` implementation."""

    def run(
        self,
        args: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess:
        log.info("run: %s (cwd=%s)", " ".join(args), cwd)
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
