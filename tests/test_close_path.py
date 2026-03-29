from __future__ import annotations

from contextlib import contextmanager

from agent_orchestrator.application.phase_service import PhaseService
from agent_orchestrator.domain.enums import PhaseResumeStage, PhaseStatus
from agent_orchestrator.infra.db.repositories import InMemoryPhaseRepository


class RecordingPhaseRepository(InMemoryPhaseRepository):
    def __init__(self, phases):
        super().__init__(phases)
        self.active_execution_events = []
        self.status_updates = []

    def set_active_execution(self, project_name, phase_name, stage, job_id, started_at):
        self.active_execution_events.append(("set", project_name, phase_name, stage, job_id))
        super().set_active_execution(project_name, phase_name, stage, job_id, started_at)

    def clear_active_execution(self, project_name, phase_name):
        self.active_execution_events.append(("clear", project_name, phase_name))
        super().clear_active_execution(project_name, phase_name)

    def update_status(self, project_name, phase_name, status):
        self.status_updates.append((project_name, phase_name, status))
        super().update_status(project_name, phase_name, status)


class NoopRunLockRepository:
    @contextmanager
    def acquire_project_lock(self, project_name):
        yield

    @contextmanager
    def acquire_phase_lock(self, project_name, phase_name):
        yield


def test_append_backlog_step_sets_and_clears_active_execution(make_phase) -> None:
    phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.READY_TO_CLOSE)})
    service = PhaseService(phase_repo=phase_repo, run_lock_repo=NoopRunLockRepository())

    executed = []
    service._append_backlog_step("demo-project", "phase-01", executed, dedupe_scope="demo-project:phase-01:snapshot-1")

    phase = phase_repo.get("demo-project", "phase-01")
    assert executed == ["append-backlog:demo-project:phase-01"]
    assert phase.active_stage is None
    assert phase.active_job_id is None
    assert phase_repo.active_execution_events == [
        ("set", "demo-project", "phase-01", PhaseResumeStage.APPEND_BACKLOG, "append-backlog:demo-project:phase-01"),
        ("clear", "demo-project", "phase-01"),
    ]


def test_close_phase_step_sets_and_clears_active_execution_and_marks_done(make_phase) -> None:
    phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.READY_TO_CLOSE)})
    service = PhaseService(phase_repo=phase_repo, run_lock_repo=NoopRunLockRepository())

    executed = []
    service._close_phase_step("demo-project", "phase-01", executed, close_marker="demo-project:phase-01")

    phase = phase_repo.get("demo-project", "phase-01")
    assert executed == ["close-phase:demo-project:phase-01"]
    assert phase.status == PhaseStatus.DONE
    assert phase.active_stage is None
    assert phase.active_job_id is None
    assert phase_repo.active_execution_events == [
        ("set", "demo-project", "phase-01", PhaseResumeStage.CLOSE_PHASE, "close-phase:demo-project:phase-01"),
        ("clear", "demo-project", "phase-01"),
    ]
    assert phase_repo.status_updates == [("demo-project", "phase-01", PhaseStatus.DONE)]
