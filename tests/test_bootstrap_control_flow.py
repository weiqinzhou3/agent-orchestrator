from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from agent_orchestrator.application.approval_service import ApprovalService
from agent_orchestrator.application.bootstrap_service import BootstrapService
from agent_orchestrator.application.scheduler_service import InMemorySchedulerService
from agent_orchestrator.domain.enums import ApprovalType, BootstrapResumeStage, JobStatus, ProjectStatus
from agent_orchestrator.domain.results import ArtifactValidationResult, JobCompletion, JobExecutionSummary
from agent_orchestrator.infra.db.repositories import (
    InMemoryApprovalRepository,
    InMemoryJobRepository,
    InMemoryPhaseRepository,
    InMemoryProjectRepository,
)
from agent_orchestrator.infra.execution.subprocess_runner import SubprocessRunner
from agent_orchestrator.infra.fs.artifact_store import InMemoryArtifactStore
from agent_orchestrator.infra.fs.artifact_store import FileArtifactStore
from agent_orchestrator.infra.workers.local import LocalSubprocessJobFactory


class RecordingProjectRepository(InMemoryProjectRepository):
    def __init__(self, projects):
        super().__init__(projects)
        self.active_execution_events = []

    def set_active_bootstrap_execution(self, project_name, stage, job_id, started_at):
        self.active_execution_events.append(("set", stage, job_id))
        super().set_active_bootstrap_execution(project_name, stage, job_id, started_at)

    def clear_active_bootstrap_execution(self, project_name):
        self.active_execution_events.append(("clear",))
        super().clear_active_bootstrap_execution(project_name)


class NoopRunLockRepository:
    @contextmanager
    def acquire_project_lock(self, project_name):
        yield

    @contextmanager
    def acquire_phase_lock(self, project_name, phase_name):
        yield


def _summary(
    *,
    status: JobStatus = JobStatus.SUCCEEDED,
    artifact_passed: bool = True,
    result_path: str | None = None,
    reason: str = "ok",
) -> JobExecutionSummary:
    return JobExecutionSummary(
        job_id="planned",
        completion=JobCompletion(status=status, reason=reason),
        gate_decision=None,
        artifact_validation=ArtifactValidationResult(passed=artifact_passed),
        review_origin_stage=None,
        result_path=result_path,
    )


def _make_service(make_project, planned_job_results, artifact_store):
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.DESIGN_READY)})
    phase_repo = InMemoryPhaseRepository({})
    approval_repo = InMemoryApprovalRepository()
    approval_service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    job_repo = InMemoryJobRepository()
    scheduler = InMemorySchedulerService(job_repo=job_repo, planned_job_results=planned_job_results)
    service = BootstrapService(
        project_repo=project_repo,
        run_lock_repo=NoopRunLockRepository(),
        job_repo=job_repo,
        scheduler=scheduler,
        approval_repo=approval_repo,
        approval_service=approval_service,
        artifact_store=artifact_store,
    )
    return service, project_repo, approval_repo


def _make_real_service(make_project, tmp_path: Path, planned_worker_inputs):
    artifact_store = FileArtifactStore(tmp_path)
    project_repo = RecordingProjectRepository({"demo-project": make_project(ProjectStatus.DESIGN_READY)})
    phase_repo = InMemoryPhaseRepository({})
    approval_repo = InMemoryApprovalRepository()
    approval_service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    job_repo = InMemoryJobRepository()
    scheduler = InMemorySchedulerService(
        job_repo=job_repo,
        worker_runner=SubprocessRunner(artifact_store=artifact_store),
        worker_job_factory=LocalSubprocessJobFactory(python_executable=sys.executable),
        planned_worker_inputs=planned_worker_inputs,
    )
    service = BootstrapService(
        project_repo=project_repo,
        run_lock_repo=NoopRunLockRepository(),
        job_repo=job_repo,
        scheduler=scheduler,
        approval_repo=approval_repo,
        approval_service=approval_service,
        artifact_store=artifact_store,
    )
    return service, project_repo, approval_repo


def test_bootstrap_pass_path_reaches_bootstrap_ready_and_clears_active_execution(make_project) -> None:
    artifact_store = InMemoryArtifactStore()
    artifact_store.seed_json("/artifacts/bootstrap-review-pass.json", {"decision": "PASS"})
    service, project_repo, _ = _make_service(
        make_project,
        {
            "bootstrap-repo": [_summary()],
            "bootstrap-review": [_summary(result_path="/artifacts/bootstrap-review-pass.json")],
        },
        artifact_store,
    )

    result = service.run_bootstrap("demo-project")

    project = project_repo.get("demo-project")
    assert result.final_status == ProjectStatus.BOOTSTRAP_READY
    assert result.executed_job_ids == [
        "bootstrap-repo:demo-project",
        "bootstrap-review:demo-project",
    ]
    assert project.active_bootstrap_stage is None
    assert project.active_bootstrap_job_id is None
    assert project.last_failed_bootstrap_stage is None
    assert project_repo.active_execution_events == [
        ("set", BootstrapResumeStage.BOOTSTRAP_REPO, "bootstrap-repo:demo-project"),
        ("clear",),
        ("set", BootstrapResumeStage.BOOTSTRAP_REVIEW, "bootstrap-review:demo-project"),
        ("clear",),
    ]


