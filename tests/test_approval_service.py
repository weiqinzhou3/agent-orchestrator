from __future__ import annotations

from contextlib import contextmanager

from agent_orchestrator.application.approval_service import ApprovalService
from agent_orchestrator.application.phase_service import PhaseService
from agent_orchestrator.application.project_service import ProjectService
from agent_orchestrator.domain.enums import ApprovalType, PhaseStatus, ProjectStatus, ReviewOriginStage
from agent_orchestrator.infra.db.repositories import (
    InMemoryApprovalRepository,
    InMemoryProjectPlanRepository,
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


class NoopRunLockRepository:
    @contextmanager
    def acquire_project_lock(self, project_name):
        yield

    @contextmanager
    def acquire_phase_lock(self, project_name, phase_name):
        yield


class ApprovalContractService:
    def validate(self, project_name, phase_name):
        class Result:
            valid = True
            contract_path = f"/tmp/contracts/{project_name}/{phase_name}.md"
            reason = None

        return Result()

    def resolve_approval_type(self, project_name, phase_name, contract_path):
        return ApprovalType.CONTRACT_APPROVAL


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


def test_create_contract_approval_blocks_phase_once(make_phase, make_project) -> None:
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.PHASE_ACTIVE, current_phase="phase-01")})
    phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.CONTRACT_VALIDATED)})
    approval_repo = InMemoryApprovalRepository()
    service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)

    approval = service.create_contract_approval(
        "demo-project",
        "phase-01",
        ApprovalType.CONTRACT_APPROVAL,
        related_files=["/tmp/contracts/phase-01.md"],
        origin_stage=None,
    )

    phase = phase_repo.get("demo-project", "phase-01")
    assert approval.approval_type == ApprovalType.CONTRACT_APPROVAL
    assert phase.latest_approval_id == approval.approval_id
    assert phase.status == PhaseStatus.BLOCKED_ON_HUMAN
    assert phase_repo.status_updates == [("demo-project", "phase-01", PhaseStatus.BLOCKED_ON_HUMAN)]
    assert project_repo.status_updates == []


def test_create_release_ready_confirm_blocks_project_once(make_project) -> None:
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.RELEASE_READY)})
    phase_repo = RecordingPhaseRepository({})
    approval_repo = InMemoryApprovalRepository()
    service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)

    approval = service.create_release_ready_confirm(
        "demo-project",
        related_files=["/tmp/release-summary.md"],
    )

    project = project_repo.get("demo-project")
    assert approval.approval_type == ApprovalType.RELEASE_READY_CONFIRM
    assert project.status == ProjectStatus.BLOCKED_ON_HUMAN
    assert project_repo.status_updates == [("demo-project", ProjectStatus.BLOCKED_ON_HUMAN)]


def test_phase_service_contract_path_does_not_duplicate_blocked_on_human_transition(
    make_phase,
    make_project,
) -> None:
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.PHASE_ACTIVE, current_phase="phase-01")})
    phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.NOT_STARTED)})
    approval_repo = InMemoryApprovalRepository()
    approval_service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    service = PhaseService(
        phase_repo=phase_repo,
        run_lock_repo=NoopRunLockRepository(),
        contract_service=ApprovalContractService(),
        approval_service=approval_service,
    )

    service.run_phase("demo-project", "phase-01")

    assert phase_repo.status_updates == [
        ("demo-project", "phase-01", PhaseStatus.CONTRACT_VALIDATED),
        ("demo-project", "phase-01", PhaseStatus.BLOCKED_ON_HUMAN),
    ]


def test_project_request_close_does_not_duplicate_blocked_on_human_transition(make_project) -> None:
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.RELEASE_READY)})
    phase_repo = RecordingPhaseRepository({})
    approval_repo = InMemoryApprovalRepository()
    approval_service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    service = ProjectService(
        project_repo=project_repo,
        project_plan_repo=InMemoryProjectPlanRepository({"demo-project": []}),
        approval_service=approval_service,
    )

    service.request_close("demo-project")

    assert project_repo.status_updates == [("demo-project", ProjectStatus.BLOCKED_ON_HUMAN)]
