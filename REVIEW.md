# Review — slopcore-factory

Reviewed 2026-10-09 against the code in `slopcore_factory/`, `tests/`, `README.md`, `SPEC.md`, and `TODO.md`.

The question was ease of use and completeness: can someone go from a lyrics file to a watchable video, and do the advertised steps (storyboard, timing, lipsync, clips, review, render) actually finish the job.

## Verdict

The free path is complete enough to use. `lyrics.md` plus optional audio and clips becomes a HyperFrames project and an MP4, with no API calls, a stage cache, a budget guard, and a dry-run that exercises the chain locally. About 107 offline tests cover the planner, the markdown plan, compose, treatments, lipsync math, avsync, and the pipeline.

The product is harder to drive than that summary suggests. The README teaches three different plans (the automatic planner, `blueprint.yaml`, and `storyboard.md`). Once `storyboard.md` exists it wins, and several later commands keep writing the file that no longer wins. Lipsync, clip generation, avsync, and covers are implemented as separate commands, and the data they need does not all survive a round-trip through the file the docs call the source of truth. A failed `check` does not stop `render`.

Someone who only wants a lyric video with their own footage can succeed by following section 4 of the README (`build --dry-run`, then a real `render`). Someone who wants the singing-shot workflow described in sections 5–8 will hit silent data loss.

## What is in good shape

- **Default is free.** Supplied audio is the song backend. Clip generation uses files already in `assets/clips/` unless `--generate-clips` is set. Dry-run swaps in local placeholders (`dryrun.py`).
- **One lyrics file is enough to start.** The deterministic planner (`storyboard.py` → `blueprint_gen.generate_offline`) builds chapters, shots, and lyric modes with no hand-written plan.
- **The render plan is real.** `compiler.py` turns a blueprint into frames, and `compose.py` emits a HyperFrames project from Jinja (index, frames, scenes, fonts). Built-in scenes are `bars`, `marquee`, `scan`, `blocks`, and `yolo`.
- **Timing works offline.** A supplied `transcript.json` is preferred. Otherwise Whisper runs locally. Word gaps (`audio.find_gaps`) feed the lipsync window planner.
- **Lipsync math is implemented.** Windows are 4–8 s, start in a gap, and quote the words (`lipsync.plan_windows`). Drift is measured by energy-envelope correlation (`avsync.py`). Covers resume at the last gap before the drift (`lipsync.plan_cover`).
- **Treatments exist.** `slow`, `pingpong`, `hold`, and `stutter` are real ffmpeg graphs (`treat.py`), with tests.
- **Paid calls are guarded.** `budget.guard` refuses a step over `cap_usd`. Generated clips are reused if the `.mp4` is already there. A failed Suno attempt can be retried with `--supersede-reason`.
- **Renders do not overwrite.** Output names go `name.mp4`, `name-2.mp4`, … (`pipeline.unique_path`).
- **The README is honest about cost and privacy.** It says a lipsync window is a plan until clips exist, lists EvoLink prices, and warns that singing-clip audio is uploaded to a public temporary host.
- **Errors have types.** `errors.py` defines a single base class so the pipeline can print a stage failure instead of a traceback. The pipeline uses that for `song` through `render`.

## Ease of use

### Two plans, and the README mixes them

The pipeline loads a plan in this order (`storyboard_md.load_plan`):

1. `storyboard.md` beside `lyrics.md`
2. else `<out>.work/blueprint.yaml`
3. else the automatic planner

`lipsync`, `clips`, `covers`, `blueprint`, and `review` all read and write `blueprint.yaml` only (`workflows.py`). They do not update `storyboard.md`.

`storyboard write` / REPL `storyboard write` render whatever `load_plan` already returned. After `storyboard.md` exists, that is the markdown file, so a write does not pick up lipsync or clip edits that landed in the yaml.

The README’s “real thing” (section 5) starts with `blueprint`, which writes the yaml. Section 6 then says `storyboard.md` is the source of truth and `storyboard run` executes it. The output table says the plan lives at `songs/<out>/storyboard.md`. `write_plan` actually writes it next to the lyrics file, which is often a different folder from `--out`.

