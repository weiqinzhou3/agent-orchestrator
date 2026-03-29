from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any, Mapping, Sequence

from agent_orchestrator.domain.entities import Job, utc_now
from agent_orchestrator.domain.results import JobExecutionSummary
from agent_orchestrator.domain.results import ArtifactValidationResult, JobCompletion
from agent_orchestrator.domain.enums import JobStatus


class SchedulerService(ABC):
    @abstractmethod
    def enqueue(self, job: Job) -> None:
        raise NotImplementedError

    @abstractmethod
    def execute_job(self, job_id: str) -> JobExecutionSummary:
        raise NotImplementedError

    @abstractmethod
    def is_job_lease_fresh(self, job_id: str) -> bool:
        raise NotImplementedError


class StubSchedulerService(SchedulerService):
    def enqueue(self, job: Job) -> None:
        return None

    def execute_job(self, job_id: str) -> JobExecutionSummary:
        raise NotImplementedError("job execution is out of scope for phase-01")

    def is_job_lease_fresh(self, job_id: str) -> bool:
        return False


class InMemorySchedulerService(SchedulerService):
    def __init__(
        self,
        job_repo,
        planned_job_results: Mapping[str, Sequence[JobExecutionSummary]] | None = None,
        worker_runner=None,
        worker_job_factory=None,
        planned_worker_inputs: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ):
        self.job_repo = job_repo
        self._planned_job_results = {
            job_type: list(results)
            for job_type, results in dict(planned_job_results or {}).items()
        }
        self.worker_runner = worker_runner
        self.worker_job_factory = worker_job_factory
        self._planned_worker_inputs = {
            job_type: [dict(item) for item in items]
            for job_type, items in dict(planned_worker_inputs or {}).items()
        }
        self._lease_fresh: dict[str, bool] = {}

    def enqueue(self, job: Job) -> None:
        job.status = JobStatus.QUEUED
        job.updated_at = utc_now()
        self.job_repo.save(job)

    def execute_job(self, job_id: str) -> JobExecutionSummary:
        job = self.job_repo.get(job_id)
        job.status = JobStatus.RUNNING
        job.last_heartbeat_at = utc_now()
        job.updated_at = utc_now()
        self.job_repo.save(job)

        planned = self._next_execution_summary(job)
        summary = replace(
            planned,
            job_id=job.job_id,
            review_origin_stage=planned.review_origin_stage or job.review_origin_stage,
        )

        job.status = summary.completion.status
        job.result_path = summary.result_path
        job.last_heartbeat_at = utc_now()
        job.updated_at = utc_now()
        job.context_refs["status_reason"] = summary.completion.reason
        if summary.exit_code is not None:
            job.context_refs["exit_code"] = str(summary.exit_code)
        if summary.stdout:
            job.context_refs["stdout"] = summary.stdout
        if summary.stderr:
            job.context_refs["stderr"] = summary.stderr
        self.job_repo.save(job)
        self._lease_fresh[job_id] = False
        return summary

    def is_job_lease_fresh(self, job_id: str) -> bool:
        return self._lease_fresh.get(job_id, False)

    def set_lease_fresh(self, job_id: str, fresh: bool) -> None:
        self._lease_fresh[job_id] = fresh

    def _next_execution_summary(self, job: Job) -> JobExecutionSummary:
        planned = self._planned_job_results.get(job.job_type)
        if planned:
            return planned.pop(0)

        if self.worker_runner is not None and self.worker_job_factory is not None and self.worker_job_factory.supports(job):
            spec = self.worker_job_factory.build(job, extra_input=self._next_worker_input(job))
            return self.worker_runner.run(spec)

        return JobExecutionSummary(
            job_id=job.job_id,
            completion=JobCompletion(status=JobStatus.SUCCEEDED, reason="ok"),
            gate_decision=None,
            artifact_validation=ArtifactValidationResult(passed=True),
            review_origin_stage=job.review_origin_stage,
            result_path=job.context_refs.get("result_path"),
            exit_code=0,
        )

    def _next_worker_input(self, job: Job) -> dict[str, Any]:
        planned = self._planned_worker_inputs.get(job.job_type)
        if planned:
            return planned.pop(0)
        return {}
