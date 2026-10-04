"""Shared test fixtures.

Nothing here touches the network, the browser, whisper or ffmpeg: the pipeline
is exercised through fakes so the suite is fast and free to run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


LYRICS_TEXT = """---
title: TEST SONG
length_sec: 24
aspect: 1280x720
---

# TEST SONG

Some prose that should be ignored.

```
[Intro]
Stay.
Look at me.

[Verse 1]
I know the hour you wake up
I know your coffee's cold
I keep it all

[Chorus]
Please continue
You could stay
Please continue
```
"""


@pytest.fixture
def lyrics_file(tmp_path: Path) -> Path:
    path = tmp_path / "lyrics.md"
    path.write_text(LYRICS_TEXT, encoding="utf-8")
    return path


@pytest.fixture
def fake_audio(tmp_path: Path) -> Path:
    path = tmp_path / "bgm.mp3"
    path.write_bytes(b"not-really-audio")
    return path


@pytest.fixture
def fake_clip(tmp_path: Path) -> Path:
    path = tmp_path / "background.mp4"
    path.write_bytes(b"not-really-a-video")
    return path


class FakeRunner:
    """Command runner that answers ffprobe and claims success otherwise."""

    def __init__(self, clip_seconds: float = 8.0) -> None:
        self.clip_seconds = clip_seconds
        self.calls: list[list[str]] = []

    def run(self, args, cwd=None, timeout=None):  # noqa: ANN001
        self.calls.append(list(args))
        program = Path(args[0]).name.lower()
        if "ffprobe" in program:
            return subprocess.CompletedProcess(args, 0, stdout=f"{self.clip_seconds}\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


class FakeTranscriber:
    """Returns word timings for the TEST SONG script, spaced 0.4 s apart."""

    SCRIPT = (
        "stay look at me i know the hour you wake up i know your coffee's cold "
        "i keep it all please continue you could stay please continue"
    )

    def transcribe(self, audio, lyrics, duration):  # noqa: ANN001
        from slopcore_factory.models import Transcript, Word

        words = []
        t = 0.5
        for token in self.SCRIPT.split():
            words.append(Word(token, round(t, 3), round(t + 0.35, 3)))
            t += 0.4
        return Transcript(engine="fake", duration=round(t + 1.0, 3), words=words)


@pytest.fixture
def fake_transcriber() -> FakeTranscriber:
    return FakeTranscriber()


class FakeRenderer:
    """Records renderer calls; check always passes unless told otherwise."""

    def __init__(
        self, check_code: int = 0, check_output: str = "0 error(s), 0 warning(s)\nCheck passed\n"
    ) -> None:
        self.check_code = check_code
        self.check_output = check_output
        self.checked: list[str] = []
        self.rendered: list[str] = []
        self.snapshot_times: list[float] = []

    def check(self, project):  # noqa: ANN001
        self.checked.append(str(project))
        return self.check_code, self.check_output

    def snapshot(self, project, times):  # noqa: ANN001
        self.snapshot_times = list(times)
        return []

    def render(self, project, out, fps):  # noqa: ANN001
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"fake-mp4")
        self.rendered.append(str(out))
        return Path(out)

    @staticmethod
    def parse_check(output: str) -> dict:
        return {"errors": 0, "warnings": 0, "passed": True}


@pytest.fixture
def fake_renderer() -> FakeRenderer:
    return FakeRenderer()
