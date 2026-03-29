from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from agent_orchestrator.domain.entities import Job
from agent_orchestrator.infra.workers.base import WorkerRunSpec

BUILD_LIKE_JOB_TYPES = {"bootstrap-repo", "phase-build", "phase-fix-blockers"}
REVIEW_LIKE_JOB_TYPES = {"bootstrap-review", "phase-review", "phase-recheck"}
SUPPORTED_JOB_TYPES = BUILD_LIKE_JOB_TYPES | REVIEW_LIKE_JOB_TYPES


def worker_artifact_path(job: Job, filename: str) -> str:
    scope = f"projects/{job.project_name}/bootstrap" if job.phase_name is None else f"projects/{job.project_name}/phases/{job.phase_name}"
    safe_job_id = job.job_id.replace(":", "__")
    return f"/artifacts/{scope}/{safe_job_id}/{filename}"


def default_source_artifact_path(job: Job) -> str | None:
    if job.job_type == "bootstrap-review":
        source_job = Job(
            job_id=f"bootstrap-repo:{job.project_name}",
            project_name=job.project_name,
            phase_name=None,
            job_type="bootstrap-repo",
            status=job.status,
        )
        return worker_artifact_path(source_job, "result.json")

    if job.job_type == "phase-review":
        source_job = Job(
            job_id=f"phase-build:{job.project_name}:{job.phase_name}",
            project_name=job.project_name,
            phase_name=job.phase_name,
            job_type="phase-build",
            status=job.status,
        )
        return worker_artifact_path(source_job, "result.json")

    return job.context_refs.get("source_artifact_path") or job.context_refs.get("source_review_result_path")


class LocalSubprocessJobFactory:
    def __init__(
        self,
        *,
        python_executable: str = sys.executable,
        entry_module: str = "agent_orchestrator.infra.workers.local",
    ):
        self.python_executable = python_executable
        self.entry_module = entry_module

    def supports(self, job: Job) -> bool:
        return job.job_type in SUPPORTED_JOB_TYPES

    def build(self, job: Job, *, extra_input: Mapping[str, Any] | None = None) -> WorkerRunSpec:
        input_path = job.context_refs.get("input_path") or worker_artifact_path(job, "input.json")
        result_path = job.context_refs.get("result_path") or worker_artifact_path(job, "result.json")
        payload: dict[str, Any] = {
            "job": {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "project_name": job.project_name,
                "phase_name": job.phase_name,
            },
            "context_refs": dict(job.context_refs),
            "logical_input_path": input_path,
            "logical_result_path": result_path,
        }
        source_artifact_path = default_source_artifact_path(job)
        if source_artifact_path is not None:
            payload["source_artifact_path"] = source_artifact_path
        if extra_input:
            payload.update(dict(extra_input))

        return WorkerRunSpec(
            job_id=job.job_id,
            job_type=job.job_type,
            entry_module=self.entry_module,
            python_executable=self.python_executable,
            input_path=input_path,
            result_path=result_path,
            input_payload=payload,
            review_origin_stage=job.review_origin_stage,
        )


def _write_json(path: str, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


def _run_build_like(job_type: str, payload: Mapping[str, Any], output_path: str) -> int:
    if payload.get("force_failure"):
        print(str(payload.get("failure_message", f"{job_type} failed")), file=sys.stderr)
        return int(payload.get("exit_code", 1))

    print(str(payload.get("stdout_message", f"{job_type} completed")))
    if payload.get("omit_output"):
        return 0

    artifact = {
        "artifact_type": job_type,
        "job": payload.get("job", {}),
        "review_payload": payload.get("review_payload", {"decision": "PASS"}),
        "notes": payload.get("notes", []),
        "omit_review_output": bool(payload.get("omit_review_output", False)),
    }
    _write_json(output_path, artifact)
    return 0


def _run_review_like(job_type: str, payload: Mapping[str, Any], output_path: str) -> int:
    if payload.get("force_failure"):
        print(str(payload.get("failure_message", f"{job_type} failed")), file=sys.stderr)
        return int(payload.get("exit_code", 1))

    source_artifact_path = payload.get("source_artifact_path")
    if not isinstance(source_artifact_path, str) or not Path(source_artifact_path).exists():
        print(f"{job_type} missing source artifact", file=sys.stderr)
        return int(payload.get("exit_code", 2))

    source_artifact = json.loads(Path(source_artifact_path).read_text(encoding="utf-8"))
    print(str(payload.get("stdout_message", f"{job_type} completed")))

    if source_artifact.get("omit_review_output") or payload.get("omit_output"):
        return 0

    review_payload = source_artifact.get("review_payload", {"decision": "PASS"})
    _write_json(output_path, review_payload)
    return 0


def _run_job(job_type: str, payload: Mapping[str, Any], output_path: str) -> int:
    if job_type in BUILD_LIKE_JOB_TYPES:
        return _run_build_like(job_type, payload, output_path)
    if job_type in REVIEW_LIKE_JOB_TYPES:
        return _run_review_like(job_type, payload, output_path)
    print(f"unsupported job type: {job_type}", file=sys.stderr)
    return 64


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-orchestrator-local-worker")
    parser.add_argument("--job-type", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    return _run_job(args.job_type, payload, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
