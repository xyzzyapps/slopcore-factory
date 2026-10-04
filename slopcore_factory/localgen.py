"""Local song-generation backends (YuE, ACE-Step) — no API, no vendored weights.

These models are large and are not bundled here. A backend is driven through a
command you configure (so you can install YuE or ACE-Step however you like and
point the factory at a small wrapper):

    set SLOPCORE_ACE_STEP_CMD=python C:\\tools\\acestep_wrapper.py
    slopcore-factory song --lyrics ... --song-backend ace_step

The wrapper receives ``--request <json>`` and ``--out <wav>``; the request holds
``title``, ``lyrics``, ``style``, ``duration``, ``seed`` and the output path. It
must write a wav/mp3 at ``--out``. CPU inference is the caller's choice inside
the wrapper.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
from pathlib import Path

from .errors import SongGenerationError
from .logging_setup import get_logger
from .models import FactorySpec, LyricsDoc

log = get_logger("localgen")


class LocalSongProvider:
    """Base class for a locally installed generator driven by a command."""

    name = "local"
    env_cmd = ""
    module = ""
    install_hint = ""

    def __init__(self, command: str | None = None, timeout: int | None = None) -> None:
        self.command = command or os.environ.get(self.env_cmd, "")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.command)

    def module_installed(self) -> bool:
        if not self.module:
            return False
        return importlib.util.find_spec(self.module) is not None

    def acquire(self, spec: FactorySpec, lyrics: LyricsDoc) -> Path:
        assets = Path(spec.out_dir) / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        dest = assets / f"bgm-{self.name}.wav"
        request = {
            "backend": self.name,
            "title": spec.title,
            "lyrics": lyrics.text,
            "style": str(spec.extra.get("style", "")),
            "duration": float(spec.duration or 180.0),
            "seed": int(spec.extra.get("seed", 0)),
            "out": str(dest),
        }
        request_path = Path(spec.out_dir) / "data" / "song_request.json"
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

        if not self.command:
            detail = self.install_hint or f"set {self.env_cmd}"
            raise SongGenerationError(
                f"{self.name} is not configured. {detail}"
                + (" (module installed but no command given)" if self.module_installed() else "")
            )

        args = shlex.split(self.command, posix=os.name != "nt")
        args += ["--request", str(request_path), "--out", str(dest)]
        log.info("%s: %s", self.name, " ".join(args))
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
            raise SongGenerationError(f"{self.name} failed:\n" + "\n".join(tail))
        if not dest.exists() or dest.stat().st_size == 0:
            raise SongGenerationError(f"{self.name} produced no file at {dest}")
        log.info("%s wrote %s", self.name, dest)
        return dest


class YuESongProvider(LocalSongProvider):
    """YuE (lyrics-to-song). Configure ``SLOPCORE_YUE_CMD``."""

    name = "yue"
    env_cmd = "SLOPCORE_YUE_CMD"
    module = "yue"
    install_hint = (
        "install YuE (https://github.com/multimodal-art-projection/YuE) and set "
        "SLOPCORE_YUE_CMD to a wrapper that accepts --request/--out"
    )


class AceStepSongProvider(LocalSongProvider):
    """ACE-Step (music generation). Configure ``SLOPCORE_ACE_STEP_CMD``."""

    name = "ace_step"
    env_cmd = "SLOPCORE_ACE_STEP_CMD"
    module = "acestep"
    install_hint = (
        "install ACE-Step (https://github.com/ace-step/ACE-Step) and set "
        "SLOPCORE_ACE_STEP_CMD to a wrapper that accepts --request/--out"
    )


BACKENDS = {
    "supplied": None,
    "suno": None,
    "dryrun": None,
    "yue": YuESongProvider,
    "ace_step": AceStepSongProvider,
}
