"""HyperFrames CLI driver: check, snapshot, render.

The factory never touches the Studio UI. It shells out to the pinned
``hyperframes`` CLI exactly the way the project scripts do, so output stays
reproducible across machines.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .errors import RenderError
from .interfaces import CommandRunner
from .logging_setup import get_logger

log = get_logger("render")


def resolve_npx() -> str:
    """Resolve the ``npx`` shim on PATH (``npx.cmd`` on Windows)."""
    for name in ("npx.cmd", "npx", "npx.exe"):
        found = shutil.which(name)
        if found:
            return found
    raise RenderError("npx not found on PATH; install Node.js")


class HyperframesRenderer:
    """The renderer the pipeline uses: a thin wrapper over the HyperFrames CLI."""

    def __init__(self, version: str, runner: CommandRunner, skill: str = "music-to-video") -> None:
        self.version = version
        self.runner = runner
        self.skill = skill

    def _cmd(self, *args: str) -> list[str]:
        return [resolve_npx(), "--yes", f"hyperframes@{self.version}", *args]

    def check(self, project: Path) -> tuple[int, str]:
        result = self.runner.run(self._cmd("check", "."), cwd=Path(project), timeout=60 * 60)
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode, output

    def snapshot(self, project: Path, times: list[float]) -> list[Path]:
        at = ",".join(str(t) for t in times)
        result = self.runner.run(
            self._cmd("snapshot", "--at", at), cwd=Path(project), timeout=60 * 30
        )
        if result.returncode != 0:
            raise RenderError(f"snapshot failed: {(result.stderr or '').strip()[-500:]}")
        snap_dir = Path(project) / "snapshots"
        return sorted(snap_dir.glob("*.png")) if snap_dir.is_dir() else []

    def render(
        self, project: Path, out: Path, fps: int, fmt: str = "mp4", workers: int | None = None
    ) -> Path:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "render",
            ".",
            "--skill",
            self.skill,
            "-q",
            "looks",
            "--format",
            fmt,
            "-o",
            str(out),
            "--fps",
            str(fps),
        ]
        if workers is not None:
            args += ["--workers", str(workers)]
        result = self.runner.run(
            self._cmd(*args),
            cwd=Path(project),
            timeout=None,  # renders can be long; no timeout
        )
        if result.returncode != 0 or not out.exists():
            tail = ((result.stderr or "") + (result.stdout or "")).strip().splitlines()[-10:]
            raise RenderError("render failed:\n" + "\n".join(tail))
        log.info("rendered %s", out)
        return out

    @staticmethod
    def parse_check(output: str) -> dict:
        """Best-effort summary of a ``check`` run for the run manifest."""
        summary = {"errors": None, "warnings": None, "passed": "Check passed" in output}
        for line in output.splitlines():
            low = line.strip().lower()
            if "error(s)" in low:
                try:
                    summary["errors"] = int(line.strip().split()[0])
                except (ValueError, IndexError):
                    pass
            if "warning(s)" in low:
                try:
                    summary["warnings"] = int(line.strip().split()[0])
                except (ValueError, IndexError):
                    pass
        return summary
