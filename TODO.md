# TODO — slopcore-factory

Reusable, headless pipeline: **lyrics + storyboard -> HyperFrames project -> MP4**.
Extracted from `please-continue-video`. No Studio UI.

## Contract (target — CONFIRM before implementing)

- **Input**: a song folder with `lyrics.md` (required) + a **storyboard** (required, format TBD)
  + the song audio (provided; or generated with `--generate-song`) + background footage
  (provided; or `--generate-clips`; or a synthesized plate).
- **Output**: one video file (`renders/<song>.mp4`).

Open questions (see "I/O pivot" below).

## Phase 0 — Skeleton — DONE
- [x] pyproject, requirements, .gitignore, package dirs, `.venv`.

## Phase 1 — Shared modules — DONE
- [x] errors, models (data structures first), interfaces, locator, config, logging, process, cache.

## Phase 2 — Feature slices — DONE
- [x] lyrics, song (supplied/optional Suno), timing (whisper + align + file reuse),
      beats, media (loop/synth plate), storyboard (planner), theme, compose, render.

## Phase 3 — CLI + orchestrator — DONE
- [x] pipeline (song->align->beats->media->plan->build->check->[snapshot]->render, cached/resumable).
- [x] cli (init|song|align|plan|build|check|snapshot|render|run|status), __main__.

## Phase 4 — Templates — DONE (externalized)
- [x] All HTML/JS lives in Jinja: index.html.j2, frame.html.j2,
      partials/media.html.j2, partials/group.html.j2, partials/timeline.js.j2, storyboard.md.j2.
- [x] compose.py builds plain data only (tokens, tiles, timeline events); no inline markup/script.
- [x] theme_broadside.json + vendored fonts.

## Phase 5 — Tests — DONE
- [x] lyrics, models, timeline/align, storyboard, compose, pipeline (fakes; no network/spend). 22 passing.

## Phase 6 — Regression on please-continue data — PARTIAL
- [x] Build from real lyrics + bgm + existing transcript + c3 loop.
- [x] `hyperframes check` = 0 errors, 0 warnings.
- [ ] snapshots at reveal times.
- [ ] full render to MP4.

## Phase 7 — Docs + commit — PENDING
- [ ] SPEC.md, README.md, git commit.

## Hardcoded song assumptions — REMOVED
- [x] `storyboard.py` TAGLINES (machine copy) -> now `spec.extra["taglines"]`, default empty.
- [x] `clips.py` SHOTS/CINEMATIC_BASE (monitor-wall imagery) -> now `spec.extra["clip_prompts"]`/`["clip_style"]`.
- [x] `song.py` DEFAULT_STYLE (Portishead) -> generic fallback; real style from `prompts/suno-style.md`.
- [x] `song.py` negative_tags / vocal_gender -> from spec/extra.
- [ ] Remaining generic heuristics (HELD_SECTIONS, STOPWORDS, canvas/tempo defaults) stay as
      documented, overridable defaults — not song content.

## I/O pivot (needs approval)
- [ ] Decide storyboard input format:
      (A) machine-readable `storyboard.yaml` (frames, groups, copy bindings), or
      (B) parse the existing `STORYBOARD.md` (front-matter + Frame/Group sections).
- [ ] Decide storyboard authority: explicit frames/groups the factory obeys, or a brief
      (mood/sections/palette) the planner expands.
- [ ] Decide audio source: provided file (default) vs generated from lyrics.
- [ ] Implement storyboard loader + `compose` consumes it; planner becomes the fallback
      when no storyboard is supplied.

## End-user product path (reference: ESCAPE VELOCITY prompts)
Target UX: type lyrics -> factory generates song + storyboard -> iterate -> "make the video,
lyrics + lipsync, upper budget" -> MP4. User decisions recorded.

