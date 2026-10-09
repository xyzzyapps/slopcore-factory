"""Shared workflows used by both the CLI and the REPL.

Keeps the command surfaces thin: each function resolves whatever prerequisite it
needs (aligned cues, an analysis, a blueprint), does the work, and persists the
result under the work directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from .audio import AudioAnalysis, analyze, load_analysis
from .blueprint import Blueprint
from .blueprint_gen import generate as generate_blueprint
from .budget import apply_estimate, guard
from .lipsync import add_covers, attach_to_blueprint, plan_clips, plan_windows
from .lyrics import parse_lyrics
from .models import Cue, FactorySpec, Transcript
from .pipeline import Pipeline
from .serde import cues_from_list, transcript_from_dict
from .storyboard_md import load_plan, save_plan


def ensure_aligned(spec: FactorySpec, work: Path, services) -> tuple[list[Cue], Transcript, float]:
    """Run song+align if needed and return (cues, transcript, duration)."""
    cues_path = Path(work) / "cues.json"
    transcript_path = Path(work) / "transcript.json"
    if not (cues_path.exists() and transcript_path.exists()):
        Pipeline(spec, services, work).run(until="align", skip={"snapshot"})
    cues = cues_from_list(json.loads(cues_path.read_text(encoding="utf-8")))
    transcript = transcript_from_dict(json.loads(transcript_path.read_text(encoding="utf-8")))
    duration = transcript.duration or spec.duration or 180.0
    return cues, transcript, duration


def analyze_song(spec: FactorySpec, work: Path, services, separate: bool = False) -> AudioAnalysis:
    """Word gaps (+ optional vocal stem) for the song."""
    _, transcript, _ = ensure_aligned(spec, work, services)
    return analyze(Path(spec.audio_path), transcript, Path(work), separate=separate)


def ensure_analysis(
    spec: FactorySpec, work: Path, services, separate: bool = False
) -> AudioAnalysis:
    path = Path(work) / "analysis.json"
    if path.exists():
        return load_analysis(path)
    return analyze_song(spec, work, services, separate=separate)


def song_backend(spec: FactorySpec) -> str:
    """The backend a run would use: explicit, else suno when generating, else supplied."""
    return str(spec.extra.get("song_backend") or ("suno" if spec.generate_song else "supplied"))


def ensure_blueprint(
    spec: FactorySpec, work: Path, services, use_llm: bool = False, brief: str = ""
) -> Blueprint:
    """Load the plan (``storyboard.md`` first), generating one if none exists."""
    lyrics = parse_lyrics(spec.lyrics_path)
    plan = load_plan(Path(spec.lyrics_path).parent, Path(work), lyrics)
    if plan is not None:
        plan[0].meta["song_backend"] = song_backend(spec)
        return plan[0]

    cues, _transcript, duration = ensure_aligned(spec, work, services)
    blueprint = generate_blueprint(
        spec,
        lyrics,
        cues,
        duration,
        spec.theme_name,
        use_llm=use_llm,
        brief=brief or str(spec.extra.get("brief", "")),
    )
    if not blueprint.budgets.cap_usd:
        blueprint.budgets.cap_usd = float(spec.extra.get("budget_usd", 0) or 0)
    blueprint.meta["song_backend"] = song_backend(spec)
    apply_estimate(blueprint)
    save_plan(blueprint, Path(spec.lyrics_path).parent, Path(work), spec=spec)
    return blueprint


def plan_lipsync(
    spec: FactorySpec,
    work: Path,
    services,
    clip_min: float = 4.0,
    clip_max: float = 8.0,
    plate: str = "hero",
    style: str = "",
) -> Blueprint:
    """Plan the lipsync windows, write them into the blueprint, enforce the cap."""
    analysis = ensure_analysis(spec, work, services)
    _cues, transcript, duration = ensure_aligned(spec, work, services)
    blueprint = ensure_blueprint(spec, work, services)

    windows = plan_windows(
        transcript.words, duration, analysis.gaps, clip_min=clip_min, clip_max=clip_max
    )
    clips = plan_clips(windows, blueprint.character, plate=plate, style=style)
    attach_to_blueprint(blueprint, windows, clips)
    guard(blueprint)
    save_plan(blueprint, Path(spec.lyrics_path).parent, Path(work), spec=spec)
    return blueprint


def clips_dir(spec: FactorySpec) -> Path:
    return Path(spec.out_dir) / "assets" / "clips"


def generate_clips(
    spec: FactorySpec, work: Path, services, quality: str = "720p"
) -> tuple[Blueprint, dict[str, Path]]:
    """Generate the Seedance clips named by the blueprint.

    Dry-run writes local placeholders; otherwise the paid provider runs behind
    the budget guard.
    """
    from .clipgen import (
        EvoLinkClipProvider,
        SuppliedClipProvider,
        generate_seedance_clips,
        reference_images,
    )
    from .dryrun import DryRunClipProvider, is_dry_run

    blueprint = ensure_blueprint(spec, work, services)
    if spec.generate_clips:
        guard(blueprint)
        provider = EvoLinkClipProvider(
            reference_audio=spec.audio_path,
            quality=quality,
            reference_images=reference_images(Path(spec.lyrics_path).parent),
            supersede_reason=str(spec.extra.get("supersede_reason") or "").strip() or None,
        )
    elif is_dry_run(spec):
        provider = DryRunClipProvider()
    else:
        # default: use files the user supplied, never call an API
        provider = SuppliedClipProvider(Path(spec.lyrics_path).parent)
    paths = generate_seedance_clips(blueprint, provider, clips_dir(spec))
    save_plan(blueprint, Path(spec.lyrics_path).parent, Path(work), spec=spec)
    return blueprint, paths


def run_avsync(
    spec: FactorySpec, work: Path, services, threshold: float = 0.6
) -> tuple[Blueprint, list, str]:
    """Check every generated singing clip against the reference vocal."""
    from .avsync import check_blueprint, summarise

    blueprint = ensure_blueprint(spec, work, services)
    results = check_blueprint(
        blueprint, Path(spec.audio_path), clips_dir(spec), threshold=threshold
    )
    return blueprint, results, summarise(results)


def apply_covers(
    spec: FactorySpec, work: Path, services, threshold: float = 0.6
) -> tuple[Blueprint, list, list]:
    """Measure drift, then add cover windows for the clips that drifted."""
    from .avsync import check_blueprint

    analysis = ensure_analysis(spec, work, services)
    _cues, transcript, _duration = ensure_aligned(spec, work, services)
    blueprint = ensure_blueprint(spec, work, services)
    results = check_blueprint(
        blueprint, Path(spec.audio_path), clips_dir(spec), threshold=threshold
    )
    divergences = {r.clip: r.divergence for r in results if r.divergence is not None}
    covers = add_covers(blueprint, divergences, transcript.words, analysis.gaps)
    guard(blueprint)
    save_plan(blueprint, Path(spec.lyrics_path).parent, Path(work), spec=spec)
    return blueprint, results, covers


def sing(
    spec: FactorySpec, work: Path, services, quality: str = "720p"
) -> tuple[Blueprint, dict[str, Path], list, list]:
    """The whole singing path in one command.

    Plans the lipsync windows, resolves (or generates) the clips, measures the
    drift, then adds the covers — each step writing back through the plan.
    """
    plan_lipsync(spec, work, services)
    blueprint, paths = generate_clips(spec, work, services, quality=quality)
    blueprint, results, _summary = run_avsync(spec, work, services)
    blueprint, _results, covers = apply_covers(spec, work, services)
    return blueprint, paths, results, covers


def review(
    spec: FactorySpec,
    work: Path,
    services,
    times: list[float] | None = None,
    max_shots: int = 8,
) -> tuple[list[float], list[Path], Path]:
    """Snapshot the built project at shot midpoints and write a review report.

    This is the human-in-the-loop step: look at the frames, decide what to change
    in the blueprint, regenerate. It makes no calls beyond the local renderer.
    """
    blueprint = ensure_blueprint(spec, work, services)
    shots = sorted(blueprint.shots, key=lambda s: s.t0)
    if times is None:
        if not shots:
            times = []
        else:
            step = max(1, len(shots) // max_shots)
            times = [round((s.t0 + s.t1) / 2.0, 2) for s in shots[::step]][:max_shots]

    renderer = services.get("renderer")
    paths = list(renderer.snapshot(Path(spec.out_dir), times)) if times else []

    reviews_dir = Path(spec.out_dir) / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Review",
        "",
        f"project: {spec.out_dir}",
        f"shots: {len(shots)}   sample times: {times}",
        "",
        "## Snapshots",
        "",
    ]
    lines += [f"- {path}" for path in paths] or ["- (none)"]
    lines += ["", "## Shots", ""]
    for shot in shots:
        lines.append(
            f"- {shot.id}  [{shot.t0}, {shot.t1}]  tier={shot.motion_tier}  "
            f"clip={shot.seedance_clip or '-'}  scene={shot.animation.scene or '-'}"
        )
    report = reviews_dir / "review.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return times, paths, report


def render_overlay(spec: FactorySpec, work: Path, services) -> Path:
    """Render the lyrics-only layer as a transparent ProRes 4444 MOV.

    Composes a transparent, media-less variant of the project (no clips, scrim or
    grain) and renders it with HyperFrames' alpha-preserving MOV format, so the
    text can be layered over the footage in an NLE.
    """
    from .compose import compose_project
    from .pipeline import unique_path
    from .theme import load_theme

    pipeline = Pipeline(spec, services, work)
    pipeline.run(until="plan", skip={"snapshot"})
    storyboard = pipeline.storyboard
    if storyboard is None:
        raise RuntimeError("overlay needs a storyboard (run the plan stage first)")
    project = Path(spec.out_dir).parent / f"{Path(spec.out_dir).name}-lyrics"
    compose_project(
        spec,
        storyboard,
        load_theme(spec.theme_name),
        pipeline._ensure_transcript(),
        services.get("runner"),
        project_dir=project,
        overlay=True,
    )
    out = unique_path(
        (Path(spec.out_dir).parent / "renders" / f"{Path(spec.out_dir).name}-lyrics.mov").resolve()
    )
    return services.get("renderer").render(project, out, spec.fps, fmt="mov", workers=1)
