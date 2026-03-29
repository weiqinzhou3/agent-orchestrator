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


def test_approve_contract_approval_returns_phase_to_contract_approved(make_phase, make_project) -> None:
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.PHASE_ACTIVE, current_phase="phase-01")})
    phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.CONTRACT_VALIDATED)})
    approval_repo = InMemoryApprovalRepository()
    service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    approval = service.create_contract_approval("demo-project", "phase-01", ApprovalType.CONTRACT_APPROVAL)

    outcome = service.approve(approval.approval_id, actor="owner")

    assert outcome.new_phase_status == PhaseStatus.CONTRACT_APPROVED
    assert phase_repo.get("demo-project", "phase-01").status == PhaseStatus.CONTRACT_APPROVED


def test_reject_contract_approval_returns_phase_to_contract_validated(make_phase, make_project) -> None:
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.PHASE_ACTIVE, current_phase="phase-01")})
    phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.CONTRACT_VALIDATED)})
    approval_repo = InMemoryApprovalRepository()
    service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    approval = service.create_contract_approval("demo-project", "phase-01", ApprovalType.CONTRACT_APPROVAL)

    outcome = service.reject(approval.approval_id, actor="owner")

    assert outcome.new_phase_status == PhaseStatus.CONTRACT_VALIDATED
    assert phase_repo.get("demo-project", "phase-01").status == PhaseStatus.CONTRACT_VALIDATED


def test_approve_and_reject_close_phase_with_important_open_routes_to_expected_phase_states(make_phase, make_project) -> None:
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.PHASE_ACTIVE, current_phase="phase-01")})
    approval_repo = InMemoryApprovalRepository()

    approve_phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(PhaseStatus.REVIEW_PENDING)})
    approve_service = ApprovalService(project_repo=project_repo, phase_repo=approve_phase_repo, approval_repo=approval_repo)
    approve_approval = approve_service.create_close_phase_with_important_open(
        "demo-project",
        "phase-01",
        origin_stage=ReviewOriginStage.PHASE_REVIEW,
    )
    approve_outcome = approve_service.approve(approve_approval.approval_id, actor="owner")

    reject_phase_repo = RecordingPhaseRepository({("demo-project", "phase-02"): make_phase(PhaseStatus.REVIEW_PENDING, phase_name="phase-02")})
    reject_service = ApprovalService(project_repo=project_repo, phase_repo=reject_phase_repo, approval_repo=approval_repo)
    reject_approval = reject_service.create_close_phase_with_important_open(
        "demo-project",
        "phase-02",
        origin_stage=ReviewOriginStage.PHASE_REVIEW,
    )
    reject_outcome = reject_service.reject(reject_approval.approval_id, actor="owner")

    assert approve_outcome.new_phase_status == PhaseStatus.READY_TO_CLOSE
    assert approve_phase_repo.get("demo-project", "phase-01").status == PhaseStatus.READY_TO_CLOSE
    assert reject_outcome.new_phase_status == PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS
    assert reject_phase_repo.get("demo-project", "phase-02").status == PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS


def test_bootstrap_ready_and_release_ready_approvals_route_project_on_approve_and_reject(make_project) -> None:
    bootstrap_project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.BOOTSTRAP_REVIEW_PENDING)})
    phase_repo = RecordingPhaseRepository({})
    approval_repo = InMemoryApprovalRepository()
    bootstrap_service = ApprovalService(project_repo=bootstrap_project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    bootstrap_approval = bootstrap_service.create_bootstrap_ready_with_important_open("demo-project")

    bootstrap_approve = bootstrap_service.approve(bootstrap_approval.approval_id, actor="owner")
    assert bootstrap_approve.new_project_status == ProjectStatus.BOOTSTRAP_READY
    assert bootstrap_project_repo.get("demo-project").status == ProjectStatus.BOOTSTRAP_READY

    reject_project_repo = RecordingProjectRepository({"demo-project-2": make_project(ProjectStatus.BOOTSTRAP_REVIEW_PENDING, project_name="demo-project-2")})
    reject_service = ApprovalService(project_repo=reject_project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    reject_bootstrap_approval = reject_service.create_bootstrap_ready_with_important_open("demo-project-2")
    bootstrap_reject = reject_service.reject(reject_bootstrap_approval.approval_id, actor="owner")
    assert bootstrap_reject.new_project_status == ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS
    assert reject_project_repo.get("demo-project-2").status == ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS

    release_project_repo = RecordingProjectRepository({"demo-project-3": make_project(ProjectStatus.RELEASE_READY, project_name="demo-project-3")})
    release_service = ApprovalService(project_repo=release_project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    release_approval = release_service.create_release_ready_confirm("demo-project-3")
    release_approve = release_service.approve(release_approval.approval_id, actor="owner")
    assert release_approve.new_project_status == ProjectStatus.CLOSED
    assert release_project_repo.get("demo-project-3").status == ProjectStatus.CLOSED

    release_reject_project_repo = RecordingProjectRepository({"demo-project-4": make_project(ProjectStatus.RELEASE_READY, project_name="demo-project-4")})
    release_reject_service = ApprovalService(project_repo=release_reject_project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    release_reject_approval = release_reject_service.create_release_ready_confirm("demo-project-4")
    release_reject = release_reject_service.reject(release_reject_approval.approval_id, actor="owner")
    assert release_reject.new_project_status == ProjectStatus.RELEASE_READY
    assert release_reject_project_repo.get("demo-project-4").status == ProjectStatus.RELEASE_READY