A first session therefore has three directories:

| Thing | Where it actually goes |
|---|---|
| Project HTML | `--out` (default `songs/<lyrics-stem>/`) |
| Stage cache, cues, `blueprint.yaml`, logs | `<out>.work/` |
| `storyboard.md` | the folder that contains `lyrics.md` |

`status` only looks at `<out>.work/run.json`. There is no command that prints these three paths together.

### `init` scaffolds the wrong folder

`init` requires `--lyrics`. The song folder defaults to `songs/<stem-of-the-lyrics-file>`. For `songs/my-song/lyrics.md` the stem is `lyrics`, so assets and `song.json` are created in `songs/lyrics/` while the lyrics file is created at the path you passed. The follow-up line it prints uses `slopcore_factory` (underscore). The installed script is `slopcore-factory`.

The reliable invocation is `init --lyrics songs/my-song/lyrics.md --out songs/my-song`. Nothing in `--help` says the two paths must name the same folder.

### The command surface is flat

There are 24 subcommands. Every one except `status` takes the full common flag set (`--generate-song`, `--song-backend`, `--supersede-reason`, `--whisper-model`, …), including `init` and `storyboard print`. `--help` does not show a short path vs a paid path.

There is no preflight. The first dry-run calls ffmpeg via `subprocess.run(..., check=True)` inside `DryRunSongProvider`. A missing ffmpeg raises `CalledProcessError` or `FileNotFoundError`. The pipeline only catches `SlopcoreFactoryError`, so the documented first command dies as a traceback. The same is true of `npx` missing, except `render.resolve_npx` does raise `RenderError` once a HyperFrames stage runs.

Out-of-band commands (`analyze`, `lipsync`, `clips`, `storyboard`, `blueprint`, …) do not catch `SlopcoreFactoryError` either. The REPL has no error handler, so `no blueprint yet` ends the session.

`storyboard run` applies a few settings and then runs the pipeline through `render` without printing the stage table. The other stage commands print one. A long render looks hung.

### `--force` does not mean “redo this shot”

`song` and `align` are hash-cached and honor `--force`. `beats` and `media` honor `--force` but the cache key is “the json file exists”, so a changed clip is invisible until `--force`.

`plan` ignores `force`. Treatments skip rendering when `<work>/treated/<shot>-<treatment>.mp4` already exists, and the filename does not include `treatment_value`. Changing `slow` from 2.5 to 4 reuses the old file. YOLO boxes are cached as `<shot-id>.json` with no hash of the source frame, so a replaced clip keeps the old boxes until that json is deleted.

### `check` does not gate `render`

`_do_check` records `FAILED` and returns. `Pipeline.run` only stops the chain when a stage raises. `run`, `render`, and `storyboard run` therefore render a project that failed `check`, then the CLI exits 1 because some stage failed. The README says check must pass before rendering.

### Optional pieces are easy to miss at install time

`pip install -e ".[dev]"` (the README install) pulls pytest and ruff. Beat tracking needs `.[beats]` (librosa). `match` needs `.[match]` (OpenCV). The LLM storyboard needs `.[llm]`. YOLO needs `ultralytics`, which is not an extra. Vocal separation needs the `demucs` binary, which is not an extra. Paid song and clip generation need a sibling checkout of `slopcore-hf` (`vendor.py` adds `../slopcore-hf/src` to `sys.path`). That dependency is not in `pyproject.toml`. The error if it is missing is “check the workspace layout”.

`requirements-dev.txt` includes librosa. `requirements.txt` does not. The two files and the README install line describe different environments.

## Completeness

### The lyric video

Complete for the scoped job: parse lyrics, align, plan shots, attach backgrounds (explicit, discovered, or a synthesized plate), build HTML, check, snapshot, render, and write a lyrics-only ProRes MOV (`overlay`). Themes, per-line position, and per-line time offset reach the templates. Render output and the OTIO export from `match` are there.

