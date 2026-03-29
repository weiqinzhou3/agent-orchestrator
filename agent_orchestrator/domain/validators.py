from __future__ import annotations

from .enums import PhaseStatus, ProjectStatus
from .state_machine import ensure_phase_transition, ensure_project_transition


def validate_project_status_transition(current: ProjectStatus, target: ProjectStatus) -> None:
    ensure_project_transition(current, target)


def validate_phase_status_transition(current: PhaseStatus, target: PhaseStatus) -> None:
    ensure_phase_transition(current, target)
