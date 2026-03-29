from __future__ import annotations

import sys
from pathlib import Path

from agent_orchestrator.domain.entities import Job
from agent_orchestrator.domain.enums import JobStatus
from agent_orchestrator.infra.execution.subprocess_runner import SubprocessRunner
from agent_orchestrator.infra.fs.artifact_store import FileArtifactStore
from agent_orchestrator.infra.workers.local import LocalSubprocessJobFactory


def _make_job(
    *,
    job_id: str,
    job_type: str,
    project_name: str = "demo-project",
    phase_name: str | None = "phase-01",
) -> Job:
    return Job(
        job_id=job_id,
        project_name=project_name,
        phase_name=phase_name,
        job_type=job_type,
        status=JobStatus.QUEUED,
    )


def test_subprocess_runner_executes_local_worker_and_backfills_artifact_path(tmp_path: Path) -> None:
    artifact_store = FileArtifactStore(tmp_path)
    command_factory = LocalSubprocessJobFactory(python_executable=sys.executable)
    runner = SubprocessRunner(artifact_store=artifact_store)
    job = _make_job(job_id="phase-build:demo-project:phase-01", job_type="phase-build")

    spec = command_factory.build(
        job,
        extra_input={
            "review_payload": {"decision": "PASS", "later_items": [{"id": "later-1"}]},
            "stdout_message": "phase-build complete",
        },
    )

    summary = runner.run(spec)

    assert summary.completion.status == JobStatus.SUCCEEDED
    assert summary.exit_code == 0
    assert "phase-build complete" in summary.stdout
    assert summary.stderr == ""
    assert summary.result_path == spec.result_path
    assert artifact_store.read_json(summary.result_path)["review_payload"]["decision"] == "PASS"


def test_subprocess_runner_captures_non_zero_exit_and_stderr(tmp_path: Path) -> None:
    artifact_store = FileArtifactStore(tmp_path)
    command_factory = LocalSubprocessJobFactory(python_executable=sys.executable)
    runner = SubprocessRunner(artifact_store=artifact_store)
    job = _make_job(job_id="bootstrap-repo:demo-project", job_type="bootstrap-repo", phase_name=None)

    spec = command_factory.build(
        job,
        extra_input={"force_failure": True, "failure_message": "bootstrap repo failed", "exit_code": 7},
    )

    summary = runner.run(spec)

    assert summary.completion.status == JobStatus.FAILED
    assert summary.exit_code == 7
    assert "bootstrap repo failed" in summary.stderr
    assert summary.result_path == spec.result_path
    assert artifact_store.exists(spec.result_path) is False
