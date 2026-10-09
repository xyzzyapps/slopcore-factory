"""Pipeline orchestrator.

Models the run as an ordered set of stages with an explicit status, so an
interrupted or partial run is cheap to resume: heavy stages (song generation,
transcription) are skipped when their hash-keyed cache is still fresh.

    song -> align -> beats -> media -> plan -> build -> check -> [snapshot] -> render

Every stage persists its artifacts under the work directory, so the CLI can run
the chain up to any stage (``slopcore_factory build`` runs everything through build).
"""

from __future__ import annotations

import json
from pathlib import Path

from .beats import estimate_beats, load_audiomap
from .cache import StageCache, hash_files, hash_parts
from .compose import compose_project
from .errors import SlopcoreFactoryError
from .interfaces import CommandRunner
from .locator import ServiceLocator
from .logging_setup import get_logger
from .lyrics import parse_lyrics
from .media import prepare_background
from .models import Artifact, FactorySpec, LyricsDoc, StageResult, Storyboard
from .serde import (
    cues_from_list,
    cues_to_list,
    grid_from_dict,
    grid_to_dict,
    storyboard_summary,
    transcript_from_dict,
    transcript_to_dict,
)
from .storyboard import plan_storyboard
from .theme import load_theme
from .timing import align_cues, load_transcript_file

log = get_logger("pipeline")

STAGES = ["song", "align", "beats", "media", "plan", "build", "check", "snapshot", "render"]


def unique_path(path: Path) -> Path:
    """Never overwrite an output: ``x.mp4``, ``x-2.mp4``, ``x-3.mp4``, ..."""
    path = Path(path)
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise SlopcoreFactoryError(f"cannot find a free name for {path}")


