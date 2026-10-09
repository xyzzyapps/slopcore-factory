# slopcore-factory

Turn a folder with a song's **lyrics** into a **music video** — a HyperFrames project you
can preview, and an MP4 you can watch.

It does three things:

1. **Storyboard** — reads the lyrics and writes a plan (`storyboard.md`): which shot
   happens when, what the words look like on screen, where the camera is.
2. **Timing** — lines the lyrics up with the song, word by word, and plans the moments
   where a singer would be on camera ("lipsync windows").
3. **Video** — builds an HTML/JavaScript composition (HyperFrames) with your clips, the
   lyrics, and animated graphics, then renders it to MP4.

> **Important, so you're not surprised:** by default it **uses files you give it**. It does
> not generate the song or the singing clips unless you explicitly ask for a paid/local
> generation run. A "lipsync window" is a *plan*; it only becomes a real lipsynced shot if
> the singing clips are generated (paid) or supplied by you.

See [SPEC.md](SPEC.md) if you want the full technical design.

---

## 1. What you need installed

You only need these once. Check each in PowerShell:

| Tool | Why | Check |
|---|---|---|
| **Python 3.11+** | runs this project | `python --version` |
| **ffmpeg** | reads/creates audio and video | `ffmpeg -version` |
| **Node.js** | runs the video builder (`npx hyperframes`) | `node --version` |

If a command says "not recognized", install that tool first (ffmpeg: get a build and put
its `bin` folder on PATH; Node: install from nodejs.org).

---

## 2. Install slopcore-factory

Copy-paste this, one line at a time:

```powershell
cd C:\Users\manic\Documents\PROG\moh\slopcore-factory

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
# optional extras: .[beats] (librosa), .[match] (OpenCV), .[llm] (LangChain)
```

Check it worked:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

You should see `116 passed` (or similar). If you do, everything is installed.

> Every command below starts with `.\.venv\Scripts\slopcore-factory.exe`. That's just "run
> the tool from this project's Python environment". You must run it from the
> `slopcore-factory` folder.

---

## 3. Make a song folder

A "song folder" is just a folder you create. The only file it **must** have is `lyrics.md`.

```
songs/my-song/
  lyrics.md            <-- required: the words
  assets/
    bgm.mp3            <-- the song (or use --audio)
    clips/             <-- your video clips (or use --background)
      c1.mp4
      c2.mp4
    ref/               <-- optional character images (up to 6) for generated clips
      01-face.png
  transcript.json      <-- optional: word timings, if you already have them
  audiomap.json        <-- optional: beat grid
  song.json            <-- optional: settings (title, budget, ...)
```

Minimal `lyrics.md` (a `[Section]` header, then one line per line):

````markdown
# MY SONG

```
[Intro]
Stay.

[Verse 1]
I know the hour you wake up
I know your coffee's cold

[Chorus]
Please continue
```
````

Nothing else is required to start. If you don't have `transcript.json`, the tool can make
one with Whisper (slower, local); if you don't have clips, it can synthesise a plain
background.

---

## 4. Your first run (free, no assets needed)

This runs everything locally with placeholder audio and clips, so you can see the whole
machine work without spending anything:

```powershell
.\.venv\Scripts\slopcore-factory.exe build --lyrics songs/my-song/lyrics.md --out songs/my-song-demo --dry-run
```

You'll see a table like:

```
song    DONE   songs\my-song-demo\assets\bgm.wav
align   DONE   52 words, 52 cues
plan    DONE   5 frames
build   DONE   songs\my-song-demo
```

Your generated project is now in `songs\my-song-demo\` — open `index.html` there, or run
`check` (below) to have the tool inspect it.

---

## 5. The real thing, step by step

Put your song at `songs/my-song/assets/bgm.mp3` and your clips in
`songs/my-song/assets/clips/`, then run these five commands:

```powershell
$ly = "songs/my-song/lyrics.md"
$out = "songs/my-song-video"

# 1) Write the storyboard plan
.\.venv\Scripts\slopcore-factory.exe blueprint --lyrics $ly --out $out --budget 120

# 2) Plan the lipsync windows (which moments need a singing shot)
.\.venv\Scripts\slopcore-factory.exe lipsync --lyrics $ly --out $out

# 3) Build the video project and check it
.\.venv\Scripts\slopcore-factory.exe check --lyrics $ly --out $out

# 4) Take still pictures to review, and write a report
.\.venv\Scripts\slopcore-factory.exe review --lyrics $ly --out $out

