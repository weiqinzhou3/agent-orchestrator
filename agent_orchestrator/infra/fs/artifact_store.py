from __future__ import annotations

import json
from pathlib import Path


class ArtifactStore:
    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def read_json(self, path: str) -> dict:
        return json.loads(self.read_text(path))

    def exists(self, path: str) -> bool:
        return Path(path).exists()


class InMemoryArtifactStore(ArtifactStore):
    def __init__(self):
        self._artifacts: dict[str, str] = {}

    def seed_text(self, path: str, content: str) -> None:
        self._artifacts[path] = content

    def seed_json(self, path: str, payload: dict) -> None:
        self._artifacts[path] = json.dumps(payload)

    def read_text(self, path: str) -> str:
        return self._artifacts[path]

    def read_json(self, path: str) -> dict:
        return json.loads(self.read_text(path))

    def exists(self, path: str) -> bool:
        return path in self._artifacts
