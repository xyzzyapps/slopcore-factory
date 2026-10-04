"""Interactive REPL.

Every factory capability is reachable from here: parse lyrics, generate or load
the song (and audition its takes), generate / show / edit the blueprint, quote
the budget, build the HyperFrames project, check, snapshot and render.

    slopcore-factory repl --lyrics songs/foo/lyrics.md
"""

from __future__ import annotations

import cmd
import json
from pathlib import Path

from .blueprint import Blueprint, load_blueprint, save_blueprint, validate_blueprint
from .blueprint_gen import generate as generate_blueprint
from .budget import apply_estimate
from .budget import report as budget_report
from .errors import SlopcoreFactoryError
from .locator import ServiceLocator
from .logging_setup import get_logger
from .models import FactorySpec
from .pipeline import Pipeline
from .serde import cues_from_list
from .song import SunoSongProvider, SuppliedSongProvider

log = get_logger("repl")


class Repl(cmd.Cmd):
    """A tiny command shell over the factory."""

    intro = (
        "slopcore-factory REPL. Type 'help' for commands, 'quit' to leave.\n"
        "Commands: lyrics song takes blueprint analyze lipsync clips avsync covers review "
        "dryrun quote compile build check snapshot render status"
    )
    prompt = "slopcore> "

    def __init__(self, spec: FactorySpec, work_dir: Path, services: ServiceLocator) -> None:
        super().__init__()
        self.spec = spec
        self.work = Path(work_dir)
        self.services = services
        self._lyrics = None
        self.blueprint: Blueprint | None = None

    # -- helpers ----------------------------------------------------------

    def _lyrics_doc(self):
        if self._lyrics is None:
            from .lyrics import parse_lyrics

            self._lyrics = parse_lyrics(self.spec.lyrics_path)
        return self._lyrics

    def _ensure_cues(self):
        cues_path = self.work / "cues.json"
        if not cues_path.exists():
            print("aligning lyrics to the song (run 'song' first if it fails)...")
            Pipeline(self.spec, self.services, self.work).run(until="align", skip={"snapshot"})
        if not cues_path.exists():
            raise SlopcoreFactoryError("no cues; run 'song' then 'blueprint'")
        return cues_from_list(json.loads(cues_path.read_text(encoding="utf-8")))

    def _duration(self) -> float:
        transcript = self.work / "transcript.json"
        if transcript.exists():
            data = json.loads(transcript.read_text(encoding="utf-8"))
            if data.get("duration"):
                return float(data["duration"])
        return float(self.spec.duration or 180.0)

    def _blueprint_path(self) -> Path:
        return self.work / "blueprint.yaml"

    def _load_blueprint(self) -> Blueprint:
        if self.blueprint is None:
            if self._blueprint_path().exists():
                self.blueprint = load_blueprint(self._blueprint_path())
            else:
                raise SlopcoreFactoryError("no blueprint yet; run 'blueprint gen'")
        return self.blueprint

    def _pipeline(self) -> Pipeline:
        return Pipeline(self.spec, self.services, self.work)

    def _run(self, until: str) -> None:
        results = self._pipeline().run(until=until, skip={"snapshot"})
        for result in results:
            print(f"  {result.stage:<10} {result.status:<9} {result.detail}")

    # -- commands ---------------------------------------------------------

    def do_lyrics(self, arg: str) -> None:
        """lyrics            show the parsed lyrics (sections and lines)."""
        doc = self._lyrics_doc()
        print(f"{doc.title}: {len(doc.sections)} sections, {len(doc.lines)} lines")
        for section in doc.sections:
            print(f"  [{section.name}] {len(section.lines)} lines")

    def do_song(self, arg: str) -> None:
        """song [gen]        use the supplied track, or 'song gen' to generate takes."""
        generate = arg.strip() == "gen"
        self.spec.generate_song = generate
        provider = (
            SunoSongProvider(take=int(self.spec.extra.get("suno_take", 1)))
            if generate
            else SuppliedSongProvider()
        )
        self.services.register_instance("song_provider", provider)
        self._run("song")
        self.do_takes("")

    def do_takes(self, arg: str) -> None:
        """takes             list the generated song takes."""
        manifest = Path(self.spec.out_dir) / "assets" / "song_takes.json"
        if not manifest.exists():
            print("no takes manifest (use 'song gen')")
            return
        data = json.loads(manifest.read_text(encoding="utf-8"))
        print(f"chosen take: {data.get('chosen')}")
        for take in data.get("takes", []):
            print(f"  {take['take']}: {take['path']}")

    def do_blueprint(self, arg: str) -> None:
        """blueprint [gen|llm|show|path]   generate, show, or locate the blueprint."""
        mode = (arg or "gen").strip()
        if mode == "path":
            print(self._blueprint_path())
            return
        if mode == "show":
            self._show_blueprint()
            return

        lyrics = self._lyrics_doc()
        cues = self._ensure_cues()
        use_llm = mode == "llm"
        brief = str(self.spec.extra.get("brief", ""))
        print(f"generating blueprint ({'LLM' if use_llm else 'offline'})...")
        blueprint = generate_blueprint(
            self.spec,
            lyrics,
            cues,
            self._duration(),
            theme_name=self.spec.theme_name,
            use_llm=use_llm,
            brief=brief,
        )
        if not blueprint.budgets.cap_usd:
            blueprint.budgets.cap_usd = float(self.spec.extra.get("budget_usd", 0) or 0)
        apply_estimate(blueprint)
        self.blueprint = blueprint
        path = save_blueprint(blueprint, self._blueprint_path())
        print(f"blueprint: {path}")
        problems = validate_blueprint(blueprint)
        print("validation: OK" if not problems else "validation: " + "; ".join(problems))
        self._show_blueprint()

    def _show_blueprint(self) -> None:
        bp = self._load_blueprint()
        print(
            f"{bp.title}: {len(bp.chapters)} chapters, {len(bp.shots)} shots, "
            f"{len(bp.seedance)} clips, {len(bp.lipsync)} lipsync windows"
        )
        print(budget_report(bp))

    def do_quote(self, arg: str) -> None:
        """quote             show the planned budget."""
        bp = self._load_blueprint()
        apply_estimate(bp)
        print(budget_report(bp))

    def do_analyze(self, arg: str) -> None:
        """analyze [separate]  word gaps (+ optional vocal stem separation)."""
        from .workflows import analyze_song

        analysis = analyze_song(
            self.spec, self.work, self.services, separate=arg.strip() == "separate"
        )
        stem = "separated" if analysis.has_stem else "full mix"
        print(f"words: {analysis.word_count}   gaps: {len(analysis.gaps)}   stem: {stem}")

    def do_lipsync(self, arg: str) -> None:
        """lipsync           plan lipsync windows into the blueprint."""
        from .budget import report as budget_report
        from .workflows import plan_lipsync

        blueprint = plan_lipsync(self.spec, self.work, self.services)
        self.blueprint = blueprint
        print(
            f"windows: {len(blueprint.lipsync)}   clips: {len(blueprint.seedance)}   "
            f"sung: {blueprint.sung_seconds}s"
        )
        print(budget_report(blueprint))

    def do_clips(self, arg: str) -> None:
        """clips             generate the Seedance clips (dry-run = local placeholders)."""
        from .workflows import generate_clips

        blueprint, paths = generate_clips(self.spec, self.work, self.services)
        self.blueprint = blueprint
        print(f"clips: {len(paths)}")

    def do_avsync(self, arg: str) -> None:
        """avsync            measure clip drift against the reference vocal."""
        from .workflows import run_avsync

        _blueprint, results, summary = run_avsync(self.spec, self.work, self.services)
        print(summary)
        for result in results:
            state = "in sync" if result.in_sync else f"drift at {result.divergence}s"
            print(f"  {result.clip:<8} {state}")

    def do_dryrun(self, arg: str) -> None:
        """dryrun [on|off]   toggle paid calls (default: on = no spend)."""
        value = arg.strip().lower()
        self.spec.extra["dry_run"] = value != "off"
        print(f"dry_run = {self.spec.extra['dry_run']}")

    def do_covers(self, arg: str) -> None:
        """covers            add cover windows for clips whose sync drifted."""
        from .workflows import apply_covers

        blueprint, results, covers = apply_covers(self.spec, self.work, self.services)
        self.blueprint = blueprint
        drifted = [r for r in results if not r.in_sync]
        print(f"checked {len(results)}; {len(drifted)} drifted; added {len(covers)} cover(s)")

    def do_review(self, arg: str) -> None:
        """review            snapshot the project and write a review report."""
        from .workflows import review

        times, paths, report = review(self.spec, self.work, self.services)
        print(f"review: {len(paths)} snapshot(s) at {times}")
        print(f"report: {report}")

    def do_compile(self, arg: str) -> None:
        """compile           build the HyperFrames project from the plan."""
        self._ensure_cues()
        self._run("build")
        print(f"project: {self.spec.out_dir}")

    def do_build(self, arg: str) -> None:
        """build             alias for compile."""
        self.do_compile(arg)

    def do_check(self, arg: str) -> None:
        """check             run hyperframes check on the project."""
        self._run("check")

    def do_snapshot(self, arg: str) -> None:
        """snapshot          render still frames at lyric reveal times."""
        Pipeline(self.spec, self.services, self.work).run(until="snapshot")

    def do_render(self, arg: str) -> None:
        """render            render the MP4."""
        self._run("render")

    def do_status(self, arg: str) -> None:
        """status            show the last run manifest."""
        run = self.work / "run.json"
        print(run.read_text(encoding="utf-8") if run.exists() else "no run yet")

    def do_quit(self, arg: str) -> bool:
        """quit              leave the REPL."""
        print("bye")
        return True

    do_EOF = do_quit  # Ctrl-D

    def emptyline(self) -> bool:
        return False

    def default(self, line: str) -> None:
        print(f"unknown command: {line!r} (type 'help')")