# 5) Render the MP4
.\.venv\Scripts\slopcore-factory.exe render --lyrics $ly --out $out
```

### Where your files end up

| What | Where |
|---|---|
| The video project (HTML/JS) | `songs/<out>/index.html` |
| The storyboard plan | `storyboard.md`, **beside `lyrics.md`** |
| Review pictures + report | `songs/<out>/reviews/review.md` |
| **The finished video** | `songs/renders/<out>.mp4` |
| Lyrics-only layer (alpha) | `songs/renders/<out>-lyrics.mov` |
| Editor timeline (OpenTimelineIO) | `songs/renders/<out>.otio` |

Rendering takes a few minutes for a 3-minute song.

Three places matter: the project in `--out`, the work dir at `<out>.work/` (stage cache,
cues, `blueprint.yaml`, logs), and the plan `storyboard.md` beside your `lyrics.md`. Run
`slopcore-factory doctor` to check your tools.

---

## 6. The interactive shell (REPL)

If you'd rather type commands one at a time:

```powershell
.\.venv\Scripts\slopcore-factory.exe repl --lyrics $ly --out $out --budget 120
```

```
slopcore> storyboard write  # write storyboard.md (the plan) beside the lyrics
slopcore> storyboard        # print it
slopcore> storyboard run    # execute it: align -> generate -> build -> check -> render
slopcore> storyboard shot sh03   # inspect one shot (times, lyrics, prompt)
slopcore> treat list        # the ffmpeg treatments per shot
slopcore> treat sh02 slow   # set + run a treatment
slopcore> analyze           # find the gaps between words
slopcore> review            # stills + report
slopcore> quit
```

Type `help` inside the shell to list everything.

---

## 7. Commands cheat-sheet

| Command | What it does |
|---|---|
| `init` | creates an empty song folder to start from |
| `blueprint` | writes the legacy plan (`blueprint.yaml`) |
| `storyboard` | prints the plan, writes `storyboard.md`, or runs it (`storyboard run`) |
| `analyze` | finds word gaps (needed for lipsync planning) |
| `lipsync` | plans the lipsync windows into the plan |
| `clips` | resolves the clips the plan asks for (supplied by default) |
| `avsync` | measures how far a generated clip drifts from the song |
| `covers` | plans a "cover" clip for the parts that drifted |
| `review` | takes stills at key moments and writes a report |
| `overlay` | renders the lyrics-only layer (text only, transparent) as a MOV for an editor |
| `match` | cuts a finished render at its scenes and matches each segment back to a clip |
| `doctor` | checks python, ffmpeg, node and the optional extras |
| `sing` | runs the whole singing path: lipsync -> clips -> avsync -> covers |
| `build` | builds the video project |
| `check` | lints/tests the project (must pass before rendering) |
| `snapshot` | saves still frames |
| `render` | renders the MP4 |
| `run` | does the whole chain (build -> check -> render) |
| `repl` | the interactive shell |
| `status` | shows what the last run did |

Useful extras: `--dry-run` (no API, placeholders), `--force` (redo cached steps),
`--budget 120` (hard spending cap in USD).

---

## 8. What's free, what costs money

**Free (local):** storyboard generation (offline), timing, lipsync *planning*, building,
checking, review, rendering, dry runs.

**Paid (opt-in only):** generating the song (`--song-backend suno`), generating the
singing/b-roll clips (`clips --generate-clips`). Both go through a budget guard and never
run unless you ask.

**Local models (free, but heavy):** YuE2 / ACE-Step can be wired in with
`--song-backend yue` / `ace_step` plus a command (see `tools/yue2_wrapper.py`). They need
large downloads and are very slow on CPU.

### About lipsync

`lipsync` writes a plan: windows of 4-8 seconds that start in a gap between words, each
with the exact words to sing. To see a real lipsynced shot you must either generate those
clips (paid) or drop files named after the clip ids (`ls01.mp4`, `ls02.mp4`, ...) into
`<song>/assets/clips/`. Otherwise the video shows your b-roll with lyrics and animated
graphics — no mouth movement.

---

## 9. External services used

Nothing outside your machine runs on a supplied-assets job except the two build-time
services at the bottom. The paid and network services only run when you ask for them.

### Only when you explicitly opt in

| Service | Used for | When it runs | Cost |
|---|---|---|---|
| **EvoLink** — `api.evolink.ai` | Suno song generation (`suno-v6-beta`) | `--song-backend suno` | ~$0.118 per request (4 takes) |
| **EvoLink** — `api.evolink.ai` | Seedance 2.5 clips (`seedance-2.5-reference-to-video`) | `clips --generate-clips` | 480p $0.138/s, 720p $0.296/s |
| **EvoLink Files** — `files-api.evolink.ai` | uploads image references (via the `slopcore-hf` client) | same as above | free |
| **uguu.se** (primary) / **tmpfiles.org** (fallback) | hosts the audio slice so Seedance can lip-sync to it (`@Audio1`) | `clips --generate-clips`, singing windows only | free, anonymous |
| **Your LLM provider** (Anthropic/OpenAI/...) via LangChain | AI storyboard (`blueprint --llm`) | only when `SLOPCORE_FACTORY_LLM` is set | your provider's rates |
| **Hugging Face Hub** | YuE2 weights (`m-a-p/YuE2-3B`, `m-a-p/YuE2-Vae`) | `--song-backend yue` | free download, ~7 GB |

Keys: `EVOLINK_API_KEY` for EvoLink; `SLOPCORE_FACTORY_LLM` plus your provider's key for
the LLM; `SLOPCORE_YUE_CMD` / `SLOPCORE_ACE_STEP_CMD` for the local song models.

### Always used (build/render time)

| Service | Used for | Notes |
|---|---|---|
| **npm registry** (`npx`) | downloads the pinned HyperFrames CLI (`hyperframes@0.8.116`) | first run downloads it; needs Node |
| **jsDelivr CDN** | the generated project loads GSAP 3.14.2 from `cdn.jsdelivr.net` | needs internet when you preview or render |
| **Hugging Face Hub** | faster-whisper model, when there is no `transcript.json` | `small.en`, downloaded once |

Configured but unused unless you install registry blocks: the HyperFrames registry URL
(`raw.githubusercontent.com/heygen-com/hyperframes`) in the generated `hyperframes.json`.

### Privacy note

The temporary file host (uguu.se / tmpfiles.org) is **anonymous and public**. The audio
slice it receives is a short excerpt of your song, retrievable by anyone with the URL for
48 hours (uguu) or 60 minutes (tmpfiles). It is used only on the paid clip-generation path,
and only for the seconds of audio a singing window needs. If that is not acceptable, do not
run `clips --generate-clips` — supply your own clips instead.

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `ffmpeg`/`ffprobe` not recognized | install ffmpeg and add its `bin` folder to PATH; open a new terminal |
| `npx not found` | install Node.js and open a new terminal |
| `check` fails | run `check` again and read the last lines; it names the file and the problem |
| No MP4 anywhere | `render` is a separate step — run `render` (or `run`) |
| "no audio found" | put the song at `assets/bgm.mp3` or pass `--audio PATH` |
| Render is slow | normal: it draws every frame; a 3-minute song takes a few minutes |
| A paid generation failed | failed tasks are not charged; retry with `--supersede-reason "why"` (recorded in the ledger) |
| `module not found` in Python | you forgot to activate/use `.\.venv\Scripts\...`; re-run install step 2 |

---

## 11. Glossary

- **Lyrics file** (`lyrics.md`) — your words, grouped by `[Section]` tags.
- **Storyboard** (`storyboard.md`) — the plan: settings, chapters, shots, lyrics, and the
  prompts sent to the servers. It is the source of truth: edit it, then `storyboard run`.
- **Shot** — one piece of the video (a few seconds) with its own look.
- **Frame** — a sub-composition of the video that covers a slice of the timeline.
- **Lipsync window** — a short planned clip where a singer is on camera.
- **Avsync** — measuring whether a generated clip's mouth matches the song.
- **Cover** — a replacement clip for the part of a take that drifted out of sync.
- **Scene** — an animated graphic layer (pulsing bars, a scrolling word wall, scan lines).
- **HyperFrames** — the HTML/JavaScript video framework the project builds on.
- **ffmpeg** — the tool that reads/writes audio and video.
- **Dry run** — everything with placeholders, nothing paid, nothing downloaded.

---

## 12. Tests and license

```powershell
.\.venv\Scripts\python.exe -m pytest -q      # all offline
.\.venv\Scripts\python.exe -m ruff check .   # lint
```

[PolyForm Noncommercial License 1.0.0](LICENSE). Noncommercial use only; see `LICENSE`.