The automatic planner is a lyric stack with `bars` on hook-like section names and `scan` elsewhere (`blueprint_gen.generate_offline`). Camera, action, character, and clip prompts stay empty on that path. That matches the SPEC non-goal of “no Studio”, and it is a thin video if the user expected the all-yours treatment without writing a plan.

### `storyboard.md` is not a full blueprint

The markdown round-trips title, canvas, chapters, shot times, framing, tier, clip id, treatment name, scene, media path, lyric mode/position/offset, song style, clip prompt, sing, reference flag, lipsync rows, animation, and plates. Tests cover that subset.

These fields exist on the blueprint and are dropped on the way through the template (`templates/storyboard.plan.md.j2`) and the parser:

| Field | Why it matters |
|---|---|
| `SeedanceClip.song_t0`, `words`, `path`, `cover_of`, `plate` | Avsync slices the reference vocal at `song_t0`. After a reload that value is 0, so the check compares the clip to the start of the song. `path` is recovered only when `<clip-id>.mp4` happens to sit in the clips directory. |
| `Shot.treatment_value` | The parser looks for a `value` column the template never writes. An explicit slow factor or hold trim becomes 0, which means “auto”. |
| `Shot.action`, `camera`, `lift`, `meme_visual`, `assets`, `chrome` | SPEC and TODO already say these default on load. `chrome` is how a shot gets its on-screen kicker (`compiler.py`). A kicker set only in yaml disappears after `storyboard write`. |
| `Shot.detections` | Recomputed from the YOLO cache when the media file still exists. They are not part of the plan you edit. |
| Settings `audio`, `duration`, `lyrics`, `retry_buffer`, `seedance_quality` | Stored in the blueprint object. `apply_settings` (used by `storyboard run`) copies only canvas, fps, theme, `budget_usd`, and `dry_run`. Editing the audio path or duration in the plan does not change the run. |
| `song_backend`, `generate_song`, `generate_clips` | Not settings at all. TODO already notes that `storyboard run` takes generate flags from the CLI spec. |

`storyboard shot <id>` prints one shot. It does not rebuild that shot. TODO lists this as open.

### Lipsync is a plan plus a manual chain

What exists: window planning, Seedance prompt text, budget estimate, paid or supplied clip resolution, drift measurement, cover windows.

What the user still has to do by hand, and what does not stick:

1. `lipsync` writes windows into `blueprint.yaml` and retargets overlapping shots at `seedance` clips.
2. `clips --generate-clips` (paid) or files named `<clip-id>.mp4` produce the pictures. The singing path uploads an audio slice to uguu.se or tmpfiles.org. That only runs when you pass the flag. The provider calls `submit_once` without `--supersede-reason` (`clipgen.EvoLinkClipProvider`). The song backend does pass it. A failed clip cannot be retried with a recorded reason.
3. `avsync` and `covers` update the yaml again. Covers are new windows. Nothing in `covers` generates the replacement clip.
4. If `storyboard.md` exists, the next `build` ignores steps 1–3. Avsync on a blueprint loaded from markdown uses `song_t0=0`.

Vocal-stem separation is a flag (`analyze --separate`). With no `demucs` on `PATH` it logs and uses the full mix. TODO still lists this as open, which matches the code: there is a fallback, not a finished stem path.

There is no single command that means “plan windows, generate the singing clips, measure drift, and cut covers”. The REPL exposes the same pieces as separate verbs.

### Paid and local generation

| Backend | State |
|---|---|
| `supplied` | Default. Complete. |
| `dryrun` | Complete for song, transcript, and placeholder clips. |
| `suno` | Implemented behind `slopcore-hf` and `EVOLINK_API_KEY`. Keeps every take and writes `song_takes.json`. The REPL can list takes. It cannot switch the chosen take. |
| `yue`, `ace_step` | Adapters. They run a user-supplied command (`SLOPCORE_YUE_CMD` / `SLOPCORE_ACE_STEP_CMD`). Weights are not vendored. SPEC says a YuE2 run was seen to start on CPU. |
| Seedance clips | Implemented, paid, guarded, resumable when the mp4 already exists. Reference images (up to 6) upload on the paid path. |
| LLM storyboard | One LangChain call (`blueprint --llm`), with one retry on validation errors. The multi-director panel in TODO is not built. Offline generation remains the default when `SLOPCORE_FACTORY_LLM` is unset. |
| Plates | The budget charges `$0.068` per plate entry. No command generates a plate. SPEC says image generation is a non-goal, so the line item on the quote describes spend that cannot happen. |

