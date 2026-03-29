from __future__ import annotations

from typing import Optional

from agent_orchestrator.domain.enums import ProjectStatus
from agent_orchestrator.domain.errors import InvalidProjectTransitionError


class ProjectService:
    def __init__(self, project_repo, project_plan_repo, approval_service=None):
        self.project_repo = project_repo
        self.project_plan_repo = project_plan_repo
        self.approval_service = approval_service

    def on_phase_done(self, project_name: str, phase_name: str) -> None:
        project = self.project_repo.get(project_name)
        if project.status != ProjectStatus.PHASE_ACTIVE:
            raise InvalidProjectTransitionError(
                f"project {project_name} is {project.status.value}, expected PHASE_ACTIVE before on_phase_done"
            )
        self.project_repo.update_status(project_name, ProjectStatus.PHASE_DONE)

    def advance(self, project_name: str) -> None:
        phases = self.project_plan_repo.list_ordered_phases(project_name)
        project = self.project_repo.get(project_name)

        if project.status == ProjectStatus.BOOTSTRAP_READY:
            first_phase = phases[0] if phases else None
            if first_phase is None:
                self.project_repo.update_status(project_name, ProjectStatus.RELEASE_READY)
                self.project_repo.set_current_phase(project_name, None)
                return

            self.project_repo.set_current_phase(project_name, first_phase)
            self.project_repo.update_status(project_name, ProjectStatus.PHASE_ACTIVE)
            return

        if project.status != ProjectStatus.PHASE_DONE:
            raise InvalidProjectTransitionError(
                f"project {project_name} is {project.status.value}, expected BOOTSTRAP_READY or PHASE_DONE"
            )

        next_phase = _find_next_phase_after(project.current_phase, phases)
        if next_phase is None:
            self.project_repo.update_status(project_name, ProjectStatus.RELEASE_READY)
            self.project_repo.set_current_phase(project_name, None)
            return

        self.project_repo.set_current_phase(project_name, next_phase)
        self.project_repo.update_status(project_name, ProjectStatus.PHASE_ACTIVE)

    def request_close(self, project_name: str) -> str:
        project = self.project_repo.get(project_name)
        if project.status != ProjectStatus.RELEASE_READY:
            raise InvalidProjectTransitionError(
                f"project {project_name} is {project.status.value}, expected RELEASE_READY"
            )
        if self.approval_service is None:
            raise RuntimeError("approval_service is required for request_close")
        approval = self.approval_service.create_release_ready_confirm(project_name)
        return approval.approval_id


def _find_next_phase_after(current_phase: Optional[str], phases: list[str]) -> Optional[str]:
    if not phases:
        return None
    if current_phase is None:
        return phases[0]
    try:
        current_index = phases.index(current_phase)
    except ValueError:
        return None
    next_index = current_index + 1
    if next_index >= len(phases):
        return None
    return phases[next_index]
