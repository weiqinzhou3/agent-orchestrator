from __future__ import annotations

from contextlib import contextmanager

from agent_orchestrator.application.bootstrap_service import BootstrapService
from agent_orchestrator.application.phase_service import PhaseService
from agent_orchestrator.domain.enums import PhaseStatus, ProjectStatus
from agent_orchestrator.infra.db.repositories import (
    InMemoryPhaseRepository,
    InMemoryProjectRepository,
)


class RecordingRunLockRepository:
    def __init__(self, events):
        self.events = events

    @contextmanager
    def acquire_project_lock(self, project_name):
        self.events.append("acquire lock")
        yield

    @contextmanager
    def acquire_phase_lock(self, project_name, phase_name):
        self.events.append("acquire lock")
        yield


class RecordingBootstrapService(BootstrapService):
    def __init__(self, *args, events, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = events

    def _reconcile_inflight_bootstrap_entry(self, project_name):
        self.events.append("reconcile inflight")

    def _normalize_failed_bootstrap_entry(self, project_name, force_full):
        self.events.append("normalize failed entry")

    def _run_bootstrap_waterfall(self, project_name, executed):
        self.events.append("waterfall")


class RecordingPhaseService(PhaseService):
    def __init__(self, *args, events, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = events

    def _reconcile_inflight_phase_entry(self, project_name, phase_name):
        self.events.append("reconcile inflight")

    def _normalize_failed_phase_entry(self, project_name, phase_name):
        self.events.append("normalize failed entry")

    def _run_phase_waterfall(self, project_name, phase_name, executed):
        self.events.append("waterfall")


def test_run_bootstrap_uses_required_order(make_project) -> None:
    events = []
    service = RecordingBootstrapService(
        project_repo=InMemoryProjectRepository({"demo-project": make_project(ProjectStatus.DESIGN_READY)}),
        run_lock_repo=RecordingRunLockRepository(events),
        events=events,
    )

    service.run_bootstrap("demo-project")

    assert events == [
        "acquire lock",
        "reconcile inflight",
        "normalize failed entry",
        "waterfall",
    ]


def test_run_phase_uses_required_order(make_phase) -> None:
    events = []
    service = RecordingPhaseService(
        phase_repo=InMemoryPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.NOT_STARTED)}),
        run_lock_repo=RecordingRunLockRepository(events),
        events=events,
    )

    service.run_phase("demo-project", "phase-01")

    assert events == [
        "acquire lock",
        "reconcile inflight",
        "normalize failed entry",
        "waterfall",
    ]
