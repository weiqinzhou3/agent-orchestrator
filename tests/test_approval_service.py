from __future__ import annotations

from agent_orchestrator.application.approval_service import ApprovalService
from agent_orchestrator.domain.enums import ApprovalType, PhaseStatus, ProjectStatus, ReviewOriginStage
from agent_orchestrator.infra.db.repositories import (
    InMemoryApprovalRepository,
    InMemoryPhaseRepository,
    InMemoryProjectRepository,
)


class RecordingPhaseRepository(InMemoryPhaseRepository):
    def __init__(self, phases):
        super().__init__(phases)
        self.status_updates = []

    def update_status(self, project_name, phase_name, status):
        self.status_updates.append((project_name, phase_name, status))
        super().update_status(project_name, phase_name, status)


class RecordingProjectRepository(InMemoryProjectRepository):
    def __init__(self, projects):
        super().__init__(projects)
        self.status_updates = []

    def update_status(self, project_name, status):
        self.status_updates.append((project_name, status))
        super().update_status(project_name, status)


def test_create_close_phase_with_important_open_is_single_blocking_responsibility(
    make_phase,
    make_project,
) -> None:
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.PHASE_ACTIVE, current_phase="phase-01")})
    phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.REVIEW_PENDING)})
    approval_repo = InMemoryApprovalRepository()
    service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)

    approval = service.create_close_phase_with_important_open(
        "demo-project",
        "phase-01",
        origin_stage=ReviewOriginStage.PHASE_REVIEW,
        related_files=["/tmp/review.json"],
    )

    phase = phase_repo.get("demo-project", "phase-01")
    assert phase.latest_approval_id == approval.approval_id
    assert phase.status == PhaseStatus.BLOCKED_ON_HUMAN
    assert phase_repo.status_updates == [("demo-project", "phase-01", PhaseStatus.BLOCKED_ON_HUMAN)]
    assert project_repo.status_updates == []


def test_create_bootstrap_ready_with_important_open_blocks_project_once(make_project) -> None:
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.BOOTSTRAP_REVIEW_PENDING)})
    phase_repo = RecordingPhaseRepository({})
    approval_repo = InMemoryApprovalRepository()
    service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)

    approval = service.create_bootstrap_ready_with_important_open(
        "demo-project",
        origin_stage=ReviewOriginStage.BOOTSTRAP_REVIEW,
        related_files=["/tmp/bootstrap-review.json"],
    )

    project = project_repo.get("demo-project")
    assert approval.approval_type == ApprovalType.BOOTSTRAP_READY_WITH_IMPORTANT_OPEN
    assert project.status == ProjectStatus.BLOCKED_ON_HUMAN
    assert project_repo.status_updates == [("demo-project", ProjectStatus.BLOCKED_ON_HUMAN)]
