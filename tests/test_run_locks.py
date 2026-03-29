from __future__ import annotations

import threading

import pytest

from agent_orchestrator.application.bootstrap_service import BootstrapService
from agent_orchestrator.application.phase_service import PhaseService
from agent_orchestrator.domain.errors import AlreadyRunningError
from agent_orchestrator.domain.enums import PhaseStatus, ProjectStatus
from agent_orchestrator.infra.db.repositories import InMemoryPhaseRepository, InMemoryProjectRepository
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


class BlockingBootstrapService(BootstrapService):
    def __init__(self, *args, entered_event, release_event, **kwargs):
        super().__init__(*args, **kwargs)
        self.entered_event = entered_event
        self.release_event = release_event

    def _run_bootstrap_waterfall(self, project_name, executed):
        self.entered_event.set()
        self.release_event.wait(timeout=2)


class BlockingPhaseService(PhaseService):
    def __init__(self, *args, entered_event, release_event, **kwargs):
        super().__init__(*args, **kwargs)
        self.entered_event = entered_event
        self.release_event = release_event

    def _run_phase_waterfall(self, project_name, phase_name, executed):
        self.entered_event.set()
        self.release_event.wait(timeout=2)


def test_bootstrap_run_rejects_parallel_entry_for_same_project(tmp_path, make_project) -> None:
    lock_repo = FileRunLockRepository(tmp_path)
    service = BlockingBootstrapService(
        project_repo=InMemoryProjectRepository({"demo-project": make_project(ProjectStatus.DESIGN_READY)}),
        run_lock_repo=lock_repo,
        entered_event=threading.Event(),
        release_event=threading.Event(),
    )

    worker = threading.Thread(target=service.run_bootstrap, args=("demo-project",), daemon=True)
    worker.start()
    assert service.entered_event.wait(timeout=1)

    with pytest.raises(AlreadyRunningError):
        service.run_bootstrap("demo-project")

    service.release_event.set()
    worker.join(timeout=1)


def test_phase_run_rejects_parallel_entry_for_same_scope(tmp_path, make_phase) -> None:
    lock_repo = FileRunLockRepository(tmp_path)
    service = BlockingPhaseService(
        phase_repo=InMemoryPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.NOT_STARTED)}),
        run_lock_repo=lock_repo,
        entered_event=threading.Event(),
        release_event=threading.Event(),
    )

    worker = threading.Thread(target=service.run_phase, args=("demo-project", "phase-01"), daemon=True)
    worker.start()
    assert service.entered_event.wait(timeout=1)

    with pytest.raises(AlreadyRunningError):
        service.run_phase("demo-project", "phase-01")

    service.release_event.set()
    worker.join(timeout=1)
