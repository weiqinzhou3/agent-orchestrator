from __future__ import annotations

from abc import ABC, abstractmethod

from agent_orchestrator.domain.entities import Job
from agent_orchestrator.domain.results import JobExecutionSummary


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