- [x] 1. Storyboard generator: `blueprint.py` schema + `blueprint_gen.py` (offline +
      LangChain single-call, validated, retries on the validator's complaints).
- [x] 2. Song takes: SunoSongProvider keeps every take, writes `assets/song_takes.json`,
      copies the chosen one to `assets/bgm.*`; REPL `takes` lists them.
- [x] 7. Budget guard: `budget.py` (estimate + cap + retry buffer), enforced at submit.
- [x] REPL: `slopcore_factory/repl.py` (lyrics/song/takes/blueprint/quote/compile/build/
      check/snapshot/render/status); CLI commands `blueprint` and `repl`.
- [x] Repo renamed to `slopcore-factory` (package `slopcore_factory`).
- [ ] 3. Audio analysis: word gaps DONE (`audio.py`, `analyze`); vocal stem via demucs
      when installed (falls back to the full mix); beat map already in `beats.py`.
- [ ] 4. Lipsync: window planner DONE (`lipsync.py`: starts in a gap, quotes exact
      words, alternates framing, 4-8 s); drift detection DONE (`detect_divergence`,
      measured on envelopes); cover planning DONE (`plan_cover`). No LatentSync (user
      decision). Remaining: actually generate the clips (paid, guarded) and run the
      avsync check on the returned soundtracks.
- [x] Blueprint -> compose: `compiler.py` maps the blueprint's shots/backgrounds to the
      render plan; the pipeline `plan` stage uses the blueprint when present. Verified:
      `check` passes (0 errors) on a blueprint-driven dry-run project.
- [x] Covers from drift: `lipsync.add_covers` + `workflows.apply_covers`; CLI/REPL
      `covers`. Re-estimates the budget and guards.
- [x] 6. Animation: `scenes.py` + a `scenes/` registry in the project; built-in scenes
      (`bars` on hooks, `marquee`, `scan`) are pure-function GSAP tweens wired into the
      frame timeline; a shot's `animation.module` can point at a custom HTML fragment
      that is copied into `scenes/` and inlined (the arbitrary-animation escape hatch).
      Verified: `check` passes with scenes (0 errors).
- [x] 5. Assets: SUPPLIED ONLY (user decision — no generation). `SuppliedClipProvider`
      resolves `assets/clips/<clip>.*`; shots without their own clip fall back to the
      user's `assets/clips` footage; plates/depth/tracking stay declared fields the user
      can point at files. No image/plate generation.
- [x] Regenerated BOTH songs with no API calls: please-continue (22 windows, 152.7 s,
      5 supplied clips, 5 frames) and all-hours (10 windows, 70.5 s, 4 supplied clips,
      3 frames). `check` = 0 errors, 0 warnings on both; snapshots confirm supplied
      footage + lyrics + animation scenes.
- [x] 8. Human review: `review` command snapshots the built project at shot midpoints and
      writes `reviews/review.md` (snapshot paths + per-shot table); REPL `review`.
      Verified on both songs.
- [x] Docs: SPEC.md (architecture, data model, contracts) + README.md.
- [x] Song backends: `supplied` (default) / `suno` / `dryrun` / `yue` / `ace_step`.
      `tools/yue2_wrapper.py` is the YuE2 adapter. YuE2 generation was confirmed to start
      on CPU (reached audio synthesis, 14/32 steps) but is not vendored: it is large,
      slow on CPU, and its weights are CC BY-NC. ACE-Step was blocked (spacy==3.8.4 has
      no Python 3.14 wheel); the backend option remains.
- [ ] Multi-agent storyboard panel (3 directors + judges) as an option over the
      single-call generator.
- [x] Dry-run mode (`dryrun.py`): local placeholders for song, transcript and clips, so
      the whole chain runs with zero spend. `--dry-run` / `SLOPCORE_FACTORY_DRY_RUN=1`.
- [x] Clip generation stage (`clipgen.py`): `generate_seedance_clips`; dry-run provider
      (tested) and EvoLink provider (paid, behind the guard). CLI/REPL `clips`.
- [x] avsync (`avsync.py`): decode clip + reference, measure drift, summarise; CLI/REPL
      `avsync`. Degrades gracefully when a clip has no audio stream.
- [ ] Wire the blueprint into `compose` — DONE (`compiler.py`; plan uses the blueprint).

## Open question
- [ ] LLM for the storyboard generator: set `SLOPCORE_FACTORY_LLM`
      (e.g. `anthropic:claude-sonnet-4-5`) + the provider key, and install `.[llm]`.
      Single-call generator exists; the reference's 3-directors/3-judges multi-agent
      version would be a follow-up.

## Discovered (needs approval before doing)
- [x] MoviePy backend — DECLINED. HyperFrames only. No `moviepy_compose.py`, no `--backend`.

## Maintenance
- [x] Dead-code audit + cleanup: removed unused protocols (`ClipProvider`, `Planner`,
      `SongProvider`, `Renderer`), `SubprocessRunner.echo`/`run_or_raise`,
      `ServiceLocator.has`/`clear`, `StageCache.invalidate`, `render.write_json`,
      `localgen.BACKENDS`, `Theme.font_ref`, `Group.title`/`accent_line`, `Frame.end`,
      `Storyboard.frame_duration_sum`, `Budgets.with_buffer`.
- [x] Unified clip generation: deleted `clips.py`; the pipeline's `media` stage and the
      `clips` command both use `clipgen` (blueprint-driven, audio-conditioned, guarded).
      Dropped the now-dead `clip_prompts`/`clip_style` config keys.
- [x] README rewritten for absolute beginners (install, song folder, first run,
      five-command walkthrough, REPL, cheat-sheet, free vs paid, troubleshooting, glossary).
- [x] Verified after cleanup: 75 tests pass, ruff clean, `check` on please-continue 0/0,
      `clips` (supplied) resolves 0 with no API.
