# TODO — slopcore-factory

Headless factory: **lyrics + `storyboard.md` -> HyperFrames project -> MP4**.
See `SPEC.md` for the design and `README.md` for the first-run walkthrough.

## Open

- [ ] `storyboard shot <id> build` is a convenience; the README documents `storyboard shot`
      as inspect-only and a full render as the way to see a change. Revisit if render time
      becomes a problem.
- [ ] Multi-agent storyboard panel (3 directors + judges) over the single-call generator.
- [ ] The remaining generic heuristics (`HELD_SECTIONS`, stopwords, canvas/tempo defaults)
      stay documented, overridable defaults — not song content.

## Deliberately not doing

- **One folded lipsync command.** `lipsync` / `clips` / `avsync` / `covers` stay separate so
  the free/paid line is clear; `lipsync` never spends.
- **Generate flags in the plan.** Paid generation runs only on `--song-backend suno` /
  `--generate-clips`; a file on disk must not turn on spend.
- **The decorative blueprint fields in `storyboard.md`** (`action`, `camera`, `lift`,
  `meme_visual`, per-shot `assets`, `detections`). They never reach the HyperFrames
  templates, so they would not change the MP4. (`chrome`/`section` stay — they drive the
  kicker.)
- **Retiring `storyboard.json` / `clips.md`**, or moving `.otio` under an `export`
  sub-command. Readers are pointed at `storyboard.md`, `match`, and `songs/renders/*.otio`.
- **Vocal stems (demucs).** The full-mix fallback is enough for gap finding and avsync.
- **LLM storyboard setup** beyond `.[llm]` + `SLOPCORE_FACTORY_LLM` (already documented).

## Done (condensed)

- **Phases 0-7**: skeleton, shared modules, feature slices, CLI + pipeline, Jinja templates,
  tests, docs; regressed on `please-continue` and `all-hours` (`check` 0/0).
- **End-user path**: blueprint schema + offline/LLM generator, Suno takes, budget guard,
  REPL, word gaps, lipsync planner + measured drift + covers, animation scenes, supplied
  assets, review.
- **Song backends**: `supplied` (default) / `suno` / `dryrun` / `yue` / `ace_step`; dry-run
  exercises the whole chain with zero spend.
- **all-yours**: Suno song (take 2, 179.4 s), 26 clips, per-shot media treatments, real YOLO
  boxes, text-only alpha lyrics overlay, OpenTimelineIO, per-line position + timing offset,
  REPL `treat`.
- **Storyboard step**: `storyboard.md` is the single live plan — `save_plan` writes through
  it and `ensure_blueprint` reads it, so lipsync/clips/covers/treat no longer strand edits
  in `blueprint.yaml`; the loader plus `storyboard print|write|run|shot`.
- **`match`**: cut a finished render at its scenes, match each segment back to a clip
  (OpenCV), emit an OTIO timeline.
- **`doctor`** preflight + clean CLI/REPL errors (no tracebacks).
- **Review fixes**: round-trip the fields the later stages read (`treatment_value`, `chrome`,
  `section`, clip `song_t0`/`path`/`cover_of`/`words`/`plate`, settings `lyrics`/`audio`/
  `duration`); a failed `check` gates the render; `storyboard run` prints the stage table;
  `init` defaults to the lyrics folder; clip `--supersede-reason`; the quote matches the run.
- **Maintenance**: two dead-code audits; `requirements.txt` synced with `pyproject.toml`.
