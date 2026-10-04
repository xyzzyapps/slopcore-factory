"""The yue2 adapter: contract with the factory + a fake yue2 CLI (no model)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools" / "yue2_wrapper.py"

FAKE_CLI = """\
import argparse
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("command")
p.add_argument("--request")
p.add_argument("--output")
p.add_argument("--device")
p.add_argument("--budget")
args, _ = p.parse_known_args()
song = Path(args.output) / "song"
song.mkdir(parents=True, exist_ok=True)
(song / "audio.flac").write_bytes(b"fLaC-fake")
(song / "result.json").write_text('{"status":"complete"}', encoding="utf-8")
"""


def _fake_yue2(tmp_path: Path) -> Path:
    fake = tmp_path / "fake"
    pkg = fake / "yue2"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "cli.py").write_text(FAKE_CLI, encoding="utf-8")
    return fake


def test_yue2_wrapper_produces_out(tmp_path: Path, monkeypatch) -> None:
    fake = _fake_yue2(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(fake))

    request = tmp_path / "request.json"
    request.write_text(
        json.dumps({"lyrics": "[Verse]\nStay.", "style": "noir", "seed": 3}),
        encoding="utf-8",
    )
    out = tmp_path / "out" / "bgm-yue.wav"

    subprocess.run(
        [sys.executable, str(WRAPPER), "--request", str(request), "--out", str(out)],
        check=True,
    )
    assert out.exists() and out.stat().st_size > 0
