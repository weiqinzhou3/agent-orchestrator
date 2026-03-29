from __future__ import annotations

from agent_orchestrator.application.contract_service import StubContractService
from agent_orchestrator.domain.enums import ApprovalType, JobStatus, PhaseResumeStage, PhaseStatus, ReviewOriginStage
from agent_orchestrator.domain.errors import (
    ContractInvalidError,
    InvalidPhaseTransitionError,
    MissingResumeContextError,
    PhaseAlreadyRunningError,
)
from agent_orchestrator.domain.recovery import (
    ALLOWED_PHASE_ENTRY,
    CLOSE_PATH_ACTIVE_STAGES,
    EXECUTING_PHASE_STATES,
    FAILED_BLOCKING_PHASE_STATES,
    phase_stage_from_status,
)
from agent_orchestrator.domain.results import PhaseRunResult


class PhaseService:
    def __init__(
        self,
        phase_repo,
        run_lock_repo,
        contract_service=None,
        approval_service=None,
        project_service=None,
        job_repo=None,
        scheduler=None,
        approval_repo=None,
    ):
        self.phase_repo = phase_repo
        self.run_lock_repo = run_lock_repo
        self.contract_service = contract_service or StubContractService()
        self.approval_service = approval_service
        self.project_service = project_service
        self.job_repo = job_repo
        self.scheduler = scheduler
        self.approval_repo = approval_repo

    def run_phase(self, project_name: str, phase_name: str) -> PhaseRunResult:
        with self.run_lock_repo.acquire_phase_lock(project_name, phase_name):
            phase = self.phase_repo.get(project_name, phase_name)
            if phase.status not in ALLOWED_PHASE_ENTRY:
                raise InvalidPhaseTransitionError(
                    f"phase {project_name}/{phase_name} is {phase.status.value}, phase run is not allowed"
                )

            executed: list[str] = []

            self._reconcile_inflight_phase_entry(project_name, phase_name)
            self._normalize_failed_phase_entry(project_name, phase_name)
            self._run_phase_waterfall(project_name, phase_name, executed)

            phase = self.phase_repo.get(project_name, phase_name)
            return PhaseRunResult(
                project_name=project_name,
                phase_name=phase_name,
                final_status=phase.status,
                executed_job_ids=executed,
                pending_approval_id=phase.latest_approval_id if phase.status == PhaseStatus.BLOCKED_ON_HUMAN else None,
                message="phase run completed",
            )

    def _reconcile_inflight_phase_entry(self, project_name: str, phase_name: str) -> None:
        phase = self.phase_repo.get(project_name, phase_name)

        if phase.status in EXECUTING_PHASE_STATES:
            failed_stage = phase_stage_from_status(phase.status)

            if phase.active_job_id is None:
                self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
                self.phase_repo.update_failure_context(
                    project_name,
                    phase_name,
                    failed_stage,
                    None,
                    None,
                    f"inflight {phase.status.value} without active job; treating as interrupted execution",
                )
                self.phase_repo.clear_active_execution(project_name, phase_name)
                return

            if self.job_repo is None or self.scheduler is None:
                raise MissingResumeContextError("job repository and scheduler are required for inflight phase reconciliation")

            job = self.job_repo.get(phase.active_job_id)
            if job.status == JobStatus.RUNNING and self.scheduler.is_job_lease_fresh(job.job_id):
                raise PhaseAlreadyRunningError(f"phase is already running for {project_name}/{phase_name}")

            if job.status == JobStatus.RUNNING:
                self.job_repo.mark_stale_failed(job.job_id, "stale inflight phase job detected during resume")

            blocked_status = (
                PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT
                if failed_stage in {PhaseResumeStage.REVIEW, PhaseResumeStage.RECHECK} and not bool(job.result_path)
                else PhaseStatus.BLOCKED_ON_WORKER_FAILURE
            )
            self.phase_repo.update_status(project_name, phase_name, blocked_status)
            self.phase_repo.update_failure_context(
                project_name,
                phase_name,
                failed_stage,
                job.job_id,
                job.result_path,
                f"inflight {phase.status.value} interrupted or stale; last job status={job.status.value}",
            )
            self.phase_repo.clear_active_execution(project_name, phase_name)
            return

        if phase.status == PhaseStatus.READY_TO_CLOSE and phase.active_stage in CLOSE_PATH_ACTIVE_STAGES:
            self._reconcile_ready_to_close_active_entry(project_name, phase_name)

    def _reconcile_ready_to_close_active_entry(self, project_name: str, phase_name: str) -> None:
        phase = self.phase_repo.get(project_name, phase_name)
        if phase.active_stage not in CLOSE_PATH_ACTIVE_STAGES:
            return

        if phase.active_job_id is None:
            self.phase_repo.clear_active_execution(project_name, phase_name)
            return

        if self.job_repo is None or self.scheduler is None:
            raise MissingResumeContextError("job repository and scheduler are required for close-path reconciliation")

        job = self.job_repo.get(phase.active_job_id)
        if job.status == JobStatus.RUNNING and self.scheduler.is_job_lease_fresh(job.job_id):
            raise PhaseAlreadyRunningError(f"phase is already running for {project_name}/{phase_name}")

        if job.status == JobStatus.RUNNING:
            self.job_repo.mark_stale_failed(job.job_id, "stale close-path job detected during resume")
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
            self.phase_repo.update_failure_context(
                project_name,
                phase_name,
                phase.active_stage,
                job.job_id,
                job.result_path,
                f"close-path active stage {phase.active_stage.value} interrupted or stale",
            )
            self.phase_repo.clear_active_execution(project_name, phase_name)
            return

        self.phase_repo.clear_active_execution(project_name, phase_name)

    def _normalize_failed_phase_entry(self, project_name: str, phase_name: str) -> None:
        phase = self.phase_repo.get(project_name, phase_name)
        if phase.status not in FAILED_BLOCKING_PHASE_STATES:
            return

        if phase.last_failed_stage is None:
            raise MissingResumeContextError("missing phase failure context")

        if phase.last_failed_stage == PhaseResumeStage.BUILD:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.CONTRACT_APPROVED)
            return

        if phase.last_failed_stage == PhaseResumeStage.REVIEW:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.REVIEW_PENDING)
            return

        if phase.last_failed_stage == PhaseResumeStage.FIX_BLOCKERS:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS)
            return

        if phase.last_failed_stage == PhaseResumeStage.RECHECK:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.RECHECK_PENDING)
            return

        if phase.last_failed_stage in {PhaseResumeStage.APPEND_BACKLOG, PhaseResumeStage.CLOSE_PHASE}:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.READY_TO_CLOSE)
            return

        raise MissingResumeContextError("unsupported phase failure stage")

    def _run_phase_waterfall(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        phase = self.phase_repo.get(project_name, phase_name)

        if phase.status in {PhaseStatus.NOT_STARTED, PhaseStatus.CONTRACT_VALIDATED}:
            self._enter_contract_path(project_name, phase_name, executed)
            phase = self.phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.CONTRACT_APPROVED:
            self._run_build_review_path(project_name, phase_name, executed)
            phase = self.phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.REVIEW_PENDING:
            self._run_review_only_path(project_name, phase_name, executed)
            phase = self.phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS:
            self._run_fix_recheck_path(project_name, phase_name, executed)
            phase = self.phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.RECHECK_PENDING:
            self._run_recheck_only_path(project_name, phase_name, executed)
            phase = self.phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.READY_TO_CLOSE:
            self._run_close_path(project_name, phase_name, executed)

    def _enter_contract_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        contract_result = self.contract_service.validate(project_name, phase_name)
        if not contract_result.valid:
            raise ContractInvalidError(contract_result.reason or "contract validation failed")

        self.phase_repo.update_status(project_name, phase_name, PhaseStatus.CONTRACT_VALIDATED)

        approval_type = self.contract_service.resolve_approval_type(
            project_name,
            phase_name,
            contract_result.contract_path or "",
        )
        if approval_type is None:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.CONTRACT_APPROVED)
            return

        if self.approval_service is None:
            raise RuntimeError("approval_service is required for contract approvals")
        self.approval_service.create_contract_approval(
            project_name,
            phase_name,
            approval_type,
            related_files=[contract_result.contract_path] if contract_result.contract_path else None,
        )

    def _run_build_review_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        return None

    def _run_review_only_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        return None

    def _run_fix_recheck_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        return None

    def _run_recheck_only_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        return None

    def _run_close_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        phase = self.phase_repo.get(project_name, phase_name)
        dedupe_scope = f"{project_name}:{phase_name}:{phase.latest_gate_snapshot_id or 'pending'}"
        close_marker = f"{project_name}:{phase_name}"
        self._append_backlog_step(project_name, phase_name, executed, dedupe_scope=dedupe_scope)
        self._close_phase_step(project_name, phase_name, executed, close_marker=close_marker)

    def _append_backlog_step(self, project_name: str, phase_name: str, executed: list[str], *, dedupe_scope: str) -> None:
        return None

    def _close_phase_step(self, project_name: str, phase_name: str, executed: list[str], *, close_marker: str) -> None:
        return None
