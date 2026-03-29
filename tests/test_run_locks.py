from __future__ import annotations

import pytest

from agent_orchestrator.domain.errors import AlreadyRunningError
from agent_orchestrator.infra.fs.run_locks import FileRunLockRepository


def test_project_lock_rejects_second_holder_for_same_project(tmp_path) -> None:
    repository = FileRunLockRepository(tmp_path)

    with repository.acquire_project_lock("demo-project"):
        with pytest.raises(AlreadyRunningError):
            with repository.acquire_project_lock("demo-project"):
                pass


def test_phase_lock_is_scoped_by_project_and_phase(tmp_path) -> None:
    repository = FileRunLockRepository(tmp_path)

    with repository.acquire_phase_lock("demo-project", "phase-01"):
        with pytest.raises(AlreadyRunningError):
            with repository.acquire_phase_lock("demo-project", "phase-01"):
                pass

        with repository.acquire_phase_lock("demo-project", "phase-02"):
            pass
