from __future__ import annotations

from agent_orchestrator.domain.entities import Job, utc_now
from agent_orchestrator.domain.enums import GateDecisionType, JobStatus, ProjectStatus, ReviewOriginStage
from agent_orchestrator.domain.errors import BootstrapAlreadyRunningError, InvalidProjectTransitionError, MissingResumeContextError
from agent_orchestrator.domain.recovery import (
    ALLOWED_BOOTSTRAP_ENTRY,
    EXECUTING_BOOTSTRAP_STATES,
    FAILED_BLOCKING_BOOTSTRAP_STATES,
    bootstrap_stage_from_status,
)
from agent_orchestrator.domain.results import BootstrapRunResult
from agent_orchestrator.domain.review_parser import parse_review_payload


class BootstrapService:
    def __init__(
        self,
        project_repo,
        run_lock_repo,
        job_repo=None,
        scheduler=None,
        approval_repo=None,
        approval_service=None,
        artifact_store=None,
    ):
        self.project_repo = project_repo
        self.run_lock_repo = run_lock_repo
        self.job_repo = job_repo
        self.scheduler = scheduler
        self.approval_repo = approval_repo
        self.approval_service = approval_service
        self.artifact_store = artifact_store

    def run_bootstrap(self, project_name: str, force_full: bool = False) -> BootstrapRunResult:
        with self.run_lock_repo.acquire_project_lock(project_name):
            project = self.project_repo.get(project_name)
            if project.status not in ALLOWED_BOOTSTRAP_ENTRY:
                raise InvalidProjectTransitionError(
                    f"project {project_name} is {project.status.value}, bootstrap run is not allowed"
                )

            executed: list[str] = []

            self._reconcile_inflight_bootstrap_entry(project_name)
            self._normalize_failed_bootstrap_entry(project_name, force_full)
            self._run_bootstrap_waterfall(project_name, executed)

            project = self.project_repo.get(project_name)
            return BootstrapRunResult(
                project_name=project_name,
                final_status=project.status,
                executed_job_ids=executed,
                pending_approval_id=self._find_pending_approval_id(project_name),
                message="bootstrap run completed",
            )

    def _reconcile_inflight_bootstrap_entry(self, project_name: str) -> None:
        project = self.project_repo.get(project_name)
        if project.status not in EXECUTING_BOOTSTRAP_STATES:
            return

        failed_stage = bootstrap_stage_from_status(project.status)

        if project.active_bootstrap_job_id is None:
            self.project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_WORKER_FAILURE)
            self.project_repo.update_failure_context(
                project_name,
                failed_stage,
                None,
                None,
                f"inflight {project.status.value} without active job; treating as interrupted bootstrap",
            )
            self.project_repo.clear_active_bootstrap_execution(project_name)
            return

        if self.job_repo is None or self.scheduler is None:
            raise MissingResumeContextError("job repository and scheduler are required for inflight bootstrap reconciliation")

        job = self.job_repo.get(project.active_bootstrap_job_id)
        if job.status == JobStatus.RUNNING and self.scheduler.is_job_lease_fresh(job.job_id):
            raise BootstrapAlreadyRunningError(f"bootstrap is already running for {project_name}")

        if job.status == JobStatus.RUNNING:
            self.job_repo.mark_stale_failed(job.job_id, "stale inflight bootstrap job detected during resume")

        blocked_status = (
            ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT
            if failed_stage.value == "BOOTSTRAP_REVIEW" and not bool(job.result_path)
            else ProjectStatus.BLOCKED_ON_WORKER_FAILURE
        )
        self.project_repo.update_status(project_name, blocked_status)
        self.project_repo.update_failure_context(
            project_name,
            failed_stage,
            job.job_id,
            job.result_path,
            f"inflight {project.status.value} interrupted or stale; last job status={job.status.value}",
        )
        self.project_repo.clear_active_bootstrap_execution(project_name)

    def _normalize_failed_bootstrap_entry(self, project_name: str, force_full: bool) -> None:
        project = self.project_repo.get(project_name)

        if project.status == ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS:
            target = ProjectStatus.BOOTSTRAP_RUNNING if force_full else ProjectStatus.BOOTSTRAP_REVIEW_PENDING
            self.project_repo.update_status(project_name, target)
            return

        if project.status not in FAILED_BLOCKING_BOOTSTRAP_STATES:
            return

        if force_full:
            self.project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_RUNNING)
            return

        if project.last_failed_bootstrap_stage is None:
            raise MissingResumeContextError("missing bootstrap failure context")

        if project.last_failed_bootstrap_stage.value == "BOOTSTRAP_REPO":
            self.project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_RUNNING)
            return

        if project.last_failed_bootstrap_stage.value == "BOOTSTRAP_REVIEW":
            self.project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_REVIEW_PENDING)
            return

        raise MissingResumeContextError("unsupported bootstrap failure stage")

    def _run_bootstrap_waterfall(self, project_name: str, executed: list[str]) -> None:
        project = self.project_repo.get(project_name)

        if project.status == ProjectStatus.DESIGN_READY:
            self.project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_RUNNING)
            project = self.project_repo.get(project_name)

        if project.status == ProjectStatus.BOOTSTRAP_RUNNING:
            self._run_bootstrap_repo_path(project_name, executed)
            project = self.project_repo.get(project_name)

        if project.status == ProjectStatus.BOOTSTRAP_REVIEW_PENDING:
            self._run_bootstrap_review_path(project_name, executed)

    def _run_bootstrap_repo_path(self, project_name: str, executed: list[str]) -> None:
        self._ensure_runtime_dependencies()

        bootstrap_job = self._new_bootstrap_job(project_name, "bootstrap-repo")
        self.scheduler.enqueue(bootstrap_job)
        self.project_repo.set_active_bootstrap_execution(
            project_name,
            bootstrap_stage_from_status(ProjectStatus.BOOTSTRAP_RUNNING),
            bootstrap_job.job_id,
            utc_now(),
        )
        try:
            bootstrap_exec = self.scheduler.execute_job(bootstrap_job.job_id)
        finally:
            self.project_repo.clear_active_bootstrap_execution(project_name)

        executed.append(bootstrap_job.job_id)

        if bootstrap_exec.completion.status != JobStatus.SUCCEEDED:
            self.project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_WORKER_FAILURE)
            self.project_repo.update_failure_context(
                project_name,
                bootstrap_stage_from_status(ProjectStatus.BOOTSTRAP_RUNNING),
                bootstrap_job.job_id,
                bootstrap_exec.result_path,
                "bootstrap-repo failed",
            )
            return

        self.project_repo.clear_failure_context(project_name)
        self.project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_REVIEW_PENDING)

    def _run_bootstrap_review_path(self, project_name: str, executed: list[str]) -> None:
        self._ensure_runtime_dependencies()

        review_job = self._new_bootstrap_job(
            project_name,
            "bootstrap-review",
            review_origin_stage=ReviewOriginStage.BOOTSTRAP_REVIEW,
        )
        self.scheduler.enqueue(review_job)
        self.project_repo.set_active_bootstrap_execution(
            project_name,
            bootstrap_stage_from_status(ProjectStatus.BOOTSTRAP_REVIEW_PENDING),
            review_job.job_id,
            utc_now(),
        )
        try:
            review_exec = self.scheduler.execute_job(review_job.job_id)
        finally:
            self.project_repo.clear_active_bootstrap_execution(project_name)

        executed.append(review_job.job_id)
        gate = self._load_gate_decision(review_exec)

        if review_exec.completion.status not in {JobStatus.SUCCEEDED, JobStatus.DONE_WITH_CONCERNS} and gate is None:
            self.project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_WORKER_FAILURE)
            self.project_repo.update_failure_context(
                project_name,
                bootstrap_stage_from_status(ProjectStatus.BOOTSTRAP_REVIEW_PENDING),
                review_exec.job_id,
                review_exec.result_path,
                "bootstrap review did not produce a valid gate decision",
            )
            return

        if gate is None:
            blocked_status = (
                ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT
                if not review_exec.artifact_validation.passed
                else ProjectStatus.BLOCKED_ON_WORKER_FAILURE
            )
            self.project_repo.update_status(project_name, blocked_status)
            self.project_repo.update_failure_context(
                project_name,
                bootstrap_stage_from_status(ProjectStatus.BOOTSTRAP_REVIEW_PENDING),
                review_exec.job_id,
                review_exec.result_path,
                "bootstrap review did not produce a valid gate decision",
            )
            return

        self.project_repo.clear_failure_context(project_name)

        if gate.decision == GateDecisionType.INVALID_FORMAT:
            self.project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT)
            self.project_repo.update_failure_context(
                project_name,
                bootstrap_stage_from_status(ProjectStatus.BOOTSTRAP_REVIEW_PENDING),
                review_exec.job_id,
                review_exec.result_path,
                "bootstrap review invalid format",
            )
            return

        if gate.decision == GateDecisionType.FAIL:
            self.project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS)
            return

        if gate.decision == GateDecisionType.CONDITIONAL_PASS:
            if self.approval_service is None:
                raise RuntimeError("approval_service is required for bootstrap conditional pass routing")
            self.approval_service.create_bootstrap_ready_with_important_open(
                project_name,
                origin_stage=ReviewOriginStage.BOOTSTRAP_REVIEW,
                related_files=[review_exec.result_path] if review_exec.result_path else None,
            )
            return

        self.project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_READY)

    def _find_pending_approval_id(self, project_name: str):
        if self.approval_repo is None:
            return None
        pending = self.approval_repo.list_pending(project_name)
        return pending[0].approval_id if pending else None

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

    def _ensure_runtime_dependencies(self) -> None:
        if self.job_repo is None or self.scheduler is None:
            raise RuntimeError("job repository and scheduler are required for bootstrap execution")

    @staticmethod
    def _new_bootstrap_job(project_name: str, job_type: str, review_origin_stage=None) -> Job:
        return Job(
            job_id=f"{job_type}:{project_name}",
            project_name=project_name,
            phase_name=None,
            job_type=job_type,
            status=JobStatus.QUEUED,
            review_origin_stage=review_origin_stage,
        )
