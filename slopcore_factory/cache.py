"""Hash-keyed stage cache.

Every stage writes a marker JSON keyed by a hash of its inputs. Re-running the
pipeline only redoes stages whose inputs changed, which is what keeps iteration
cheap when only the tail of the song is being tuned.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def hash_parts(*parts: object, **kwargs: object) -> str:
    """Stable sha256 over arbitrary JSON-serialisable parts.

    Positional parts and keyword parts are hashed in a fixed order, so both
    ``hash_parts(a, b)`` and ``hash_parts(song=a, take=b)`` are accepted.
    """
    payload: list[object] = list(parts)
    if kwargs:
        payload.append(kwargs)
    digest = hashlib.sha256()
    for part in payload:
        digest.update(json.dumps(part, sort_keys=True, default=str).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:16]


def hash_files(*paths: Path) -> str:
    """Hash file metadata + size (fast; content hash would be needlessly slow)."""
    items = []
    for path in paths:
        if path is None:
            continue
        p = Path(path)
        if p.exists():
            items.append([str(p), p.stat().st_size, int(p.stat().st_mtime)])
        else:
            items.append([str(p), None, None])
    return hash_parts(items)


class StageCache:
    """Marker store rooted at ``<workdir>/cache``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _marker(self, stage: str) -> Path:
        return self.root / f"{stage}.json"

    def is_fresh(self, stage: str, key: str) -> bool:
        marker = self._marker(stage)
        if not marker.exists():
            return False
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return data.get("key") == key

    def mark(self, stage: str, key: str, outputs: list[Path] | None = None) -> None:
        marker = self._marker(stage)
        payload = {
            "key": key,
            "outputs": [str(p) for p in (outputs or [])],
        }
        marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")
