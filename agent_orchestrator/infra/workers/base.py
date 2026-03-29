from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping

from agent_orchestrator.domain.enums import ReviewOriginStage
from agent_orchestrator.domain.results import JobExecutionSummary


@dataclass(frozen=True)
class WorkerRunSpec:
    job_id: str
    job_type: str
    entry_module: str
    python_executable: str
    input_path: str
    result_path: str
    input_payload: Mapping[str, Any]
    review_origin_stage: ReviewOriginStage | None = None


class WorkerRunner(ABC):
    @abstractmethod
    def run(self, spec: WorkerRunSpec) -> JobExecutionSummary:
        raise NotImplementedError


class Worker:
    def run(self, job):
        raise NotImplementedError("worker execution is out of scope for phase-01")
