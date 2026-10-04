"""Subprocess runner.

Thin wrapper over :mod:`subprocess` that logs every command line, so the traces
in the log file show exactly which external tool ran and with what arguments.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import RenderError
from .logging_setup import get_logger

log = get_logger("process")


class SubprocessRunner:
    """Default :class:`~slopcore_factory.interfaces.CommandRunner` implementation."""

    def __init__(self, echo: bool = True) -> None:
        self.echo = echo

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

    def run_or_raise(
        self,
        args: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess:
        """Run and raise :class:`RenderError` on a non-zero exit code."""
        result = self.run(args, cwd=cwd, timeout=timeout)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
            raise RenderError(
                f"command failed ({result.returncode}): {' '.join(args)}\n" + "\n".join(tail)
            )
        return result
