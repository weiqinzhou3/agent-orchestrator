from __future__ import annotations

import subprocess
from typing import Any, Mapping

from agent_orchestrator.domain.enums import JobStatus
from agent_orchestrator.domain.results import ArtifactValidationResult, JobCompletion, JobExecutionSummary
from agent_orchestrator.infra.workers.base import WorkerRunSpec, WorkerRunner


class SubprocessRunner(WorkerRunner):
    def __init__(self, artifact_store, *, cwd: str | None = None):
        self.artifact_store = artifact_store
        self.cwd = cwd

    def run(self, spec: WorkerRunSpec) -> JobExecutionSummary:
        runtime_payload = self._runtime_payload(spec.input_payload)
        runtime_payload["result_path"] = str(self.artifact_store.resolve_path(spec.result_path))

        source_artifact_path = runtime_payload.get("source_artifact_path")
        if isinstance(source_artifact_path, str):
            runtime_payload["source_artifact_path"] = str(self.artifact_store.resolve_path(source_artifact_path))

        self.artifact_store.write_json(spec.input_path, runtime_payload)

        completed = subprocess.run(
            [
                spec.python_executable,
                "-m",
                spec.entry_module,
                "--job-type",
                spec.job_type,
                "--input",
                str(self.artifact_store.resolve_path(spec.input_path)),
                "--output",
                str(self.artifact_store.resolve_path(spec.result_path)),
            ],
            capture_output=True,
            text=True,
            cwd=self.cwd,
            check=False,
        )

        artifact_exists = self.artifact_store.exists(spec.result_path)
        return JobExecutionSummary(
            job_id=spec.job_id,
            completion=JobCompletion(
                status=JobStatus.SUCCEEDED if completed.returncode == 0 else JobStatus.FAILED,
                reason="ok" if completed.returncode == 0 else f"command exited with code {completed.returncode}",
            ),
            gate_decision=None,
            artifact_validation=ArtifactValidationResult(
                passed=artifact_exists,
                reason=None if artifact_exists else "expected artifact was not written",
            ),
            review_origin_stage=spec.review_origin_stage,
            result_path=spec.result_path,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    @staticmethod
    def _runtime_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        return dict(payload)
