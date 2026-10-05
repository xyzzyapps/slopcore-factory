# slopcore-factory

Turn a folder with a song's **lyrics** into a **music video** — a HyperFrames project you
can preview, and an MP4 you can watch.

It does three things:

1. **Storyboard** — reads the lyrics and writes a plan (`blueprint.yaml`): which shot
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
```

Check it worked:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

You should see `75 passed` (or similar). If you do, everything is installed.

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
  transcript.json      <-- optional: word timings, if you already have them
  audiomap.json        <-- optional: beat grid
  song.json            <-- optional: settings (title, budget, ...)
```

Minimal `lyrics.md` (a `[Section]` header, then one line per line):

```markdown
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
```

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
| The storyboard plan | `songs/<out>.work/blueprint.yaml` |
| Review pictures + report | `songs/<out>/reviews/review.md` |
| **The finished video** | `songs/renders/<out>.mp4` |

Rendering takes a few minutes for a 3-minute song.

---

## 6. The interactive shell (REPL)

If you'd rather type commands one at a time:

```powershell
.\.venv\Scripts\slopcore-factory.exe repl --lyrics $ly --out $out --budget 120
```

```
slopcore> blueprint gen     # write the plan (offline)
slopcore> analyze           # find the gaps between words
slopcore> lipsync           # plan the lipsync windows
slopcore> clips             # use clips you supplied (no API)
slopcore> review            # stills + report
slopcore> render            # make the MP4
slopcore> quit
```

Type `help` inside the shell to list everything.

---

## 7. Commands cheat-sheet

| Command | What it does |
|---|---|
| `init` | creates an empty song folder to start from |
| `blueprint` | writes the storyboard plan (`blueprint.yaml`) |
| `analyze` | finds word gaps (needed for lipsync planning) |
| `lipsync` | plans the lipsync windows into the plan |
| `clips` | resolves the clips the plan asks for (supplied by default) |
| `avsync` | measures how far a generated clip drifts from the song |
| `covers` | plans a "cover" clip for the parts that drifted |
| `review` | takes stills at key moments and writes a report |
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

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `ffmpeg`/`ffprobe` not recognized | install ffmpeg and add its `bin` folder to PATH; open a new terminal |
| `npx not found` | install Node.js and open a new terminal |
| `check` fails | run `check` again and read the last lines; it names the file and the problem |
| No MP4 anywhere | `render` is a separate step — run `render` (or `run`) |
| "no audio found" | put the song at `assets/bgm.mp3` or pass `--audio PATH` |
| Render is slow | normal: it draws every frame; a 3-minute song takes a few minutes |
| `module not found` in Python | you forgot to activate/use `.\.venv\Scripts\...`; re-run install step 2 |

---

## 10. Glossary

- **Lyrics file** (`lyrics.md`) — your words, grouped by `[Section]` tags.
- **Storyboard / blueprint** — the plan: shots, timing, on-screen text, camera.
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

## 11. Tests and license

```powershell
.\.venv\Scripts\python.exe -m pytest -q      # all offline
.\.venv\Scripts\python.exe -m ruff check .   # lint
```

[PolyForm Noncommercial License 1.0.0](LICENSE). Noncommercial use only; see `LICENSE`.
