from __future__ import annotations

import pytest

from agent_orchestrator.domain.enums import PhaseStatus, ProjectStatus
from agent_orchestrator.domain.errors import InvalidPhaseTransitionError, InvalidProjectTransitionError
from agent_orchestrator.domain.state_machine import ALLOWED_PHASE_TRANSITIONS, ALLOWED_PROJECT_TRANSITIONS
from agent_orchestrator.infra.db.repositories import InMemoryPhaseRepository, InMemoryProjectRepository


PROJECT_ALLOWED_CASES = [
    (current_status, target_status)
    for current_status, allowed_targets in ALLOWED_PROJECT_TRANSITIONS.items()
    for target_status in allowed_targets
]

PROJECT_DISALLOWED_CASES = [
    (current_status, target_status)
    for current_status in ProjectStatus
    for target_status in ProjectStatus
    if target_status not in ALLOWED_PROJECT_TRANSITIONS.get(current_status, set())
]

PHASE_ALLOWED_CASES = [
    (current_status, target_status)
    for current_status, allowed_targets in ALLOWED_PHASE_TRANSITIONS.items()
    for target_status in allowed_targets
]

PHASE_DISALLOWED_CASES = [
    (current_status, target_status)
    for current_status in PhaseStatus
    for target_status in PhaseStatus
    if target_status not in ALLOWED_PHASE_TRANSITIONS.get(current_status, set())
]


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


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    PROJECT_ALLOWED_CASES,
    ids=lambda case: f"{case.value}" if hasattr(case, "value") else str(case),
)
def test_project_repository_accepts_all_allowed_transitions(make_project, current_status, target_status) -> None:
    repository = InMemoryProjectRepository({"demo-project": make_project(current_status)})

    repository.update_status("demo-project", target_status)

    assert repository.get("demo-project").status == target_status


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    PROJECT_DISALLOWED_CASES,
    ids=lambda case: f"{case.value}" if hasattr(case, "value") else str(case),
)
def test_project_repository_rejects_all_disallowed_transitions(make_project, current_status, target_status) -> None:
    repository = InMemoryProjectRepository({"demo-project": make_project(current_status)})

    with pytest.raises(InvalidProjectTransitionError):
        repository.update_status("demo-project", target_status)


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    PHASE_ALLOWED_CASES,
    ids=lambda case: f"{case.value}" if hasattr(case, "value") else str(case),
)
def test_phase_repository_accepts_all_allowed_transitions(make_phase, current_status, target_status) -> None:
    repository = InMemoryPhaseRepository({("demo-project", "phase-01"): make_phase(current_status)})

    repository.update_status("demo-project", "phase-01", target_status)

    assert repository.get("demo-project", "phase-01").status == target_status


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    PHASE_DISALLOWED_CASES,
    ids=lambda case: f"{case.value}" if hasattr(case, "value") else str(case),
)
def test_phase_repository_rejects_all_disallowed_transitions(make_phase, current_status, target_status) -> None:
    repository = InMemoryPhaseRepository({("demo-project", "phase-01"): make_phase(current_status)})

    with pytest.raises(InvalidPhaseTransitionError):
        repository.update_status("demo-project", "phase-01", target_status)
