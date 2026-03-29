from __future__ import annotations

from typing import Dict, Iterable, Set

from .enums import PhaseStatus, ProjectStatus
from .errors import InvalidPhaseTransitionError, InvalidProjectTransitionError


ALLOWED_PHASE_TRANSITIONS: Dict[PhaseStatus, Set[PhaseStatus]] = {
    PhaseStatus.NOT_STARTED: {PhaseStatus.CONTRACT_VALIDATED},
    PhaseStatus.CONTRACT_VALIDATED: {PhaseStatus.CONTRACT_APPROVED, PhaseStatus.BLOCKED_ON_HUMAN},
    PhaseStatus.CONTRACT_APPROVED: {PhaseStatus.BUILDING},
    PhaseStatus.BUILDING: {PhaseStatus.REVIEW_PENDING, PhaseStatus.BLOCKED_ON_WORKER_FAILURE},
    PhaseStatus.REVIEW_PENDING: {
        PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
        PhaseStatus.BLOCKED_ON_HUMAN,
        PhaseStatus.READY_TO_CLOSE,
        PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
        PhaseStatus.BLOCKED_ON_WORKER_FAILURE,
    },
    PhaseStatus.BLOCKED_ON_HUMAN: {
        PhaseStatus.CONTRACT_APPROVED,
        PhaseStatus.READY_TO_CLOSE,
        PhaseStatus.CONTRACT_VALIDATED,
        PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
    },
    PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS: {
        PhaseStatus.BLOCKER_FIXING,
        PhaseStatus.RECHECK_PENDING,
        PhaseStatus.BLOCKED_ON_WORKER_FAILURE,
        PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
    },
    PhaseStatus.BLOCKER_FIXING: {PhaseStatus.RECHECK_PENDING, PhaseStatus.BLOCKED_ON_WORKER_FAILURE},
    PhaseStatus.RECHECK_PENDING: {
        PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
        PhaseStatus.BLOCKED_ON_HUMAN,
        PhaseStatus.READY_TO_CLOSE,
        PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
        PhaseStatus.BLOCKED_ON_WORKER_FAILURE,
    },
    PhaseStatus.READY_TO_CLOSE: {PhaseStatus.DONE, PhaseStatus.BLOCKED_ON_WORKER_FAILURE},
    PhaseStatus.BLOCKED_ON_WORKER_FAILURE: {
        PhaseStatus.CONTRACT_APPROVED,
        PhaseStatus.REVIEW_PENDING,
        PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
        PhaseStatus.RECHECK_PENDING,
        PhaseStatus.READY_TO_CLOSE,
    },
    PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT: {
        PhaseStatus.REVIEW_PENDING,
        PhaseStatus.RECHECK_PENDING,
    },
}


ALLOWED_PROJECT_TRANSITIONS: Dict[ProjectStatus, Set[ProjectStatus]] = {
    ProjectStatus.INIT: {ProjectStatus.DESIGN_READY},
    ProjectStatus.DESIGN_READY: {ProjectStatus.BOOTSTRAP_RUNNING},
    ProjectStatus.BOOTSTRAP_RUNNING: {
        ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
        ProjectStatus.BLOCKED_ON_WORKER_FAILURE,
    },
    ProjectStatus.BOOTSTRAP_REVIEW_PENDING: {
        ProjectStatus.BOOTSTRAP_READY,
        ProjectStatus.BLOCKED_ON_HUMAN,
        ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS,
        ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT,
        ProjectStatus.BLOCKED_ON_WORKER_FAILURE,
    },
    ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS: {
        ProjectStatus.BOOTSTRAP_RUNNING,
        ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
    },
    ProjectStatus.BLOCKED_ON_WORKER_FAILURE: {
        ProjectStatus.BOOTSTRAP_RUNNING,
        ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
    },
    ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT: {
        ProjectStatus.BOOTSTRAP_RUNNING,
        ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
    },
    ProjectStatus.BLOCKED_ON_HUMAN: {
        ProjectStatus.BOOTSTRAP_READY,
        ProjectStatus.RELEASE_READY,
        ProjectStatus.CLOSED,
    },
    ProjectStatus.BOOTSTRAP_READY: {ProjectStatus.PHASE_ACTIVE, ProjectStatus.RELEASE_READY},
    ProjectStatus.PHASE_ACTIVE: {ProjectStatus.PHASE_DONE},
    ProjectStatus.PHASE_DONE: {ProjectStatus.PHASE_ACTIVE, ProjectStatus.RELEASE_READY},
    ProjectStatus.RELEASE_READY: {ProjectStatus.BLOCKED_ON_HUMAN},
}


def _is_allowed(target, allowed: Iterable) -> bool:
    return target in set(allowed)


def ensure_project_transition(current: ProjectStatus, target: ProjectStatus) -> None:
    if not _is_allowed(target, ALLOWED_PROJECT_TRANSITIONS.get(current, set())):
        raise InvalidProjectTransitionError(f"invalid project transition: {current.value} -> {target.value}")


def ensure_phase_transition(current: PhaseStatus, target: PhaseStatus) -> None:
    if not _is_allowed(target, ALLOWED_PHASE_TRANSITIONS.get(current, set())):
        raise InvalidPhaseTransitionError(f"invalid phase transition: {current.value} -> {target.value}")
