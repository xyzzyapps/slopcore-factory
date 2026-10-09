# TODO — slopcore-factory

Headless factory: **lyrics + `storyboard.md` -> HyperFrames project -> MP4**.
No Studio UI. See `SPEC.md` for the design.

## Open

### Storyboard step
- [ ] `storyboard shot <id>` should run a slice (rebuild for one shot); it only inspects now.
- [ ] Retire the remaining user-facing formats: `storyboard.json` (work dir, internal) and
      `clips.md`; make `.otio` a `storyboard export otio` sub-command.
- [ ] The markdown carries the run-relevant fields; the decorative blueprint fields
      (`action`, `camera`, `lift`, `meme_visual`, per-shot `assets`, `detections`) are not
      represented and default on load.
- [ ] `storyboard run` takes the generate flags (song/clips) from the spec, not the plan.

### End-user product path
- [ ] Lipsync: generate the singing clips (paid, guarded) and run the avsync check on the
      returned soundtracks.
- [ ] Vocal-stem separation via demucs (falls back to the full mix when absent).
- [ ] Multi-agent storyboard panel (3 directors + judges) over the single-call generator.
- [ ] LLM storyboard: set `SLOPCORE_FACTORY_LLM` + the provider key and install `.[llm]`.
- [ ] Remaining generic heuristics (`HELD_SECTIONS`, stopwords, canvas/tempo defaults) stay
      documented, overridable defaults — not song content.

### Review (2026-10-09) follow-ups
- [x] One plan file: `save_plan` writes `storyboard.md` when it exists, and the mutating
      commands (lipsync, clips, covers, treat) plus `ensure_blueprint` read/write through
      it, so their edits are no longer stranded in `blueprint.yaml`.
- [x] Round-trip the fields the later stages read: `treatment_value` (`value` column),
      `chrome`, clip `song_t0` (`start`), `path`, `cover_of`; a clip with no start inherits
      its lipsync row's start (avsync); `apply_settings` applies `audio`/`duration`.
- [x] A failed `check` stops the chain; `storyboard run` prints the stage table.
- [x] The CLI and REPL catch `SlopcoreFactoryError` and print the log dir; `doctor` checks
      the tools + the optional extras.
- [x] `init` defaults to the `lyrics.md` folder and prints `slopcore-factory`.
- [x] `--supersede-reason` reaches clip submission; the treated-file cache key includes
      `treatment_value`.
- [x] The quote matches the run: no plate dollars (image generation is a non-goal), Suno
      only for a Suno run.
- [x] One lipsync command: `sing` (lipsync -> clips -> avsync -> covers), CLI + REPL.
- [x] `storyboard shot <id> build` re-runs that shot's treatment and rebuilds the project.
- [x] The markdown round-trips the remaining fields: shot `section`/`action`/`camera`/
      `lift`/`meme_visual`, a `## shot assets` table (plate/depth/tracking), clip `words`/
      `plate`, and the settings `lyrics`/`song_backend`/`generate_song`/`generate_clips`.
- [x] A missing required tool is a clean error (`doctor.require_tools` in the CLI; the REPL
      catches `OSError`).
- [ ] Still open: the multi-agent storyboard panel (a TODO feature, not a defect).

### Session
- [ ] Commit + push (storyboard pivot, `treat`, `match`, `doctor`, the review fixes).

## Done (condensed)

- **Phases 0-7**: skeleton, shared modules, feature slices, CLI + pipeline, Jinja templates,
  tests, docs. Regressed on `please-continue` and `all-hours` (`check` 0/0).
- **End-user path**: blueprint schema + offline/LLM generator, Suno takes, budget guard,
  REPL, audio analysis (word gaps), lipsync planner + measured drift + covers, animation
  scenes, supplied assets, review.
- **Song backends**: `supplied` (default) / `suno` / `dryrun` / `yue` / `ace_step`; dry-run
  mode runs the whole chain with zero spend.
- **all-yours**: lyrics, Suno song (take 2, 179.4 s), 26 clips, per-shot media treatments
  (slow+interpolate / pingpong / hold / stutter), real YOLO boxes, text-only alpha lyrics
  overlay, OpenTimelineIO timeline + clip list, per-line position (`bottom`) and timing
  offset (`I'll keep it on` +3 s), REPL `treat`.
- **Storyboard step**: `storyboard.md` (strict markdown) is the authority — loader
  (`storyboard_md.parse` / `load_plan`) + `storyboard` command (`print` / `write` / `run` /
  `shot`); the old `STORYBOARD.md` dump is retired so `build` cannot clobber the plan.
- **Maintenance**: two dead-code audits (unused protocols/functions/params/constants/fields,
  orphan template, stale deps); `requirements.txt` synced with `pyproject.toml`.
- **Decisions**: HyperFrames only (MoviePy declined); assets supplied not generated; no API
  calls by default; lipsync measured with no fallback model; renders never overwrite.
