from __future__ import annotations

from agent_orchestrator.application.scheduler_service import InMemorySchedulerService
from agent_orchestrator.domain.entities import Job
from agent_orchestrator.domain.enums import JobStatus
from agent_orchestrator.domain.results import ArtifactValidationResult, JobCompletion, JobExecutionSummary
from agent_orchestrator.infra.db.repositories import InMemoryJobRepository


def _summary(
    *,
    status: JobStatus = JobStatus.SUCCEEDED,
    result_path: str | None = None,
    artifact_passed: bool = True,
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


def test_in_memory_scheduler_enqueues_and_executes_planned_job_summary() -> None:
    job_repo = InMemoryJobRepository()
    scheduler = InMemorySchedulerService(
        job_repo=job_repo,
        planned_job_results={
            "phase-build": [
                _summary(result_path="/artifacts/build.json"),
            ],
        },
    )
    job = Job(
        job_id="phase-build:demo-project:phase-01",
        project_name="demo-project",
        phase_name="phase-01",
        job_type="phase-build",
        status=JobStatus.QUEUED,
    )

    scheduler.enqueue(job)
    exec_summary = scheduler.execute_job(job.job_id)

    stored = job_repo.get(job.job_id)
    assert exec_summary.job_id == job.job_id
    assert stored.status == JobStatus.SUCCEEDED
    assert stored.result_path == "/artifacts/build.json"
    assert stored.context_refs["status_reason"] == "ok"


def test_in_memory_scheduler_lease_freshness_can_be_toggled() -> None:
    job_repo = InMemoryJobRepository()
    scheduler = InMemorySchedulerService(job_repo=job_repo)
    job = Job(
        job_id="bootstrap-review:demo-project",
        project_name="demo-project",
        phase_name=None,
        job_type="bootstrap-review",
        status=JobStatus.RUNNING,
    )
    job_repo.save(job)

    assert scheduler.is_job_lease_fresh(job.job_id) is False

    scheduler.set_lease_fresh(job.job_id, True)

    assert scheduler.is_job_lease_fresh(job.job_id) is True
