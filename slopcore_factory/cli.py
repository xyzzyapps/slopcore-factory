"""Command line interface.

    slopcore_factory run     --lyrics songs/foo/lyrics.md --audio songs/foo/assets/bgm.mp3
    slopcore_factory build   --lyrics songs/foo/lyrics.md            # generate the project
    slopcore_factory render  --lyrics songs/foo/lyrics.md            # full chain + MP4
    slopcore_factory status  --out songs/foo.song

Each stage command runs its prerequisites, so ``render`` implies song -> build.
Heavy stages are cached; pass ``--force`` to redo them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .clipgen import EvoLinkClipProvider
from .config import build_spec
from .errors import SlopcoreFactoryError
from .locator import ServiceLocator
from .logging_setup import get_logger, setup_logging
from .pipeline import Pipeline
from .process import SubprocessRunner
from .render import HyperframesRenderer
from .song import SunoSongProvider, SuppliedSongProvider
from .timing import LineAligner, WhisperTranscriber

log = get_logger("cli")

# command -> the stage we run up to (inclusive)
TARGETS = {
    "song": "song",
    "align": "align",
    "plan": "plan",
    "build": "build",
    "check": "check",
    "snapshot": "snapshot",
    "render": "render",
    "run": "render",
}

HELP = {
    "init": "scaffold a song folder (lyrics.md, assets/, song.json)",
    "song": "acquire or generate the audio track",
    "align": "transcribe the audio and align lyric lines",
    "plan": "build the storyboard (frames, groups, anchors)",
    "build": "generate the HyperFrames project",
    "check": "run hyperframes check on the generated project",
    "snapshot": "render still frames at lyric reveal times",
    "render": "run the whole chain and render the MP4",
    "run": "run the whole chain (snapshot optional)",
    "status": "print the last run manifest for a project",
    "blueprint": "generate the storyboard blueprint (offline or LLM)",
    "analyze": "word gaps (+ optional vocal stem) for the song",
    "lipsync": "plan lipsync windows and write them into the blueprint",
    "clips": "generate the Seedance clips named by the blueprint (dry-run free)",
    "avsync": "measure clip drift against the reference vocal",
    "covers": "add cover windows for clips whose sync drifted",
    "review": "snapshot the built project and write a review report",
    "overlay": "render the lyrics-only layer as a transparent MOV (for an NLE)",
    "storyboard": "print the plan, or write storyboard.md beside the lyrics",
    "match": "cut a render at its scenes and match each segment to a clip",
    "doctor": "check python, ffmpeg, node, and the optional extras",
    "repl": "interactive shell over every factory capability",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slopcore-factory", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in [
        "init",
        "song",
        "align",
        "plan",
        "build",
        "check",
        "snapshot",
        "render",
        "run",
        "status",
        "blueprint",
        "analyze",
        "lipsync",
        "clips",
        "avsync",
        "covers",
        "review",
        "overlay",
        "storyboard",
        "match",
        "doctor",
        "repl",
    ]:
        sp = sub.add_parser(name, help=HELP[name])
        if name == "status":
            sp.add_argument("--out", required=True, type=Path, help="generated project directory")
            continue
        if name == "doctor":
            continue  # no arguments
        _add_common(sp)
        if name in {"run", "render"}:
            sp.add_argument("--snapshot", action="store_true", help="also render still frames")
        if name in {"blueprint", "repl"}:
            sp.add_argument("--llm", action="store_true", help="use the LLM storyboard generator")
            sp.add_argument("--brief", default=None, help="creative brief for the storyboard")
            sp.add_argument("--budget", type=float, default=None, help="budget cap in USD")
        if name == "analyze":
            sp.add_argument(
                "--separate", action="store_true", help="separate the vocal stem (demucs)"
            )
        if name == "lipsync":
            sp.add_argument("--clip-min", type=float, default=4.0)
            sp.add_argument("--clip-max", type=float, default=8.0)
            sp.add_argument("--plate", default="hero")
            sp.add_argument("--style", default="")
        if name == "clips":
            sp.add_argument("--quality", default="720p")
        if name == "avsync":
            sp.add_argument("--threshold", type=float, default=0.6)
        if name == "storyboard":
            sp.add_argument(
                "mode",
                nargs="?",
                choices=["print", "write", "run"],
                default="print",
                help="print the plan, write it beside the lyrics, or execute it",
            )
        if name == "match":
            sp.add_argument("--render", type=Path, default=None, help="video to match")
            sp.add_argument("--threshold", type=float, default=0.12, help="scene-change threshold")
            sp.add_argument("--otio", action="store_true", help="also write an OTIO timeline")
    return parser


def _add_common(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--lyrics", required=True, type=Path, help="path to lyrics.md")
    sp.add_argument("--out", type=Path, default=None, help="generated project directory")
    sp.add_argument("--audio", type=Path, default=None, help="supplied audio track")
    sp.add_argument(
        "--transcript", type=Path, default=None, help="existing word-level transcript.json"
    )
    sp.add_argument(
        "--background", type=Path, action="append", default=[], help="background clip (repeatable)"
    )
    sp.add_argument(
        "--generate-song", action="store_true", help="generate the song with Suno (paid)"
    )
    sp.add_argument(
        "--generate-clips", action="store_true", help="generate b-roll with Seedance (paid)"
    )
    sp.add_argument("--duration", type=float, default=None, help="target song length in seconds")
    sp.add_argument("--title", default=None)
    sp.add_argument("--theme", default=None)
    sp.add_argument("--fps", type=int, default=None)
    sp.add_argument("--whisper-model", default=None)
    sp.add_argument("--hyperframes-version", default=None)
    sp.add_argument("--snapshot-times", default=None, help="comma-separated sample times")
    sp.add_argument("--dry-run", action="store_true", help="no paid calls; local placeholders only")
    sp.add_argument(
        "--song-backend",
        choices=["supplied", "suno", "dryrun", "yue", "ace_step"],
        default=None,
        help="song source (default: supplied, or suno with --generate-song)",
    )
    sp.add_argument(
        "--song-command", default=None, help="wrapper command for the yue / ace_step backends"
    )
    sp.add_argument(
        "--supersede-reason",
        default=None,
        help="record why a previously failed paid attempt may be retried",
    )
    sp.add_argument("--force", action="store_true", help="ignore stage caches")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except SlopcoreFactoryError as exc:
        print(f"error: {exc}")
        out = getattr(args, "out", None)
        lyrics = getattr(args, "lyrics", None)
        if out or lyrics:
            base = Path(out) if out else Path("songs") / _slug(Path(lyrics).stem)
            print(f"log:   {base.parent / (base.name + '.work') / 'logs'}")
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    if args.command not in {"doctor", "status", "init"}:
        from .doctor import require_tools

        require_tools()
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "status":
        return _cmd_status(args.out)
    if args.command == "doctor":
        return _cmd_doctor(args)
    if args.command == "repl":
        return _cmd_repl(args)
    if args.command == "blueprint":
        return _cmd_blueprint(args)
    if args.command == "analyze":
        return _cmd_analyze(args)
    if args.command == "lipsync":
        return _cmd_lipsync(args)
    if args.command == "clips":
        return _cmd_clips(args)
    if args.command == "avsync":
        return _cmd_avsync(args)
    if args.command == "covers":
        return _cmd_covers(args)
    if args.command == "review":
        return _cmd_review(args)
    if args.command == "overlay":
        return _cmd_overlay(args)
    if args.command == "storyboard":
        return _cmd_storyboard(args)
    if args.command == "match":
        return _cmd_match(args)

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    log.info("slopcore-factory %s -> %s", spec.song_id, spec.out_dir)

    services = _services(spec)
    pipeline = Pipeline(spec, services, work, snapshot_times=_parse_times(args.snapshot_times))
    results = pipeline.run(until=TARGETS[args.command], skip=_skip_for(args), force=args.force)
    _print_results(results)
    return 1 if pipeline.failed() else 0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_spec(args: argparse.Namespace):
    out = args.out or (Path("songs") / _slug(args.lyrics.stem))
    overrides = {
        key: value
        for key, value in {
            "theme": args.theme,
            "fps": args.fps,
            "whisper_model": args.whisper_model,
            "hyperframes_version": args.hyperframes_version,
            "budget_usd": getattr(args, "budget", None),
            "brief": getattr(args, "brief", None),
            "song_backend": getattr(args, "song_backend", None),
            "song_command": getattr(args, "song_command", None),
            "supersede_reason": getattr(args, "supersede_reason", None),
        }.items()
        if value is not None
    }
    if getattr(args, "dry_run", False):
        overrides["dry_run"] = True
    return build_spec(
        args.lyrics,
        out,
        audio_path=args.audio,
        transcript_path=args.transcript,
        backgrounds=list(args.background or []),
        generate_song=args.generate_song,
        generate_clips=args.generate_clips,
        duration=args.duration,
        title=args.title,
        overrides=overrides,
    )


def _services(spec) -> ServiceLocator:
    from .dryrun import DryRunSongProvider, DryRunTranscriber, is_dry_run

    runner = SubprocessRunner()
    services = ServiceLocator()
    services.register_instance("runner", runner)
    services.register_instance("aligner", LineAligner())
    services.register_instance("transcriber", WhisperTranscriber(spec.whisper_model, spec.language))
    services.register_instance("song_provider", _song_provider(spec))
    services.register("clip_generator", EvoLinkClipProvider)
    services.register_instance("renderer", HyperframesRenderer(spec.hyperframes_version, runner))

    if is_dry_run(spec):
        log.info("dry-run: using local placeholder providers")
        services.register_instance("transcriber", DryRunTranscriber())
        services.register_instance("song_provider", DryRunSongProvider())
    return services


def _song_provider(spec):
    """Resolve the song backend named by the spec (default: supplied, no API)."""
    backend = spec.extra.get("song_backend") or ("suno" if spec.generate_song else "supplied")
    command = spec.extra.get("song_command")
    if backend == "suno":
        return SunoSongProvider(take=int(spec.extra.get("suno_take", 1)))
    if backend == "dryrun":
        from .dryrun import DryRunSongProvider

        return DryRunSongProvider()
    if backend == "yue":
        from .localgen import YuESongProvider

        return YuESongProvider(command=command)
    if backend == "ace_step":
        from .localgen import AceStepSongProvider

        return AceStepSongProvider(command=command)
    return SuppliedSongProvider()


def _work_dir(spec) -> Path:
    out = Path(spec.out_dir)
    return out.parent / f"{out.name}.work"


def _skip_for(args: argparse.Namespace) -> set[str]:
    skip: set[str] = set()
    if args.command != "snapshot" and not getattr(args, "snapshot", False):
        skip.add("snapshot")
    return skip


def _parse_times(value: str | None) -> list[float]:
    if not value:
        return []
    return [float(part) for part in re.split(r"[,\s]+", value.strip()) if part]


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "song"


def _print_results(results) -> None:
    print()
    print(f"{'stage':<10} {'status':<9} detail")
    print("-" * 64)
    for result in results:
        print(f"{result.stage:<10} {result.status:<9} {result.detail}")
    print()


def _cmd_analyze(args: argparse.Namespace) -> int:
    from .workflows import analyze_song

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    analysis = analyze_song(spec, work, _services(spec), separate=args.separate)
    stem = "separated" if analysis.has_stem else "full mix"
    print(f"words: {analysis.word_count}   gaps: {len(analysis.gaps)}   stem: {stem}")
    for gap in analysis.gaps[:8]:
        print(f"  gap {gap.start:8.2f} - {gap.end:8.2f}  ({gap.duration:.2f}s)")
    if len(analysis.gaps) > 8:
        print(f"  ... {len(analysis.gaps) - 8} more")
    return 0


def _cmd_lipsync(args: argparse.Namespace) -> int:
    from .blueprint import validate_blueprint
    from .budget import report as budget_report
    from .workflows import plan_lipsync

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    blueprint = plan_lipsync(
        spec,
        work,
        _services(spec),
        clip_min=args.clip_min,
        clip_max=args.clip_max,
        plate=args.plate,
        style=args.style or "",
    )
    problems = validate_blueprint(blueprint)
    print(
        f"windows: {len(blueprint.lipsync)}   clips: {len(blueprint.seedance)}   "
        f"sung: {blueprint.sung_seconds}s"
    )
    print(budget_report(blueprint))
    print("validation: " + ("OK" if not problems else "; ".join(problems)))
    return 0


def _cmd_clips(args: argparse.Namespace) -> int:
    from .workflows import clips_dir, generate_clips

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    _blueprint, paths = generate_clips(spec, work, _services(spec), quality=args.quality)
    print(f"clips: {len(paths)} -> {clips_dir(spec)}")
    return 0


def _cmd_avsync(args: argparse.Namespace) -> int:
    from .workflows import run_avsync

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    _blueprint, results, summary = run_avsync(spec, work, _services(spec), threshold=args.threshold)
    print(summary)
    for result in results:
        state = "in sync" if result.in_sync else f"drift at {result.divergence}s"
        print(f"  {result.clip:<8} {state}")
    return 0


def _cmd_covers(args: argparse.Namespace) -> int:
    from .workflows import apply_covers

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    _blueprint, results, covers = apply_covers(spec, work, _services(spec))
    drifted = [r for r in results if not r.in_sync]
    print(f"checked {len(results)} clip(s); {len(drifted)} drifted; added {len(covers)} cover(s)")
    for cover in covers:
        print(f"  {cover.clip}  {cover.song_t0:.2f}s  {cover.words[:60]}")
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    from .workflows import review

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    services = _services(spec)
    Pipeline(spec, services, work).run(until="build", skip={"snapshot"})
    times, paths, report = review(spec, work, services)
    print(f"review: {len(paths)} snapshot(s) at {times}")
    print(f"report: {report}")
    return 0


def _cmd_overlay(args: argparse.Namespace) -> int:
    from .workflows import render_overlay

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    path = render_overlay(spec, work, _services(spec))
    print(f"overlay: {path}")
    return 0


def _cmd_storyboard(args: argparse.Namespace) -> int:
    from .storyboard_md import apply_settings, plan_path, plan_text, settings_of, write_plan

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    if args.mode == "write":
        print(f"storyboard: {write_plan(spec, work)}")
        return 0
    if args.mode == "run":
        plan = plan_path(Path(spec.lyrics_path).parent)
        if plan.exists():
            apply_settings(spec, settings_of(plan.read_text(encoding="utf-8")))
        results = Pipeline(spec, _services(spec), work).run(until="render", skip={"snapshot"})
        _print_results(results)
        return 0 if all(result.status != "FAILED" for result in results) else 1
    print(plan_text(spec, work))
    return 0


def _cmd_match(args: argparse.Namespace) -> int:
    from .match import candidate_clips, match, to_otio, write_json, write_otio

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    services = _services(spec)

    song_dir = Path(spec.lyrics_path).parent
    name = Path(spec.out_dir).name
    renders = Path(spec.out_dir).parent / "renders"
    render = Path(args.render) if args.render else renders / f"{name}.mp4"
    if not render.exists():
        print(f"no render to match: {render}")
        return 1

    candidates = candidate_clips(song_dir / "assets" / "clips", song_dir / "assets" / "media")
    segments = match(
        render, candidates, runner=services.get("runner"), fps=spec.fps, threshold=args.threshold
    )
    for seg in segments:
        print(
            f"  {seg.index:02d}  {seg.start:7.3f}-{seg.end:7.3f}  {seg.clip:<16} "
            f"score {seg.score:+.3f}  margin {seg.margin:+.3f}"
        )
    print(f"match: {write_json(segments, renders / f'{name}-match.json')}")
    if args.otio:
        lyrics = renders / f"{name}-lyrics.mov"
        timeline = to_otio(
            segments,
            fps=spec.fps,
            lyrics=lyrics if lyrics.exists() else None,
            song=Path(spec.audio_path) if spec.audio_path else None,
            name=spec.title,
        )
        print(f"otio: {write_otio(timeline, renders / f'{name}-davinci.otio')}")
    return 0


def _cmd_blueprint(args: argparse.Namespace) -> int:
    from .blueprint import save_blueprint, validate_blueprint
    from .blueprint_gen import generate
    from .budget import apply_estimate
    from .budget import report as budget_report
    from .lyrics import parse_lyrics
    from .serde import cues_from_list

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    services = _services(spec)

    # the blueprint needs the aligned lyric timings, so run song+align first
    Pipeline(spec, services, work).run(until="align", skip={"snapshot"})
    cues = cues_from_list(json.loads((work / "cues.json").read_text(encoding="utf-8")))
    duration = spec.duration or 180.0
    transcript = work / "transcript.json"
    if transcript.exists():
        duration = float(
            json.loads(transcript.read_text(encoding="utf-8")).get("duration") or duration
        )

    blueprint = generate(
        spec,
        parse_lyrics(spec.lyrics_path),
        cues,
        duration,
        spec.theme_name,
        use_llm=args.llm,
        brief=args.brief or str(spec.extra.get("brief", "")),
    )
    if args.budget:
        blueprint.budgets.cap_usd = float(args.budget)
    apply_estimate(blueprint)

    path = save_blueprint(blueprint, work / "blueprint.yaml")
    problems = validate_blueprint(blueprint)
    print(f"blueprint: {path}")
    print("validation: " + ("OK" if not problems else "; ".join(problems)))
    print(budget_report(blueprint))
    return 0


def _cmd_repl(args: argparse.Namespace) -> int:
    from .repl import Repl

    spec = _make_spec(args)
    work = _work_dir(spec)
    setup_logging(work / "logs")
    Repl(spec, work, _services(spec)).cmdloop()
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    lyrics = Path(args.lyrics)
    # a lyrics.md already names its own song folder; else fall back to the stem
    default = (
        lyrics.parent if lyrics.name.lower() == "lyrics.md" else Path("songs") / _slug(lyrics.stem)
    )
    base = Path(args.out or default)
    (base / "assets" / "clips").mkdir(parents=True, exist_ok=True)
    (base / "assets" / "ref").mkdir(parents=True, exist_ok=True)
    if not lyrics.exists():
        lyrics.parent.mkdir(parents=True, exist_ok=True)
        lyrics.write_text(
            "---\ntitle: Untitled\nlength_sec: 180\n---\n\n# Untitled\n\n```\n"
            "[Intro]\nFirst line here\n\n[Verse 1]\nLine one\nLine two\n\n"
            "[Chorus]\nHook line\n```\n",
            encoding="utf-8",
        )
    song_json = base / "song.json"
    if not song_json.exists():
        song_json.write_text(
            json.dumps({"title": "Untitled", "length_sec": 180, "aspect": "1280x720"}, indent=2),
            encoding="utf-8",
        )
    print(f"scaffolded: {base}")
    print(f"  lyrics: {lyrics}")
    print(f"  drop audio at: {base / 'assets' / 'bgm.mp3'}")
    print(f"  then run: slopcore-factory build --lyrics {lyrics} --out {base}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import checks, report

    rows = checks()
    print(report(rows))
    # the tools are required; the extras only disable features
    return 0 if all(row.ok for row in rows if row.required) else 1


def _cmd_status(out: Path) -> int:
    work = Path(out).parent / f"{Path(out).name}.work"
    run = work / "run.json"
    if not run.exists():
        print(f"no run manifest at {run}")
        return 1
    print(run.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
