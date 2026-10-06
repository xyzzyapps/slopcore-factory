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

### Session
- [ ] Commit + push (storyboard pivot, `treat` command, dead-code cleanup).

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