def test_bootstrap_conditional_pass_creates_approval_and_blocks_on_human(make_project) -> None:
    artifact_store = InMemoryArtifactStore()
    artifact_store.seed_json(
        "/artifacts/bootstrap-review-conditional.json",
        {"decision": "CONDITIONAL_PASS", "important_items": [{"id": "important-1"}]},
    )
    service, _, approval_repo = _make_service(
        make_project,
        {
            "bootstrap-repo": [_summary()],
            "bootstrap-review": [_summary(result_path="/artifacts/bootstrap-review-conditional.json")],
        },
        artifact_store,
    )

    result = service.run_bootstrap("demo-project")

    approval = approval_repo.get(result.pending_approval_id)
    assert result.final_status == ProjectStatus.BLOCKED_ON_HUMAN
    assert approval.approval_type == ApprovalType.BOOTSTRAP_READY_WITH_IMPORTANT_OPEN


def test_bootstrap_fail_path_blocks_on_open_blockers(make_project) -> None:
    artifact_store = InMemoryArtifactStore()
    artifact_store.seed_json("/artifacts/bootstrap-review-fail.json", {"decision": "FAIL", "blockers": [{"id": "b-1"}]})
    service, _, _ = _make_service(
        make_project,
        {
            "bootstrap-repo": [_summary()],
            "bootstrap-review": [_summary(result_path="/artifacts/bootstrap-review-fail.json")],
        },
        artifact_store,
    )

    result = service.run_bootstrap("demo-project")

    assert result.final_status == ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS


def test_bootstrap_invalid_format_blocks_on_missing_artifact_and_updates_failure_context(make_project) -> None:
    artifact_store = InMemoryArtifactStore()
    artifact_store.seed_json("/artifacts/bootstrap-review-invalid.json", {"decision": "INVALID_FORMAT"})
    service, project_repo, _ = _make_service(
        make_project,
        {
            "bootstrap-repo": [_summary()],
            "bootstrap-review": [_summary(result_path="/artifacts/bootstrap-review-invalid.json")],
        },
        artifact_store,
    )

    result = service.run_bootstrap("demo-project")
    project = project_repo.get("demo-project")

    assert result.final_status == ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT
    assert project.last_failed_bootstrap_stage == BootstrapResumeStage.BOOTSTRAP_REVIEW
    assert project.last_failed_result_path == "/artifacts/bootstrap-review-invalid.json"


@pytest.mark.parametrize(
    ("planned_summary", "expected_status"),
    [
        (_summary(artifact_passed=False, result_path="/artifacts/bootstrap-review-missing.json"), ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT),
        (_summary(status=JobStatus.FAILED, result_path="/artifacts/bootstrap-review-worker-failed.json", reason="worker failed"), ProjectStatus.BLOCKED_ON_WORKER_FAILURE),
    ],
)
def test_bootstrap_missing_artifact_and_worker_failure_paths(
    make_project,
    planned_summary,
    expected_status,
) -> None:
    service, project_repo, _ = _make_service(
        make_project,
        {
            "bootstrap-repo": [_summary()],
            "bootstrap-review": [planned_summary],
        },
        InMemoryArtifactStore(),
    )

    result = service.run_bootstrap("demo-project")
    project = project_repo.get("demo-project")

    assert result.final_status == expected_status
    assert project.last_failed_bootstrap_stage == BootstrapResumeStage.BOOTSTRAP_REVIEW


@pytest.mark.parametrize(
    ("planned_worker_inputs", "expected_status", "expected_approval_type"),
    [
        (
            {
                "bootstrap-repo": [{"review_payload": {"decision": "PASS"}}],
                "bootstrap-review": [{}],
            },
            ProjectStatus.BOOTSTRAP_READY,
            None,
        ),
        (
            {
                "bootstrap-repo": [
                    {
                        "review_payload": {
                            "decision": "CONDITIONAL_PASS",
                            "important_items": [{"id": "important-1"}],
                        }
                    }
                ],
                "bootstrap-review": [{}],
            },
            ProjectStatus.BLOCKED_ON_HUMAN,
            ApprovalType.BOOTSTRAP_READY_WITH_IMPORTANT_OPEN,
        ),
        (
            {
                "bootstrap-repo": [{"review_payload": {"decision": "FAIL", "blockers": [{"id": "blocker-1"}]}}],
                "bootstrap-review": [{}],
            },
            ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS,
            None,
        ),
        (
            {
                "bootstrap-repo": [{"review_payload": ["invalid-payload"]}],
                "bootstrap-review": [{}],
            },
            ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT,
            None,
        ),
        (
            {
                "bootstrap-repo": [{"omit_review_output": True}],
                "bootstrap-review": [{}],
            },
            ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT,
            None,
        ),
    ],
)
def test_bootstrap_local_subprocess_execution_paths(
    make_project,
    tmp_path: Path,
    planned_worker_inputs,
    expected_status,
    expected_approval_type,
) -> None:
    service, _, approval_repo = _make_real_service(make_project, tmp_path, planned_worker_inputs)

    result = service.run_bootstrap("demo-project")

    assert result.final_status == expected_status
    if expected_approval_type is None:
        assert result.pending_approval_id is None
        return

    approval = approval_repo.get(result.pending_approval_id)
    assert approval.approval_type == expected_approval_type
