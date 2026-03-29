from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Mapping, Sequence

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
    ):
        self.job_repo = job_repo
        self._planned_job_results = {
            job_type: list(results)
            for job_type, results in dict(planned_job_results or {}).items()
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

        planned = self._next_planned_summary(job)
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
        self.job_repo.save(job)
        self._lease_fresh[job_id] = False
        return summary

    def is_job_lease_fresh(self, job_id: str) -> bool:
        return self._lease_fresh.get(job_id, False)

    def set_lease_fresh(self, job_id: str, fresh: bool) -> None:
        self._lease_fresh[job_id] = fresh

    def _next_planned_summary(self, job: Job) -> JobExecutionSummary:
        planned = self._planned_job_results.get(job.job_type)
        if planned:
            return planned.pop(0)

        return JobExecutionSummary(
            job_id=job.job_id,
            completion=JobCompletion(status=JobStatus.SUCCEEDED, reason="ok"),
            gate_decision=None,
            artifact_validation=ArtifactValidationResult(passed=True),
            review_origin_stage=job.review_origin_stage,
            result_path=job.context_refs.get("result_path"),
        )
