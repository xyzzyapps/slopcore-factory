# slopcore-factory

Turn a song folder into a **HyperFrames** project and a rendered MP4: lyrics + a
storyboard + the song + footage in, a video out. No Studio UI, no API calls by default.

It reproduces the hand-authored motion design of `please-continue-video` /
`all-hours-video`, plans **lipsync** the way the ESCAPE VELOCITY production did
(audio-conditioned windows, measured drift, covers), and layers **animation scenes** on
top of the lyrics.

See [SPEC.md](SPEC.md) for the architecture and data model.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
# dev + tests:
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

External tools used at build/render time: **ffmpeg** (probe/convert) and **Node/npx**
(the pinned HyperFrames CLI). Nothing is downloaded for a supplied-assets run.

## A song folder

```
songs/my-song/                (or any folder you pass with --lyrics)
  lyrics.md                   required: [Section] tags + lines (optional front-matter)
  assets/bgm.mp3              the song (or --audio / --song-backend ...)
  assets/clips/*.mp4          footage (or --background)
  transcript.json             optional: word timings (skips whisper)
  audiomap.json               optional: beat grid
  song.json                   optional: config (title, aspect, budget_usd, taglines, ...)
```

Everything is optional except `lyrics.md`. If `transcript.json` / `audiomap.json` are
absent, align/beats fall back to whisper/librosa.

## Quick start

```powershell
$ly = "..\please-continue-video\lyrics.md"

# 1. storyboard (blueprint.yaml) — offline by default, or --llm with SLOPCORE_FACTORY_LLM
slopcore-factory blueprint --lyrics $ly --out songs/please-continue --budget 120

# 2. plan lipsync windows into the blueprint
slopcore-factory lipsync   --lyrics $ly --out songs/please-continue

# 3. build + lint the HyperFrames project
slopcore-factory check     --lyrics $ly --out songs/please-continue

# 4. review: snapshot at shot midpoints + a written report
slopcore-factory review    --lyrics $ly --out songs/please-continue

# 5. render the MP4
slopcore-factory render    --lyrics $ly --out songs/please-continue
```

`check`/`review`/`render` run their prerequisites. Outputs: the project at
`songs/<name>/`, the report at `songs/<name>/reviews/review.md`, the video at
`songs/renders/<name>.mp4`.

## REPL

```powershell
slopcore-factory repl --lyrics $ly --out songs/please-continue --budget 120
slopcore> blueprint llm        # or: blueprint gen  (offline)
slopcore> analyze
slopcore> lipsync
slopcore> clips                # supplied by default (no API)
slopcore> avsync
slopcore> covers
slopcore> review
slopcore> render
```

## Song backends

Default is **supplied** (use the file in the folder; never calls an API).

| `--song-backend` | what it does |
|---|---|
| `supplied` | use `assets/bgm.*` (default) |
| `suno` | generate via EvoLink Suno (paid; keeps all takes) |
| `dryrun` | local placeholder for a free end-to-end run |
| `yue` | YuE2 via `SLOPCORE_YUE_CMD` (`tools/yue2_wrapper.py`) |
| `ace_step` | ACE-Step via `SLOPCORE_ACE_STEP_CMD` |

Local models run through a command that accepts `--request <json> --out <audio>`:

```powershell
$env:SLOPCORE_YUE_CMD = "python C:\path\to\slopcore-factory\tools\yue2_wrapper.py"
slopcore-factory song --lyrics $ly --out songs/x --song-backend yue
```

YuE2 needs Python 3.12 and (per its authors) a 24 GB GPU; it runs on CPU but is very slow.

## Free dry run

No API, no whisper, no real assets — everything local:

```powershell
slopcore-factory run --lyrics $ly --out songs/demo --dry-run
```

## Supplying assets

- audio: `--audio PATH` or `assets/bgm.mp3`
- footage: `--background PATH` (repeatable) or `assets/clips/*.mp4`
- word timings: `--transcript PATH` or `transcript.json`
- a clip per planned window: `assets/clips/<clip>.mp4` (e.g. `ls01.mp4`)

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

All tests are offline (fakes, synthetic audio). The suite covers the blueprint schema,
lipsync planning, drift detection, covers, the compiler, scenes, the review loop, the
song backends (including the yue2 adapter against a fake CLI), and the REPL.

## License

[PolyForm Noncommercial License 1.0.0](LICENSE). Noncommercial use only; see `LICENSE`.
