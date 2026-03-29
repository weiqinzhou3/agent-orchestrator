from __future__ import annotations

from dataclasses import replace

from agent_orchestrator.application.contract_service import StubContractService
from agent_orchestrator.domain.entities import Job, PhaseGateSnapshot, utc_now
from agent_orchestrator.domain.enums import (
    ApprovalStatus,
    ApprovalType,
    GateDecisionType,
    JobStatus,
    PhaseResumeStage,
    PhaseStatus,
    ReviewOriginStage,
)
from agent_orchestrator.domain.errors import (
    ContractInvalidError,
    InvalidPhaseTransitionError,
    InvalidRecheckSourceError,
    MissingGateDecisionError,
    MissingResumeContextError,
    PhaseAlreadyRunningError,
    UnsupportedOriginStageError,
)
from agent_orchestrator.domain.recovery import (
    ALLOWED_PHASE_ENTRY,
    CLOSE_PATH_ACTIVE_STAGES,
    EXECUTING_PHASE_STATES,
    FAILED_BLOCKING_PHASE_STATES,
    phase_stage_from_status,
)
from agent_orchestrator.domain.results import PhaseRunResult
from agent_orchestrator.domain.review_parser import parse_review_payload


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
        gate_snapshot_repo=None,
        artifact_store=None,
    ):
        self.phase_repo = phase_repo
        self.run_lock_repo = run_lock_repo
        self.contract_service = contract_service or StubContractService()
        self.approval_service = approval_service
        self.project_service = project_service
        self.job_repo = job_repo
        self.scheduler = scheduler
        self.approval_repo = approval_repo
        self.gate_snapshot_repo = gate_snapshot_repo
        self.artifact_store = artifact_store

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

        # Latch the resume entry so a run starting from blockers/recheck executes that recovery path once.
        blockers_entry = phase.status == PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS
        recheck_entry = phase.status == PhaseStatus.RECHECK_PENDING

        if phase.status == PhaseStatus.CONTRACT_APPROVED:
            self._run_build_review_path(project_name, phase_name, executed)
            phase = self.phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.REVIEW_PENDING:
            self._run_review_only_path(project_name, phase_name, executed)
            phase = self.phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS and blockers_entry:
            self._run_fix_recheck_path(project_name, phase_name, executed)
            phase = self.phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.RECHECK_PENDING and recheck_entry:
            self._run_recheck_only_path(project_name, phase_name, executed)
            phase = self.phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.READY_TO_CLOSE:
            self._run_close_path(project_name, phase_name, executed)

    def _enter_contract_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        _ = executed
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
        self._ensure_runtime_dependencies()

        build_job = self._new_phase_job(project_name, phase_name, "phase-build")
        self.scheduler.enqueue(build_job)

        self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BUILDING)
        self.phase_repo.set_active_execution(
            project_name,
            phase_name,
            PhaseResumeStage.BUILD,
            build_job.job_id,
            utc_now(),
        )
        try:
            build_exec = self.scheduler.execute_job(build_job.job_id)
        finally:
            self.phase_repo.clear_active_execution(project_name, phase_name)

        executed.append(build_job.job_id)

        if build_exec.completion.status != JobStatus.SUCCEEDED:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
            self.phase_repo.update_failure_context(
                project_name,
                phase_name,
                PhaseResumeStage.BUILD,
                build_job.job_id,
                build_exec.result_path,
                "build failed",
            )
            return

        self.phase_repo.clear_failure_context(project_name, phase_name)
        self.phase_repo.update_status(project_name, phase_name, PhaseStatus.REVIEW_PENDING)
        self._run_review_only_path(project_name, phase_name, executed)

    def _run_review_only_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        self._ensure_runtime_dependencies()

        review_job = self._new_phase_job(
            project_name,
            phase_name,
            "phase-review",
            review_origin_stage=ReviewOriginStage.PHASE_REVIEW,
        )
        self.scheduler.enqueue(review_job)
        self.phase_repo.set_active_execution(
            project_name,
            phase_name,
            PhaseResumeStage.REVIEW,
            review_job.job_id,
            utc_now(),
        )
        try:
            review_exec = self.scheduler.execute_job(review_job.job_id)
        finally:
            self.phase_repo.clear_active_execution(project_name, phase_name)

        executed.append(review_job.job_id)
        review_exec = self._attach_gate_decision(review_exec)
        if self._block_review_like_failure(
            project_name,
            phase_name,
            review_exec,
            ReviewOriginStage.PHASE_REVIEW,
            "review worker failed before producing a gate",
        ):
            return

        self._route_gate_after_review(project_name, phase_name, review_exec, ReviewOriginStage.PHASE_REVIEW)

    def _run_fix_recheck_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        self._ensure_runtime_dependencies(require_snapshot_repo=True, require_artifact_store=True)

        phase = self.phase_repo.get(project_name, phase_name)
        snapshot = self.gate_snapshot_repo.get_latest(project_name, phase_name)
        review_payload = self.artifact_store.read_json(snapshot.result_path)
        approval = self.approval_repo.get(phase.latest_approval_id) if phase.latest_approval_id else None
        rework_items = self._snapshot_blockers_or_important(snapshot, review_payload, approval)

        fix_job = self._new_phase_job(
            project_name,
            phase_name,
            "phase-fix-blockers",
            context_refs={
                "source_review_result_path": snapshot.result_path,
                "rework_count": str(len(rework_items)),
            },
        )
        self.scheduler.enqueue(fix_job)
        self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKER_FIXING)
        self.phase_repo.set_active_execution(
            project_name,
            phase_name,
            PhaseResumeStage.FIX_BLOCKERS,
            fix_job.job_id,
            utc_now(),
        )
        try:
            fix_exec = self.scheduler.execute_job(fix_job.job_id)
        finally:
            self.phase_repo.clear_active_execution(project_name, phase_name)

        executed.append(fix_job.job_id)

        if fix_exec.completion.status != JobStatus.SUCCEEDED:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
            self.phase_repo.update_failure_context(
                project_name,
                phase_name,
                PhaseResumeStage.FIX_BLOCKERS,
                fix_job.job_id,
                fix_exec.result_path,
                "fix blockers failed",
            )
            return

        self.phase_repo.clear_failure_context(project_name, phase_name)
        self.phase_repo.update_status(project_name, phase_name, PhaseStatus.RECHECK_PENDING)
        self._run_recheck_only_path(project_name, phase_name, executed)

    def _run_recheck_only_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        self._ensure_runtime_dependencies(require_snapshot_repo=True)

        snapshot = self.gate_snapshot_repo.get_latest(project_name, phase_name)
        recheck_job = self._new_phase_job(
            project_name,
            phase_name,
            "phase-recheck",
            review_origin_stage=ReviewOriginStage.PHASE_RECHECK,
            context_refs={"source_review_result_path": snapshot.result_path},
        )
        self.scheduler.enqueue(recheck_job)
        self.phase_repo.set_active_execution(
            project_name,
            phase_name,
            PhaseResumeStage.RECHECK,
            recheck_job.job_id,
            utc_now(),
        )
        try:
            recheck_exec = self.scheduler.execute_job(recheck_job.job_id)
        finally:
            self.phase_repo.clear_active_execution(project_name, phase_name)

        executed.append(recheck_job.job_id)
        recheck_exec = self._attach_gate_decision(recheck_exec)
        if self._block_review_like_failure(
            project_name,
            phase_name,
            recheck_exec,
            ReviewOriginStage.PHASE_RECHECK,
            "recheck worker failed before producing a gate",
        ):
            return

        self._route_gate_after_review(project_name, phase_name, recheck_exec, ReviewOriginStage.PHASE_RECHECK)

    def _run_close_path(self, project_name: str, phase_name: str, executed: list[str]) -> None:
        phase = self.phase_repo.get(project_name, phase_name)
        dedupe_scope = f"{project_name}:{phase_name}:{phase.latest_gate_snapshot_id or 'pending'}"
        close_marker = f"{project_name}:{phase_name}"
        self._append_backlog_step(project_name, phase_name, executed, dedupe_scope=dedupe_scope)

        phase = self.phase_repo.get(project_name, phase_name)
        if phase.status == PhaseStatus.BLOCKED_ON_WORKER_FAILURE:
            return

        self._close_phase_step(project_name, phase_name, executed, close_marker=close_marker)

    def _append_backlog_step(self, project_name: str, phase_name: str, executed: list[str], *, dedupe_scope: str) -> None:
        job_id = f"append-backlog:{project_name}:{phase_name}"
        self.phase_repo.set_active_execution(
            project_name,
            phase_name,
            PhaseResumeStage.APPEND_BACKLOG,
            job_id,
            utc_now(),
        )
        try:
            if self.job_repo is None or self.scheduler is None:
                executed.append(job_id)
                _ = dedupe_scope
                return

            backlog_job = self._new_phase_job(
                project_name,
                phase_name,
                "append-backlog",
                context_refs={"dedupe_scope": dedupe_scope},
            )
            self.scheduler.enqueue(backlog_job)
            backlog_exec = self.scheduler.execute_job(backlog_job.job_id)
            executed.append(backlog_job.job_id)
            if backlog_exec.completion.status != JobStatus.SUCCEEDED:
                self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
                self.phase_repo.update_failure_context(
                    project_name,
                    phase_name,
                    PhaseResumeStage.APPEND_BACKLOG,
                    backlog_job.job_id,
                    backlog_exec.result_path,
                    "append backlog failed",
                )
        finally:
            self.phase_repo.clear_active_execution(project_name, phase_name)

    def _close_phase_step(self, project_name: str, phase_name: str, executed: list[str], *, close_marker: str) -> None:
        job_id = f"close-phase:{project_name}:{phase_name}"
        self.phase_repo.set_active_execution(
            project_name,
            phase_name,
            PhaseResumeStage.CLOSE_PHASE,
            job_id,
            utc_now(),
        )
        try:
            if self.job_repo is None or self.scheduler is None:
                executed.append(job_id)
                _ = close_marker
            else:
                close_job = self._new_phase_job(
                    project_name,
                    phase_name,
                    "close-phase",
                    context_refs={"close_marker": close_marker},
                )
                self.scheduler.enqueue(close_job)
                close_exec = self.scheduler.execute_job(close_job.job_id)
                executed.append(close_job.job_id)
                if close_exec.completion.status != JobStatus.SUCCEEDED:
                    self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
                    self.phase_repo.update_failure_context(
                        project_name,
                        phase_name,
                        PhaseResumeStage.CLOSE_PHASE,
                        close_job.job_id,
                        close_exec.result_path,
                        "close phase failed",
                    )
                    return
        finally:
            self.phase_repo.clear_active_execution(project_name, phase_name)

        self.phase_repo.clear_failure_context(project_name, phase_name)
        self.phase_repo.update_status(project_name, phase_name, PhaseStatus.DONE)
        if self.project_service is not None:
            self.project_service.on_phase_done(project_name, phase_name)

    def _attach_gate_decision(self, exec_summary):
        if exec_summary.gate_decision is not None:
            return exec_summary

        gate = self._load_gate_decision(exec_summary)
        if gate is None:
            return exec_summary
        return replace(exec_summary, gate_decision=gate)

    def _load_gate_decision(self, exec_summary):
        if exec_summary.gate_decision is not None:
            return exec_summary.gate_decision

        if (
            self.artifact_store is None
            or exec_summary.result_path is None
            or not exec_summary.artifact_validation.passed
            or not self.artifact_store.exists(exec_summary.result_path)
        ):
            return None

        return parse_review_payload(self.artifact_store.read_json(exec_summary.result_path))

    def _block_review_like_failure(
        self,
        project_name: str,
        phase_name: str,
        exec_summary,
        origin_stage: ReviewOriginStage,
        reason: str,
    ) -> bool:
        if exec_summary.gate_decision is not None:
            return False

        blocked_status = (
            PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT
            if not exec_summary.artifact_validation.passed
            else PhaseStatus.BLOCKED_ON_WORKER_FAILURE
        )
        self.phase_repo.update_status(project_name, phase_name, blocked_status)
        self.phase_repo.update_failure_context(
            project_name,
            phase_name,
            self._resume_stage_from_origin(origin_stage),
            exec_summary.job_id,
            exec_summary.result_path,
            reason,
        )
        return True

    def _route_gate_after_review(
        self,
        project_name: str,
        phase_name: str,
        final_exec,
        origin_stage: ReviewOriginStage,
    ) -> None:
        self._ensure_runtime_dependencies(require_snapshot_repo=True)

        gate = final_exec.gate_decision
        if gate is None:
            raise MissingGateDecisionError("review routing requires a gate decision")

        snapshot = PhaseGateSnapshot(
            snapshot_id=f"snapshot:{project_name}:{phase_name}:{final_exec.job_id}",
            project_name=project_name,
            phase_name=phase_name,
            decision=gate.decision,
            source_job_id=final_exec.job_id,
            origin_stage=origin_stage,
            result_path=final_exec.result_path or "",
            blocker_count=gate.blocker_count,
            important_count=gate.important_count,
            later_count=gate.later_count,
        )
        self.gate_snapshot_repo.save(snapshot)
        self.phase_repo.set_latest_gate_ref(
            project_name,
            phase_name,
            snapshot.snapshot_id,
            snapshot.result_path,
            origin_stage,
        )
        self.phase_repo.clear_failure_context(project_name, phase_name)

        if gate.decision == GateDecisionType.INVALID_FORMAT:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT)
            self.phase_repo.update_failure_context(
                project_name,
                phase_name,
                self._resume_stage_from_origin(origin_stage),
                final_exec.job_id,
                final_exec.result_path,
                f"{origin_stage.value} invalid format",
            )
            return

        if gate.decision == GateDecisionType.FAIL:
            self.phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS)
            return

        if gate.decision == GateDecisionType.CONDITIONAL_PASS:
            if self.approval_service is None:
                raise RuntimeError("approval_service is required for conditional pass routing")
            self.approval_service.create_close_phase_with_important_open(
                project_name,
                phase_name,
                origin_stage=origin_stage,
                related_files=[final_exec.result_path] if final_exec.result_path else None,
            )
            return

        self.phase_repo.update_status(project_name, phase_name, PhaseStatus.READY_TO_CLOSE)

    def _snapshot_blockers_or_important(self, snapshot: PhaseGateSnapshot, review_payload: dict, approval) -> list[dict]:
        if snapshot.decision == GateDecisionType.FAIL:
            return list(review_payload.get("blockers") or [])

        if snapshot.decision == GateDecisionType.CONDITIONAL_PASS:
            if approval is None:
                raise InvalidRecheckSourceError("conditional pass snapshot requires an approval record")
            if approval.approval_type != ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN:
                raise InvalidRecheckSourceError("conditional pass snapshot must come from close-phase approval")
            if approval.status != ApprovalStatus.REJECTED:
                raise InvalidRecheckSourceError("conditional pass snapshot can enter fix path only after reject")
            return list(review_payload.get("important_items") or [])

        raise InvalidRecheckSourceError("fix path requires FAIL or rejected CONDITIONAL_PASS snapshot")

    @staticmethod
    def _resume_stage_from_origin(origin_stage: ReviewOriginStage) -> PhaseResumeStage:
        if origin_stage == ReviewOriginStage.PHASE_REVIEW:
            return PhaseResumeStage.REVIEW
        if origin_stage == ReviewOriginStage.PHASE_RECHECK:
            return PhaseResumeStage.RECHECK
        raise UnsupportedOriginStageError(f"unsupported origin stage: {origin_stage.value}")

    def _ensure_runtime_dependencies(self, *, require_snapshot_repo: bool = False, require_artifact_store: bool = False) -> None:
        if self.job_repo is None or self.scheduler is None:
            raise RuntimeError("job repository and scheduler are required for phase execution")
        if require_snapshot_repo and self.gate_snapshot_repo is None:
            raise RuntimeError("gate_snapshot_repo is required for this phase path")
        if require_artifact_store and self.artifact_store is None:
            raise RuntimeError("artifact_store is required for this phase path")

    @staticmethod
    def _new_phase_job(
        project_name: str,
        phase_name: str,
        job_type: str,
        review_origin_stage=None,
        context_refs=None,
    ) -> Job:
        return Job(
            job_id=f"{job_type}:{project_name}:{phase_name}",
            project_name=project_name,
            phase_name=phase_name,
            job_type=job_type,
            status=JobStatus.QUEUED,
            review_origin_stage=review_origin_stage,
            context_refs=dict(context_refs or {}),
        )
