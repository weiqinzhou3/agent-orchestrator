from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    def write_text(self, path: str, content: str) -> str:
        resolved = self.resolve_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return path

    def write_json(self, path: str, payload: Any) -> str:
        return self.write_text(path, json.dumps(payload))

    def read_text(self, path: str) -> str:
        return self.resolve_path(path).read_text(encoding="utf-8")

    def read_json(self, path: str) -> Any:
        return json.loads(self.read_text(path))

    def exists(self, path: str) -> bool:
        return self.resolve_path(path).exists()

    def resolve_path(self, path: str) -> Path:
        return Path(path)


class FileArtifactStore(ArtifactStore):
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def resolve_path(self, path: str) -> Path:
        return self.base_dir / path.lstrip("/")


class InMemoryArtifactStore(ArtifactStore):
    def __init__(self):
        self._artifacts: dict[str, str] = {}

    def seed_text(self, path: str, content: str) -> None:
        self._artifacts[path] = content

    def seed_json(self, path: str, payload: dict) -> None:
        self._artifacts[path] = json.dumps(payload)

    def write_text(self, path: str, content: str) -> str:
        self._artifacts[path] = content
        return path

    def write_json(self, path: str, payload: Any) -> str:
        self._artifacts[path] = json.dumps(payload)
        return path

    def read_text(self, path: str) -> str:
        return self._artifacts[path]

    def read_json(self, path: str) -> Any:
        return json.loads(self.read_text(path))

    def exists(self, path: str) -> bool:
        return path in self._artifacts

    def resolve_path(self, path: str) -> Path:
        return Path(path)
