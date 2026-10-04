"""Generate the Seedance clips named by a blueprint.

The provider is an interface so the dry-run provider (local placeholder) and the
EvoLink provider (paid) are interchangeable. The paid provider is guarded by the
budget module before it is called.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .blueprint import Blueprint, SeedanceClip
from .errors import ClipGenerationError
from .logging_setup import get_logger
from .vendor import add_slopcore_to_path

log = get_logger("clipgen")


class ClipGenerator(Protocol):
    """Writes one clip for a Seedance entry and returns its local path."""

    def generate(self, entry: SeedanceClip, out_dir: Path) -> Path | None: ...


def generate_seedance_clips(
    blueprint: Blueprint, provider: ClipGenerator, out_dir: Path
) -> dict[str, Path]:
    """Generate every clip in the blueprint and record its path on the entry.

    A provider may return ``None`` (e.g. supplied mode with no matching file);
    those entries are simply left without a local path.
    """
    out_dir = Path(out_dir)
    paths: dict[str, Path] = {}
    for entry in blueprint.seedance:
        result = provider.generate(entry, out_dir)
        if result is None:
            continue
        path = Path(result)
        entry.path = path.as_posix()
        paths[entry.clip] = path
    log.info("resolved %d clip(s) into %s", len(paths), out_dir)
    return paths


class SuppliedClipProvider:
    """Resolve a blueprint clip to a file the user supplied (no API).

    Looks for ``<song>/assets/clips/<clip>.<ext>``. Returns ``None`` when there
    is no match, so nothing is generated and nothing is faked.
    """

    VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}

    def __init__(self, song_dir: Path) -> None:
        self.song_dir = Path(song_dir)

    def generate(self, entry: SeedanceClip, out_dir: Path) -> Path | None:
        clips_dir = self.song_dir / "assets" / "clips"
        if clips_dir.is_dir():
            for candidate in sorted(clips_dir.glob(f"{entry.clip}.*")):
                if candidate.suffix.lower() in self.VIDEO_SUFFIXES:
                    return candidate
        return None


class EvoLinkClipProvider:
    """Real Seedance 2.5 generation via EvoLink (paid).

    Audio-conditioned when the entry is a singing window: the exact slice of the
    song is cut in a word gap and hosted so the model can lip-sync to it.
    """

    def __init__(
        self,
        reference_audio: Path | None = None,
        quality: str = "720p",
        aspect: str = "16:9",
    ) -> None:
        self.reference_audio = Path(reference_audio) if reference_audio else None
        self.quality = quality
        self.aspect = aspect

    def generate(self, entry: SeedanceClip, out_dir: Path) -> Path:  # pragma: no cover - paid
        add_slopcore_to_path()
        try:
            import slopcore_hf.evolink as ev
            from slopcore_hf import media
            from slopcore_hf.config import load_settings
            from slopcore_hf.hosting import host_file
            from slopcore_hf.ledger import Ledger
        except ImportError as exc:
            raise ClipGenerationError("slopcore-hf not importable") from exc

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        data_dir = out_dir.parent.parent / "data"
        ev.DATA_DIR = data_dir
        settings = load_settings()
        client = ev.EvoLinkClient(settings.api_key, ledger=Ledger(data_dir / "ledger.jsonl"))

        payload: dict = {
            "model": settings.seedance_model,
            "prompt": entry.prompt,
            "duration": int(round(entry.duration)),
            "quality": self.quality,
            "aspect_ratio": self.aspect,
            "generate_audio": entry.sing,
        }
        if entry.sing and self.reference_audio and self.reference_audio.exists():
            slice_path = data_dir / "clips" / "audio" / f"{entry.clip}.wav"
            media.slice_audio(
                self.reference_audio, slice_path, entry.song_t0, entry.song_t0 + entry.duration
            )
            payload["audio_urls"] = [host_file(slice_path, cache_path=data_dir / "hosted.jsonl")]

        task = client.submit_once(f"clip-{entry.clip}-v1", "video", payload)
        if task is None:
            raise ClipGenerationError(f"{entry.clip}: submission failed")
        videos = [u for k, u in ev.EvoLinkClient.find_media(task) if k == "video"]
        if not videos:
            raise ClipGenerationError(f"{entry.clip}: no video URL")
        dest = out_dir / f"{entry.clip}.mp4"
        client.download(videos[0], dest)
        log.info("generated %s: %s", entry.clip, dest)
        return dest
