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
        "Commands: lyrics song takes storyboard treat blueprint analyze lipsync clips avsync "
        "covers review match doctor sing dryrun quote compile build check snapshot render status"
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
            from .storyboard_md import load_plan

            plan = load_plan(Path(self.spec.lyrics_path).parent, self.work, self._lyrics_doc())
            if plan is not None:
                self.blueprint = plan[0]
            elif self._blueprint_path().exists():
                self.blueprint = load_blueprint(self._blueprint_path())
            else:
                raise SlopcoreFactoryError("no blueprint yet; run 'blueprint gen'")
        return self.blueprint

    def _save_plan(self) -> None:
        """Write the plan back: ``storyboard.md`` when it exists, else the blueprint."""
        from .storyboard_md import load_plan, plan_path, render, song_style_for

        assert self.blueprint is not None
        song_dir = Path(self.spec.lyrics_path).parent
        path = plan_path(song_dir)
        plan = load_plan(song_dir, self.work, self._lyrics_doc())
        cues = plan[1] if plan else None
        if path.exists():
            path.write_text(
                render(self.blueprint, cues, song_style=song_style_for(self.spec)),
                encoding="utf-8",
            )
        else:
            save_blueprint(self.blueprint, self._blueprint_path())

    def _pipeline(self) -> Pipeline:
        return Pipeline(self.spec, self.services, self.work)

    def _run(self, until: str) -> None:
        results = self._pipeline().run(until=until, skip={"snapshot"})
        for result in results:
            print(f"  {result.stage:<10} {result.status:<9} {result.detail}")

    # -- commands ---------------------------------------------------------

    def onecmd(self, line: str):  # noqa: ANN201 - cmd.Cmd's contract
        """Catch factory errors so a missing prerequisite does not end the session."""
        try:
            return super().onecmd(line)
        except SlopcoreFactoryError as exc:
            print(f"error: {exc}")
            return False
        except OSError as exc:  # a missing tool, an unwritable file, ...
            print(f"error: {exc}")
            return False

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

    def do_storyboard(self, arg: str) -> None:
        """storyboard [print|write|run|shot <id>]   show, write, inspect or execute."""
        from .storyboard_md import apply_settings, plan_path, plan_text, settings_of

        parts = (arg or "").split()
        mode = parts[0] if parts else "print"
        path = plan_path(Path(self.spec.lyrics_path).parent)
        if mode == "run":
            if path.exists():
                apply_settings(self.spec, settings_of(path.read_text(encoding="utf-8")))
            self._run("render")
            return
        if mode == "shot":
            shot_id = parts[1] if len(parts) > 1 else ""
            self._show_shot(shot_id)
            if len(parts) > 2 and parts[2] == "build":
                self._rebuild_shot(shot_id)
            return
        if mode == "write":
            path.write_text(plan_text(self.spec, self.work), encoding="utf-8")
            print(f"storyboard: {path}")
            return
        print(plan_text(self.spec, self.work))

    def _show_shot(self, shot_id: str) -> None:
        from .storyboard_md import load_plan

        plan = load_plan(Path(self.spec.lyrics_path).parent, self.work, self._lyrics_doc())
        if plan is None:
            print("no plan yet (run 'storyboard write')")
            return
        blueprint, _cues = plan
        shot = next((s for s in blueprint.shots if s.id == shot_id), None)
        if shot is None:
            print(f"no such shot: {shot_id}")
            return
        clip_id = shot.seedance_clip or "-"
        print(f"{shot.id}  {shot.t0:.3f}-{shot.t1:.3f}  {shot.motion_tier}  clip={clip_id}")
        print(f"  treatment {shot.treatment} value {shot.treatment_value:g}")
        for entry in sorted(shot.type, key=lambda e: e.line):
            print(
                f"  line {entry.line}: {entry.text}  "
                f"[{entry.mode}/{entry.position} +{entry.offset:g}]"
            )
        clip = next((c for c in blueprint.seedance if c.clip == shot.seedance_clip), None)
        if clip and clip.prompt:
            print(f"  prompt: {clip.prompt}")

    def _rebuild_shot(self, shot_id: str) -> None:
        """Re-run one shot's treatment and rebuild the project so its frame is current."""
        from .treat import apply as apply_treatments

        blueprint = self._load_blueprint()
        done = apply_treatments(
            blueprint, self.work / "treated", self.services.get("runner"), shot_id
        )
        self._save_plan()
        for sid, path in done.items():
            print(f"  treated {sid}: {path}")
        self._run("build")

    def do_treat(self, arg: str) -> None:
        """treat [list | <shot> [treatment [value]]]   ffmpeg media treatments."""
        from .blueprint import TREATMENTS
        from .treat import apply as apply_treatments

        blueprint = self._load_blueprint()
        parts = (arg or "").split()
        if parts and parts[0] == "list":
            for shot in blueprint.shots:
                if shot.treatment and shot.treatment != "loop":
                    print(f"  {shot.id}: {shot.treatment} value {shot.treatment_value:g}")
            return
        only = None
        if parts:
            only = parts[0]
            shot = next((s for s in blueprint.shots if s.id == only), None)
            if shot is None:
                print(f"no such shot: {only}")
                return
            if len(parts) >= 2:
                treatment = parts[1]
                if treatment not in TREATMENTS:
                    print(
                        f"unknown treatment: {treatment} (one of {', '.join(sorted(TREATMENTS))})"
                    )
                    return
                shot.treatment = treatment
                shot.media = ""  # the old treated file no longer applies
                if len(parts) >= 3:
                    shot.treatment_value = float(parts[2])
                self._save_plan()
                print(f"{shot.id}: {treatment} value {shot.treatment_value:g}")
        done = apply_treatments(
            blueprint, self.work / "treated", self.services.get("runner"), only=only
        )
        if not done:
            print("nothing treated (treatment is 'loop', or there is no clip)")
            return
        for shot_id, path in done.items():
            print(f"  {shot_id}: {path}")

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
        from .workflows import song_backend

        blueprint.meta["song_backend"] = song_backend(self.spec)
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

    def do_match(self, arg: str) -> None:
        """match [video] [otio]   cut a render at its scenes and match each to a clip."""
        from .match import candidate_clips, match, to_otio, write_json, write_otio

        parts = (arg or "").split()
        otio = "otio" in parts
        paths = [part for part in parts if part != "otio"]
        name = Path(self.spec.out_dir).name
        renders = Path(self.spec.out_dir).parent / "renders"
        render = Path(paths[0]) if paths else renders / f"{name}.mp4"
        if not render.exists():
            print(f"no render to match: {render}")
            return
        song_dir = Path(self.spec.lyrics_path).parent
        candidates = candidate_clips(song_dir / "assets" / "clips", song_dir / "assets" / "media")
        segments = match(render, candidates, runner=self.services.get("runner"), fps=self.spec.fps)
        for seg in segments:
            print(
                f"  {seg.index:02d}  {seg.start:7.3f}-{seg.end:7.3f}  {seg.clip:<16} "
                f"score {seg.score:+.3f}  margin {seg.margin:+.3f}"
            )
        print(f"match: {write_json(segments, renders / f'{name}-match.json')}")
        if otio:
            lyrics = renders / f"{name}-lyrics.mov"
            timeline = to_otio(
                segments,
                fps=self.spec.fps,
                lyrics=lyrics if lyrics.exists() else None,
                song=Path(self.spec.audio_path) if self.spec.audio_path else None,
                name=self.spec.title,
            )
            print(f"otio: {write_otio(timeline, renders / f'{name}-davinci.otio')}")

    def do_sing(self, arg: str) -> None:
        """sing [quality]      plan lipsync, resolve clips, measure drift, add covers."""
        from .workflows import sing

        quality = (arg or "").strip() or "720p"
        blueprint, paths, results, covers = sing(
            self.spec, self.work, self.services, quality=quality
        )
        print(f"windows: {len(blueprint.lipsync)}   clips: {len(paths)}")
        for result in results:
            state = "in sync" if result.in_sync else f"drift at {result.divergence}s"
            print(f"  {result.clip:<8} {state}")
        print(f"covers: {len(covers)}")

    def do_doctor(self, arg: str) -> None:
        """doctor            check python, ffmpeg, node, and the optional extras."""
        from .doctor import checks, report

        print(report(checks()))

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
