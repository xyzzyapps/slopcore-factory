"""Song acquisition: use a supplied track, or generate one via EvoLink Suno.

Generation is opt-in and reuses the tested ``slopcore-hf`` client, so the API
key/ledger behaviour matches the original project. Supplied audio is the
zero-cost default.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .errors import AudioError, SongGenerationError
from .logging_setup import get_logger
from .models import FactorySpec, LyricsDoc
from .vendor import add_slopcore_to_path

log = get_logger("song")

# A neutral, generic fallback only. The song's own style belongs in
# ``prompts/suno-style.md`` or ``spec.extra['style']``.
DEFAULT_STYLE = "sparse minor-key ballad, intimate close female vocal, slow tempo"


class SuppliedSongProvider:
    """Use the audio file already present in the song folder."""

    def acquire(self, spec: FactorySpec, lyrics: LyricsDoc) -> Path:
        if spec.audio_path and Path(spec.audio_path).exists():
            log.info("using supplied audio: %s", spec.audio_path)
            return Path(spec.audio_path)
        raise AudioError("no audio found; pass --audio PATH or use --generate-song to create one")


class SunoSongProvider:
    """Generate the song with EvoLink Suno (paid, requires EVOLINK_API_KEY)."""

    def __init__(self, take: int = 1) -> None:
        self.take = take

    def acquire(self, spec: FactorySpec, lyrics: LyricsDoc) -> Path:
        add_slopcore_to_path()
        try:
            import slopcore_hf.evolink as ev
            from slopcore_hf.config import load_settings
            from slopcore_hf.ledger import Ledger
        except ImportError as exc:  # pragma: no cover - env dependent
            raise SongGenerationError(
                "slopcore-hf not importable; check the workspace layout"
            ) from exc

        data_dir = Path(spec.out_dir) / "data"
        ev.DATA_DIR = data_dir
        settings = load_settings()

        style = str(spec.extra.get("style", "")).strip() or DEFAULT_STYLE
        if spec.suno_style_path and Path(spec.suno_style_path).exists():
            style = _strip_front_matter(
                Path(spec.suno_style_path).read_text(encoding="utf-8")
            ).strip()

        ledger = Ledger(data_dir / "ledger.jsonl")
        client = ev.EvoLinkClient(settings.api_key, ledger=ledger)

        payload = {
            "model": settings.suno_model,
            "custom_mode": True,
            "instrumental": False,
            "style": style,
            "title": spec.suno_title or spec.title.upper(),
            "prompt": lyrics.text,
            "vocal_gender": spec.vocal_gender,
            "duration": int(spec.duration or 180),
        }
        negative_tags = str(spec.extra.get("negative_tags", "")).strip()
        if negative_tags:
            payload["negative_tags"] = negative_tags

        log.info("submitting Suno song task (%ss)", payload["duration"])
        supersede = str(spec.extra.get("supersede_reason") or "").strip() or None
        task = client.submit_once("song-v1", "song", payload, supersede_reason=supersede)
        if task is None:
            raise SongGenerationError("Suno submission failed (see ledger)")

        tracks = [
            url for kind, url in ev.EvoLinkClient.find_media(task) if kind in {"audio", "url"}
        ]
        if not tracks:
            raise SongGenerationError("Suno returned no audio URLs")

        # Keep every take so the human can audition them; expose the chosen one
        # as assets/bgm.<ext> and record the manifest for the CLI/REPL.
        assets = Path(spec.out_dir) / "assets"
        takes_dir = assets / "song"
        takes_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []
        for i, url in enumerate(tracks, start=1):
            suffix = Path(url.split("?", 1)[0]).suffix or ".mp3"
            dest = takes_dir / f"take{i}{suffix}"
            client.download(url, dest)
            downloaded.append(dest)
            log.info("song take %d/%d: %s", i, len(tracks), dest)

        index = min(max(self.take, 1), len(downloaded)) - 1
        chosen = downloaded[index]
        bgm = assets / f"bgm{chosen.suffix.lower()}"
        shutil.copy2(chosen, bgm)
        manifest = {
            "model": settings.suno_model,
            "chosen": index + 1,
            "takes": [
                {
                    "take": i,
                    "path": path.relative_to(assets.parent).as_posix(),
                }
                for i, path in enumerate(downloaded, start=1)
            ],
        }
        (assets / "song_takes.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        ledger.mark("song-v1", output=json.dumps([str(p) for p in downloaded]))
        log.info("chosen take %d: %s", index + 1, bgm)
        return bgm


def _strip_front_matter(text: str) -> str:
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return text
    lines = stripped.splitlines()
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1 :])
    return text
