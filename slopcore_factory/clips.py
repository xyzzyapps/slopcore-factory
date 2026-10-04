"""Optional Seedance clip generation (paid, opt-in).

Off by default. When ``--generate-clips`` is passed, the factory generates a
small set of silent 7 s b-roll clips from a cinematic prompt set (optionally
conditioned on reference images in ``assets/ref``), mirroring the original
``generate_clips.py`` but driven by the song rather than hand-written prompts.
"""

from __future__ import annotations

from pathlib import Path

from .errors import ClipGenerationError
from .logging_setup import get_logger
from .models import FactorySpec, LyricsDoc
from .vendor import add_slopcore_to_path

log = get_logger("clips")


def _prompts(spec: FactorySpec) -> list[str]:
    """Clip prompts are creative direction and come from the storyboard/spec."""
    prompts = spec.extra.get("clip_prompts")
    if not prompts:
        raise ClipGenerationError(
            "--generate-clips needs 'clip_prompts' (a list) in the storyboard or song.json"
        )
    return [str(p) for p in prompts]


def _prompt(index: int, spec: FactorySpec) -> str:
    prompts = _prompts(spec)
    shot = prompts[index % len(prompts)]
    style = str(spec.extra.get("clip_style", "")).strip()
    return f"{shot} {style}".strip() if style else shot


class SeedanceClipProvider:
    """Generate silent background clips via EvoLink Seedance."""

    def __init__(self, count: int = 4, quality: str = "480p", duration: int = 7) -> None:
        self.count = count
        self.quality = quality
        self.duration = duration

    def acquire(self, spec: FactorySpec, lyrics: LyricsDoc) -> list[Path]:
        add_slopcore_to_path()
        try:
            import slopcore_hf.evolink as ev
            from slopcore_hf.config import load_settings
            from slopcore_hf.ledger import Ledger
        except ImportError as exc:  # pragma: no cover
            raise ClipGenerationError("slopcore-hf not importable") from exc

        data_dir = Path(spec.out_dir) / "data"
        ev.DATA_DIR = data_dir
        settings = load_settings()
        ledger = Ledger(data_dir / "ledger.jsonl")
        client = ev.EvoLinkClient(settings.api_key, ledger=ledger)

        refs = _reference_images(Path(spec.lyrics_path).parent)
        image_urls: list[str] = []
        for ref in refs:
            try:
                image_urls.append(client.upload_image(ref))
            except Exception as exc:  # noqa: BLE001 - references are optional
                log.warning("could not upload reference %s: %s", ref, exc)

        out_dir = Path(spec.out_dir) / "assets" / "clips"
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for i in range(self.count):
            payload = {
                "model": settings.seedance_model,
                "prompt": _prompt(i, spec),
                "duration": self.duration,
                "quality": self.quality,
                "aspect_ratio": f"{spec.width}:{spec.height}",
                "generate_audio": False,
            }
            if image_urls:
                payload["image_urls"] = image_urls[:3]
            task = client.submit_once(f"clip-c{i + 1}-v1", "video", payload)
            if task is None:
                raise ClipGenerationError(f"clip {i + 1} submission failed")
            videos = [u for k, u in ev.EvoLinkClient.find_media(task) if k == "video"]
            if not videos:
                raise ClipGenerationError(f"clip {i + 1} returned no video URL")
            dest = out_dir / f"clip-c{i + 1}.mp4"
            client.download(videos[0], dest)
            ledger.mark(f"clip-c{i + 1}-v1", output=str(dest))
            paths.append(dest)
            log.info("generated clip %d/%d: %s", i + 1, self.count, dest)
        return paths


def _reference_images(base: Path) -> list[Path]:
    ref_dir = base / "assets" / "ref"
    if not ref_dir.is_dir():
        return []
    suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted(p for p in ref_dir.iterdir() if p.suffix.lower() in suffixes)[:3]
