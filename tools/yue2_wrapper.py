#!/usr/bin/env python3
"""Adapter: run YuE2 for the slopcore-factory ``yue`` song backend.

YuE2 generation was confirmed working on CPU (it reached the audio-synthesis
stage) but is far too slow and large to keep locally, so the weights are not
vendored. This adapter is the code path: point the factory at it on a machine
where YuE2 is installed.

Contract (see ``slopcore_factory/localgen.py``):

    yue2_wrapper.py --request <factory-request.json> --out <audio.wav>

``--request`` is the factory's request (``title``, ``lyrics``, ``style``,
``duration``, ``seed``, ``out``). This adapter builds a YuE2 request, runs
``python -m yue2.cli generate``, finds the produced ``audio.flac`` and converts
it to ``--out``.

Setup on a capable machine (YuE2 targets Python 3.12; a GPU is strongly
recommended):

    git clone https://github.com/multimodal-art-projection/YuE
    cd YuE && python3.12 -m venv .venv && . .venv/bin/activate && pip install .
    export SLOPCORE_YUE_CMD="python /path/to/slopcore-factory/tools/yue2_wrapper.py"
    slopcore-factory song --lyrics songs/foo/lyrics.md --song-backend yue
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_STYLE = "English, noir trip-hop, slow, close breathy female vocal, sub bass, vinyl crackle"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--device", default="cpu", help="cpu | cuda (YuE2 recommends cuda)")
    parser.add_argument("--budget", type=float, default=8.0, help="memory budget in GiB")
    parser.add_argument("--cot", default="off", choices=("full", "melody", "off"))
    args = parser.parse_args()

    request = json.loads(args.request.read_text(encoding="utf-8"))
    yue_request = {
        "id": "song",
        "style": request.get("style") or DEFAULT_STYLE,
        "lyrics": request["lyrics"],
        "cot": args.cot,
        "seed": int(request.get("seed", 0)),
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_path = tmp_path / "request.json"
        request_path.write_text(json.dumps(yue_request), encoding="utf-8")
        out_dir = tmp_path / "out"

        subprocess.run(
            [
                sys.executable,
                "-m",
                "yue2.cli",
                "generate",
                "--request",
                str(request_path),
                "--output",
                str(out_dir),
                "--device",
                args.device,
                "--budget",
                str(args.budget),
            ],
            check=True,
        )

        flac = next(out_dir.rglob("audio.flac"), None)
        if flac is None:
            raise SystemExit("YuE2 produced no audio.flac")

        args.out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            try:
                subprocess.run(
                    [ffmpeg, "-y", "-loglevel", "error", "-i", str(flac), str(args.out)],
                    check=True,
                )
                return 0
            except subprocess.CalledProcessError:
                pass
        shutil.copy2(flac, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
