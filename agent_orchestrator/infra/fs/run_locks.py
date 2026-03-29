from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from agent_orchestrator.domain.errors import AlreadyRunningError


class FileRunLockRepository:
    def __init__(self, lock_root):
        self.lock_root = Path(lock_root)
        self.lock_root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def acquire_project_lock(self, project_name: str) -> Iterator[None]:
        with self._acquire_lock(f"project::{project_name}"):
            yield

    @contextmanager
    def acquire_phase_lock(self, project_name: str, phase_name: str) -> Iterator[None]:
        with self._acquire_lock(f"phase::{project_name}::{phase_name}"):
            yield

    @contextmanager
    def _acquire_lock(self, scope: str) -> Iterator[None]:
        lock_path = self.lock_root / f"{scope.replace(':', '__')}.lock"
        descriptor = None
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError as exc:
            raise AlreadyRunningError(f"scope already locked: {scope}") from exc

        try:
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