class Pipeline:
    """Drives one song from lyrics to a rendered MP4."""

    def __init__(
        self,
        spec: FactorySpec,
        services: ServiceLocator,
        work_dir: Path,
        snapshot_times: list[float] | None = None,
    ) -> None:
        self.spec = spec
        self.services = services
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.cache = StageCache(self.work_dir / "cache")
        self.snapshot_times = snapshot_times or []

        self.lyrics: LyricsDoc | None = None
        self.transcript = None
        self.cues = None
        self.grid = None
        self.backgrounds: list[Path] = []
        self.storyboard: Storyboard | None = None
        self.build_manifest: dict = {}
        self.results: list[StageResult] = []

    # -- public ---------------------------------------------------------------

    def run(
        self, until: str | None = None, skip: set[str] | None = None, force: bool = False
    ) -> list[StageResult]:
        """Run the stage chain up to and including ``until``."""
        skip = skip or set()
        stop_index = STAGES.index(until) if until else len(STAGES) - 1

        for stage in STAGES[: stop_index + 1]:
            if stage in skip:
                self.results.append(StageResult(stage, "SKIPPED", detail="requested skip"))
                continue
            try:
                result = self._run_stage(stage, force)
            except SlopcoreFactoryError as exc:
                log.error("stage %s failed: %s", stage, exc)
                self.results.append(StageResult(stage, "FAILED", detail=str(exc)))
                break
            self.results.append(result)
            if result.status == "FAILED":
                log.error("stage %s failed: %s", stage, result.detail)
                break

        self._write_run_manifest()
        return self.results

    def failed(self) -> bool:
        return any(result.status == "FAILED" for result in self.results)

    # -- stage dispatch -------------------------------------------------------

    def _run_stage(self, stage: str, force: bool) -> StageResult:
        log.info("stage: %s", stage)
        handler = getattr(self, f"_do_{stage}")
        return handler(force)

    def _lyrics_doc(self) -> LyricsDoc:
        if self.lyrics is None:
            self.lyrics = parse_lyrics(self.spec.lyrics_path)
        return self.lyrics

    def _runner(self) -> CommandRunner:
        return self.services.get("runner")

    # -- stages ---------------------------------------------------------------

    def _do_song(self, force: bool) -> StageResult:
        lyrics = self._lyrics_doc()
        audio = self.spec.audio_path
        key = hash_parts(
            song=lyrics.text,
            generate=self.spec.generate_song,
            supplied=hash_files(audio) if audio else None,
            take=self.spec.extra.get("suno_take", 1),
        )
        if not force and audio and Path(audio).exists() and self.cache.is_fresh("song", key):
            return StageResult("song", "DONE", detail=f"cached: {audio}", cache_key=key)

        provider = self.services.get("song_provider")
        path = provider.acquire(self.spec, lyrics)
        self.spec.audio_path = Path(path)
        self.cache.mark("song", key, [Path(path)])
        return StageResult(
            "song",
            "DONE",
            detail=str(path),
            artifacts=[Artifact("song", "audio", Path(path))],
            cache_key=key,
        )

    def _do_align(self, force: bool) -> StageResult:
        lyrics = self._lyrics_doc()
        audio = self.spec.audio_path
        if not audio or not Path(audio).exists():
            raise SlopcoreFactoryError("align requires an audio track (run the song stage first)")

        key = hash_files(Path(audio)) + hash_parts(
            lyrics=lyrics.text, model=self.spec.whisper_model, lang=self.spec.language
        )
        transcript_path = self.work_dir / "transcript.json"
        cues_path = self.work_dir / "cues.json"
        if (
            not force
            and transcript_path.exists()
            and cues_path.exists()
            and self.cache.is_fresh("align", key)
        ):
            self.transcript = transcript_from_dict(
                json.loads(transcript_path.read_text(encoding="utf-8"))
            )
            self.cues = cues_from_list(json.loads(cues_path.read_text(encoding="utf-8")))
            return StageResult("align", "DONE", detail="cached", cache_key=key)

        # Prefer a supplied transcript file over paying for a transcription run.
        self.transcript = (
            load_transcript_file(self.spec.transcript_path) if self.spec.transcript_path else None
        )
        if self.transcript is None:
            transcriber = self.services.get("transcriber")
            self.transcript = transcriber.transcribe(Path(audio), lyrics, self.spec.duration or 0.0)
        else:
            log.info("using supplied transcript: %s", self.spec.transcript_path)

        aligner = self.services.get("aligner")
        if aligner is not None:
            self.cues = aligner.align(lyrics, self.transcript)
        else:
            self.cues = align_cues(lyrics, self.transcript)

        transcript_path.write_text(
            json.dumps(transcript_to_dict(self.transcript), indent=2), encoding="utf-8"
        )
        cues_path.write_text(json.dumps(cues_to_list(self.cues), indent=2), encoding="utf-8")
        self.cache.mark("align", key, [transcript_path, cues_path])
        return StageResult(
            "align",
            "DONE",
            detail=f"{len(self.transcript.words)} words, {len(self.cues)} cues",
            artifacts=[
                Artifact("align", "transcript", transcript_path),
                Artifact("align", "cues", cues_path),
            ],
            cache_key=key,
        )

    def _do_beats(self, force: bool) -> StageResult:
        audio = self.spec.audio_path
        if not audio:
            raise SlopcoreFactoryError("beats requires an audio track")
        duration = self._duration()

        cached = self.work_dir / "beats.json"
        if not force and cached.exists():
            self.grid = grid_from_dict(json.loads(cached.read_text(encoding="utf-8")))
            return StageResult("beats", "DONE", detail="cached")

        audiomap = Path(self.spec.lyrics_path).parent / "audiomap.json"
        self.grid = load_audiomap(audiomap, duration)
        if self.grid is None:
            self.grid = estimate_beats(Path(audio), duration)
        cached.write_text(json.dumps(grid_to_dict(self.grid), indent=2), encoding="utf-8")
        detail = (
            f"{self.grid.bpm:.1f} bpm, {len(self.grid.downbeats)} downbeats"
            if self.grid.has_grid
            else "no grid"
        )
        return StageResult(
            "beats", "DONE", detail=detail, artifacts=[Artifact("beats", "grid", cached)]
        )

    def _do_media(self, force: bool) -> StageResult:
        cached = self.work_dir / "backgrounds.json"
        if not force and cached.exists():
            data = json.loads(cached.read_text(encoding="utf-8"))
            self.backgrounds = [Path(p) for p in data["clips"] if Path(p).exists()]
            if self.backgrounds:
                return StageResult(
                    "media", "DONE", detail=f"cached: {len(self.backgrounds)} clip(s)"
                )

        if self.spec.generate_clips:
            # one clip path only: the blueprint's Seedance entries, via clipgen
            from .blueprint import load_blueprint, save_blueprint
            from .budget import guard
            from .clipgen import generate_seedance_clips, reference_images

            blueprint_path = self.work_dir / "blueprint.yaml"
            if not blueprint_path.exists():
                raise SlopcoreFactoryError(
                    "--generate-clips needs a blueprint; run the `blueprint` command first"
                )
            blueprint = load_blueprint(blueprint_path)
            guard(blueprint)
            provider = self.services.get(
                "clip_generator",
                reference_audio=self.spec.audio_path,
                quality=str(self.spec.extra.get("clip_quality", "720p")),
                reference_images=reference_images(Path(self.spec.lyrics_path).parent),
            )
            paths = generate_seedance_clips(
                blueprint, provider, Path(self.spec.out_dir) / "assets" / "clips"
            )
            save_blueprint(blueprint, blueprint_path)
            self.backgrounds = list(paths.values())
        else:
            self.backgrounds = prepare_background(
                self.spec, self.work_dir / "media", self._runner()
            )

        cached.write_text(
            json.dumps({"clips": [str(p) for p in self.backgrounds]}, indent=2), encoding="utf-8"
        )
        return StageResult(
            "media",
            "DONE",
            detail=f"{len(self.backgrounds)} clip(s)",
            artifacts=[Artifact("media", "background", p) for p in self.backgrounds],
        )

    def _do_plan(self, force: bool) -> StageResult:
        lyrics = self._lyrics_doc()
        duration = self._duration()

        from .storyboard_md import load_plan

        song_dir = Path(self.spec.lyrics_path).parent
        plan = load_plan(song_dir, self.work_dir, lyrics)
        source = "planner"
        if plan is not None:
            from .compiler import blueprint_to_storyboard
            from .detect import apply as apply_detections
            from .treat import apply as apply_treatments

            blueprint, plan_cues = plan
            cues = plan_cues if plan_cues is not None else self._ensure_cues()
            apply_treatments(blueprint, self.work_dir / "treated", self._runner())
            apply_detections(blueprint, self.work_dir / "detections", self._runner())
            self.storyboard = blueprint_to_storyboard(
                blueprint, cues, lyrics, fallback_backgrounds=self.backgrounds
            )
            source = "storyboard" if plan_cues is not None else "blueprint"
        else:
            cues = self._ensure_cues()
            self.storyboard = plan_storyboard(
                self.spec,
                lyrics,
                cues,
                duration,
                self.backgrounds,
                self.grid,
                taglines=self.spec.extra.get("taglines") or {},
            )
        summary_path = self.work_dir / "storyboard.json"
        summary_path.write_text(
            json.dumps(storyboard_summary(self.storyboard), indent=2), encoding="utf-8"
        )
        return StageResult(
            "plan",
            "DONE",
            detail=f"{len(self.storyboard.frames)} frames ({source})",
            artifacts=[Artifact("plan", "storyboard", summary_path)],
        )

    def _do_build(self, force: bool) -> StageResult:
        storyboard = self._ensure_storyboard()
        theme = load_theme(self.spec.theme_name)
        self.build_manifest = compose_project(
            self.spec,
            storyboard,
            theme,
            self._ensure_transcript(),
            self._runner(),
        )
        return StageResult(
            "build",
            "DONE",
            detail=self.build_manifest["project"],
            artifacts=[Artifact("build", "index", Path(self.build_manifest["index"]))],
        )

    def _do_check(self, force: bool) -> StageResult:
        renderer = self.services.get("renderer")
        code, output = renderer.check(Path(self.spec.out_dir))
        summary = getattr(renderer, "parse_check", lambda _o: {})(output)
        (self.work_dir / "check.log").write_text(output, encoding="utf-8")
        errors = summary.get("errors")
        failed = code != 0 or (errors is not None and errors > 0)
        detail = f"errors={errors} warnings={summary.get('warnings')}"
        return StageResult("check", "FAILED" if failed else "DONE", detail=detail)

    def _do_snapshot(self, force: bool) -> StageResult:
        renderer = self.services.get("renderer")
        times = self.snapshot_times or self._default_snapshot_times()
        paths = renderer.snapshot(Path(self.spec.out_dir), times)
        return StageResult(
            "snapshot",
            "DONE",
            detail=f"{len(paths)} snapshot(s)",
            artifacts=[Artifact("snapshot", "image", p) for p in paths],
        )

    def _do_render(self, force: bool) -> StageResult:
        renderer = self.services.get("renderer")
        # name the file after the project folder (unique per run), and make it
        # absolute: the renderer runs with cwd=project
        out = unique_path(
            (self.spec.out_dir.parent / "renders" / f"{self.spec.out_dir.name}.mp4").resolve()
        )
        path = renderer.render(Path(self.spec.out_dir), out, self.spec.fps)
        return StageResult(
            "render",
            "DONE",
            detail=str(path),
            artifacts=[Artifact("render", "video", Path(path))],
        )

    # -- helpers --------------------------------------------------------------

    def _duration(self) -> float:
        if self.transcript is not None and self.transcript.duration:
            return float(self.transcript.duration)
        return float(self.spec.duration or 180.0)

    def _ensure_cues(self):
        if self.cues is not None:
            return self.cues
        cues_path = self.work_dir / "cues.json"
        if cues_path.exists():
            self.cues = cues_from_list(json.loads(cues_path.read_text(encoding="utf-8")))
            return self.cues
        raise SlopcoreFactoryError("no cues available; run the align stage first")

    def _ensure_transcript(self):
        if self.transcript is not None:
            return self.transcript
        path = self.work_dir / "transcript.json"
        if path.exists():
            self.transcript = transcript_from_dict(json.loads(path.read_text(encoding="utf-8")))
            return self.transcript
        raise SlopcoreFactoryError("no transcript available; run the align stage first")

    def _ensure_storyboard(self) -> Storyboard:
        if self.storyboard is None:
            self._do_plan(force=True)
        assert self.storyboard is not None
        return self.storyboard

    def _default_snapshot_times(self) -> list[float]:
        if self.storyboard is None:
            return []
        times: list[float] = []
        for frame in self.storyboard.frames:
            for group in frame.groups:
                if group.cues:
                    times.append(round(group.cues[0].start + 1.0, 2))
                if len(times) >= 4:
                    break
            if len(times) >= 4:
                break
        return times

    def _write_run_manifest(self) -> None:
        payload = {
            "song_id": self.spec.song_id,
            "title": self.spec.title,
            "lyrics": str(self.spec.lyrics_path),
            "project": str(self.spec.out_dir),
            "theme": self.spec.theme_name,
            "stages": [
                {"stage": r.stage, "status": r.status, "detail": r.detail} for r in self.results
            ],
        }
        (self.work_dir / "run.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
