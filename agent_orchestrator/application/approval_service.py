from __future__ import annotations

from typing import Optional

from agent_orchestrator.domain.enums import ApprovalType, PhaseStatus, ProjectStatus, ReviewOriginStage
from agent_orchestrator.domain.errors import UnsupportedApprovalTypeError
from agent_orchestrator.domain.results import ApprovalOutcome


class ApprovalService:
    def __init__(self, project_repo, phase_repo, approval_repo):
        self.project_repo = project_repo
        self.phase_repo = phase_repo
        self.approval_repo = approval_repo

    def create_contract_approval(
        self,
        project_name: str,
        phase_name: str,
        approval_type: ApprovalType,
        related_files: Optional[list[str]] = None,
        origin_stage: Optional[ReviewOriginStage] = None,
    ):
        if approval_type not in {ApprovalType.CONTRACT_APPROVAL, ApprovalType.SCOPE_CHANGE}:
            raise UnsupportedApprovalTypeError(f"unsupported contract approval type: {approval_type.value}")
        approval = self.approval_repo.create(
            project_name=project_name,
            phase_name=phase_name,
            approval_type=approval_type,
            origin_stage=origin_stage,
            related_files=related_files,
        )
        self.phase_repo.attach_latest_approval(project_name, phase_name, approval.approval_id)
        self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_HUMAN)
        return approval

    def create_close_phase_with_important_open(
        self,
        project_name: str,
        phase_name: str,
        origin_stage: ReviewOriginStage,
        related_files: Optional[list[str]] = None,
    ):
        approval = self.approval_repo.create(
            project_name=project_name,
            phase_name=phase_name,
            approval_type=ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN,
            origin_stage=origin_stage,
            related_files=related_files,
        )
        self.phase_repo.attach_latest_approval(project_name, phase_name, approval.approval_id)
        self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_HUMAN)
        return approval

    def create_bootstrap_ready_with_important_open(
        self,
        project_name: str,
        origin_stage: ReviewOriginStage = ReviewOriginStage.BOOTSTRAP_REVIEW,
        related_files: Optional[list[str]] = None,
    ):
        approval = self.approval_repo.create(
            project_name=project_name,
            phase_name=None,
            approval_type=ApprovalType.BOOTSTRAP_READY_WITH_IMPORTANT_OPEN,
            origin_stage=origin_stage,
            related_files=related_files,
        )
        self.project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_HUMAN)
        return approval

    def create_release_ready_confirm(
        self,
        project_name: str,
        related_files: Optional[list[str]] = None,
    ):
        approval = self.approval_repo.create(
            project_name=project_name,
            phase_name=None,
            approval_type=ApprovalType.RELEASE_READY_CONFIRM,
            origin_stage=None,
            related_files=related_files,
        )
        self.project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_HUMAN)
        return approval

    def approve(self, approval_id: str, actor: str) -> ApprovalOutcome:
        approval = self.approval_repo.get(approval_id)
        self.approval_repo.mark_approved(approval_id, actor)

        if approval.approval_type in {ApprovalType.CONTRACT_APPROVAL, ApprovalType.SCOPE_CHANGE}:
            self.phase_repo.update_status(approval.project_name, approval.phase_name, PhaseStatus.CONTRACT_APPROVED)
            return ApprovalOutcome(
                approval_id,
                approval.approval_type,
                None,
                PhaseStatus.CONTRACT_APPROVED,
                f"agent-orchestrator phase run --project {approval.project_name} --phase {approval.phase_name}",
            )

        if approval.approval_type == ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN:
            self.phase_repo.update_status(approval.project_name, approval.phase_name, PhaseStatus.READY_TO_CLOSE)
            return ApprovalOutcome(
                approval_id,
                approval.approval_type,
                None,
                PhaseStatus.READY_TO_CLOSE,
                f"agent-orchestrator phase run --project {approval.project_name} --phase {approval.phase_name}",
            )

        if approval.approval_type == ApprovalType.BOOTSTRAP_READY_WITH_IMPORTANT_OPEN:
            self.project_repo.update_status(approval.project_name, ProjectStatus.BOOTSTRAP_READY)
            return ApprovalOutcome(
                approval_id,
                approval.approval_type,
                ProjectStatus.BOOTSTRAP_READY,
                None,
                f"agent-orchestrator project advance --project {approval.project_name}",
            )

        if approval.approval_type == ApprovalType.RELEASE_READY_CONFIRM:
            self.project_repo.update_status(approval.project_name, ProjectStatus.CLOSED)
            return ApprovalOutcome(approval_id, approval.approval_type, ProjectStatus.CLOSED, None, None)

        raise UnsupportedApprovalTypeError(f"unsupported approval type: {approval.approval_type.value}")

    def reject(self, approval_id: str, actor: str) -> ApprovalOutcome:
        approval = self.approval_repo.get(approval_id)
        self.approval_repo.mark_rejected(approval_id, actor)

        if approval.approval_type in {ApprovalType.CONTRACT_APPROVAL, ApprovalType.SCOPE_CHANGE}:
            self.phase_repo.update_status(approval.project_name, approval.phase_name, PhaseStatus.CONTRACT_VALIDATED)
            return ApprovalOutcome(
                approval_id,
                approval.approval_type,
                None,
                PhaseStatus.CONTRACT_VALIDATED,
                f"agent-orchestrator phase run --project {approval.project_name} --phase {approval.phase_name}",
            )

        if approval.approval_type == ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN:
            self.phase_repo.update_status(approval.project_name, approval.phase_name, PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS)
            return ApprovalOutcome(
                approval_id,
                approval.approval_type,
                None,
                PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
                f"agent-orchestrator phase run --project {approval.project_name} --phase {approval.phase_name}",
            )

        if approval.approval_type == ApprovalType.BOOTSTRAP_READY_WITH_IMPORTANT_OPEN:
            self.project_repo.update_status(approval.project_name, ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS)
            return ApprovalOutcome(
                approval_id,
                approval.approval_type,
                ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS,
                None,
                f"agent-orchestrator bootstrap run --project {approval.project_name}",
            )

        if approval.approval_type == ApprovalType.RELEASE_READY_CONFIRM:
            self.project_repo.update_status(approval.project_name, ProjectStatus.RELEASE_READY)
            return ApprovalOutcome(
                approval_id,
                approval.approval_type,
                ProjectStatus.RELEASE_READY,
                None,
                f"agent-orchestrator project request-close --project {approval.project_name}",
            )

        raise UnsupportedApprovalTypeError(f"unsupported approval type: {approval.approval_type.value}")