The quote always adds the Suno price (`$0.118`) even when the song is a file you supplied (`budget.estimate`). A tight `--budget` can refuse a clips-only run because of a song generation that will not run.

### Review, match, overlay

`review` snapshots up to eight shot midpoints and writes `reviews/review.md` as a path list plus a shot table. It does not judge framing, lyric collisions, or sync. The shot list comes from `ensure_blueprint` (the yaml, or a freshly generated one), which can disagree with the storyboard the build just compiled.

`overlay` builds a second project and renders a transparent MOV. That path is implemented.

`match` cuts a finished render on scene changes and writes a JSON report, plus an OTIO timeline with `--otio`. It needs OpenCV. It is an after-the-fact tool, not part of `run`.

### Tests vs the gaps above

The suite is offline and uses fakes for ffmpeg, Whisper, and HyperFrames. It locks the markdown round-trip for the fields the template actually writes, and it locks pipeline failure when `check` is the last stage (`test_pipeline_fails_when_check_fails` stops at `check`). It does not lock:

- `render` being skipped after a failed check
- lipsync windows and `song_t0` surviving `storyboard.md`
- `storyboard write` after `lipsync` keeping the new windows
- `init` placing assets next to the lyrics file
- a clean error when ffmpeg or npx is absent

## Doc drift worth fixing with the code

- README section 5 says the storyboard is `songs/<out>/storyboard.md`. It is written beside the lyrics.
- README section 2 says `.[dev]` and “104 passed”. Dev extras omit librosa; `requirements-dev.txt` includes it. The test count in the tree is 107 functions.
- `logging_setup.py` says logs go to `<out>/../logs`. The CLI passes `<out>.work/logs`.
- SPEC section 9 says `storyboard` takes `print` / `write` / `run`. The REPL also has `shot`, and `run` does not print stages.
- `init`’s printed next step uses the wrong executable name.

## What to fix first

These are the changes that would make the advertised workflow true. They are ordered by how often a new user hits them.

1. **One plan file.** Make `lipsync`, `clips`, `covers`, `treat`, and `review` read and write `storyboard.md` when it exists, and stop leaving the live edits in `blueprint.yaml`. Until that lands, the README should teach a single sequence and say which file each command edits.
2. **Round-trip the fields the later stages read.** At least `song_t0`, clip `path`, `treatment_value`, and shot `chrome`. Point avsync at the lipsync row’s start if the clip row has no `song_t0`.
3. **Stop the pipeline on a failed check**, and print the stage table from `storyboard run`.
4. **Catch `SlopcoreFactoryError` (and missing ffmpeg / npx) at the CLI and REPL** and print the message plus the log path. Add a `doctor` command for Python, ffmpeg, ffprobe, Node, npx, and the optional extras.
5. **Fix `init`** so the default folder is the parent of `--lyrics` when the file is named `lyrics.md`, and print `slopcore-factory`.
6. **Decide the lipsync product.** Either one command that plans, resolves clips, measures, and writes covers back into the plan, or a short “this is as far as the free path goes” stop in `lipsync`’s own output. Pass `--supersede-reason` through clip submission the way the song backend does.
7. **Make the quote match the run.** Omit the Suno line when the backend is `supplied`. Omit plate dollars until a plate command exists. Include `treatment_value` in the treated-file cache key.

## Where that leaves a user

Use it today for a lyric video from a lyrics file, a song file, and your own clips. Treat `storyboard.md` as the edit surface only after you know that lipsync, clip paths, treatment amounts, and avsync offsets still live in `<out>.work/blueprint.yaml` and are ignored on the next build. The singing-shot pipeline is a set of working parts, not a finished path.
