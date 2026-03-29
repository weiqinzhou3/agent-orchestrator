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
