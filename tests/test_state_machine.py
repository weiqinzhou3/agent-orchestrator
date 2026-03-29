from __future__ import annotations

import pytest

from agent_orchestrator.domain.enums import PhaseStatus, ProjectStatus
from agent_orchestrator.domain.errors import InvalidPhaseTransitionError, InvalidProjectTransitionError
from agent_orchestrator.domain.state_machine import ALLOWED_PHASE_TRANSITIONS, ALLOWED_PROJECT_TRANSITIONS
from agent_orchestrator.infra.db.repositories import InMemoryPhaseRepository, InMemoryProjectRepository


def test_allowed_project_transitions_include_bootstrap_ready_to_release_ready() -> None:
    assert ProjectStatus.RELEASE_READY in ALLOWED_PROJECT_TRANSITIONS[ProjectStatus.BOOTSTRAP_READY]


def test_project_repository_update_status_rejects_illegal_transition(make_project) -> None:
    repository = InMemoryProjectRepository({"demo-project": make_project(ProjectStatus.DESIGN_READY)})

    with pytest.raises(InvalidProjectTransitionError):
        repository.update_status("demo-project", ProjectStatus.CLOSED)


def test_phase_repository_update_status_rejects_illegal_transition(make_phase) -> None:
    repository = InMemoryPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.NOT_STARTED)})

    with pytest.raises(InvalidPhaseTransitionError):
        repository.update_status("demo-project", "phase-01", PhaseStatus.DONE)
