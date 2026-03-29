from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from agent_orchestrator.application.approval_service import ApprovalService
from agent_orchestrator.application.phase_service import PhaseService
from agent_orchestrator.application.project_service import ProjectService
from agent_orchestrator.application.scheduler_service import InMemorySchedulerService
from agent_orchestrator.domain.entities import PhaseGateSnapshot
from agent_orchestrator.domain.enums import (
    ApprovalType,
    GateDecisionType,
    JobStatus,
    PhaseResumeStage,
    PhaseStatus,
    ProjectStatus,
    ReviewOriginStage,
)
from agent_orchestrator.domain.results import (
    ArtifactValidationResult,
    ContractValidationResult,
    JobCompletion,
    JobExecutionSummary,
)
from agent_orchestrator.infra.db.repositories import (
    InMemoryApprovalRepository,
    InMemoryJobRepository,
    InMemoryPhaseGateSnapshotRepository,
    InMemoryPhaseRepository,
    InMemoryProjectPlanRepository,
    InMemoryProjectRepository,
)
from agent_orchestrator.infra.execution.subprocess_runner import SubprocessRunner
from agent_orchestrator.infra.fs.artifact_store import FileArtifactStore, InMemoryArtifactStore
from agent_orchestrator.infra.workers.local import LocalSubprocessJobFactory


class RecordingPhaseRepository(InMemoryPhaseRepository):
    def __init__(self, phases):
        super().__init__(phases)
        self.active_execution_events = []

    def set_active_execution(self, project_name, phase_name, stage, job_id, started_at):
        self.active_execution_events.append(("set", stage, job_id))
        super().set_active_execution(project_name, phase_name, stage, job_id, started_at)

    def clear_active_execution(self, project_name, phase_name):
        self.active_execution_events.append(("clear",))
        super().clear_active_execution(project_name, phase_name)


class NoopRunLockRepository:
    @contextmanager
    def acquire_project_lock(self, project_name):
        yield

    @contextmanager
    def acquire_phase_lock(self, project_name, phase_name):
        yield


class NoApprovalContractService:
    def validate(self, project_name, phase_name):
        return ContractValidationResult(valid=True, contract_path=f"/contracts/{project_name}/{phase_name}.md")

    def resolve_approval_type(self, project_name, phase_name, contract_path):
        return None


class ApprovalContractService(NoApprovalContractService):
    def resolve_approval_type(self, project_name, phase_name, contract_path):
        return ApprovalType.CONTRACT_APPROVAL


def _summary(
    *,
    status: JobStatus = JobStatus.SUCCEEDED,
    artifact_passed: bool = True,
    result_path: str | None = None,
    reason: str = "ok",
    origin_stage: ReviewOriginStage | None = None,
) -> JobExecutionSummary:
    return JobExecutionSummary(
        job_id="planned",
        completion=JobCompletion(status=status, reason=reason),
        gate_decision=None,
        artifact_validation=ArtifactValidationResult(passed=artifact_passed),
        review_origin_stage=origin_stage,
        result_path=result_path,
    )


def _make_service(
    make_project,
    make_phase,
    *,
    phase_status: PhaseStatus,
    contract_service=None,
    planned_job_results=None,
    artifact_store=None,
):
    project_repo = InMemoryProjectRepository(
        {"demo-project": make_project(ProjectStatus.PHASE_ACTIVE, current_phase="phase-01")}
    )
    phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(phase_status)})
    approval_repo = InMemoryApprovalRepository()
    snapshot_repo = InMemoryPhaseGateSnapshotRepository()
    plan_repo = InMemoryProjectPlanRepository({"demo-project": ["phase-01", "phase-02"]})
    approval_service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    project_service = ProjectService(project_repo=project_repo, project_plan_repo=plan_repo, approval_service=approval_service)
    job_repo = InMemoryJobRepository()
    scheduler = InMemorySchedulerService(job_repo=job_repo, planned_job_results=planned_job_results or {})
    service = PhaseService(
        phase_repo=phase_repo,
        run_lock_repo=NoopRunLockRepository(),
        contract_service=contract_service or NoApprovalContractService(),
        approval_service=approval_service,
        project_service=project_service,
        job_repo=job_repo,
        scheduler=scheduler,
        approval_repo=approval_repo,
        gate_snapshot_repo=snapshot_repo,
        artifact_store=artifact_store or InMemoryArtifactStore(),
    )
    return service, phase_repo, project_repo, approval_repo, snapshot_repo


def _make_real_service(
    make_project,
    make_phase,
    tmp_path: Path,
    *,
    phase_status: PhaseStatus,
    planned_worker_inputs,
):
    artifact_store = FileArtifactStore(tmp_path)
    project_repo = InMemoryProjectRepository(
        {"demo-project": make_project(ProjectStatus.PHASE_ACTIVE, current_phase="phase-01")}
    )
    phase_repo = RecordingPhaseRepository({("demo-project", "phase-01"): make_phase(phase_status)})
    approval_repo = InMemoryApprovalRepository()
    snapshot_repo = InMemoryPhaseGateSnapshotRepository()
    plan_repo = InMemoryProjectPlanRepository({"demo-project": ["phase-01", "phase-02"]})
    approval_service = ApprovalService(project_repo=project_repo, phase_repo=phase_repo, approval_repo=approval_repo)
    project_service = ProjectService(project_repo=project_repo, project_plan_repo=plan_repo, approval_service=approval_service)
    job_repo = InMemoryJobRepository()
    scheduler = InMemorySchedulerService(
        job_repo=job_repo,
        worker_runner=SubprocessRunner(artifact_store=artifact_store),
        worker_job_factory=LocalSubprocessJobFactory(python_executable=sys.executable),
        planned_worker_inputs=planned_worker_inputs,
    )
    service = PhaseService(
        phase_repo=phase_repo,
        run_lock_repo=NoopRunLockRepository(),
        contract_service=NoApprovalContractService(),
        approval_service=approval_service,
        project_service=project_service,
        job_repo=job_repo,
        scheduler=scheduler,
        approval_repo=approval_repo,
        gate_snapshot_repo=snapshot_repo,
        artifact_store=artifact_store,
    )
    return service, phase_repo, project_repo, approval_repo, snapshot_repo


def test_phase_contract_approval_path_blocks_on_human(make_project, make_phase) -> None:
    service, phase_repo, _, approval_repo, _ = _make_service(
        make_project,
        make_phase,
        phase_status=PhaseStatus.NOT_STARTED,
        contract_service=ApprovalContractService(),
    )

    result = service.run_phase("demo-project", "phase-01")

    approval = approval_repo.get(result.pending_approval_id)
    phase = phase_repo.get("demo-project", "phase-01")
    assert result.final_status == PhaseStatus.BLOCKED_ON_HUMAN
    assert approval.approval_type == ApprovalType.CONTRACT_APPROVAL
    assert phase.latest_approval_id == approval.approval_id


def test_phase_build_review_pass_path_runs_to_done_and_marks_project_phase_done(make_project, make_phase) -> None:
    artifact_store = InMemoryArtifactStore()
    artifact_store.seed_json("/artifacts/phase-review-pass.json", {"decision": "PASS", "later_items": [{"id": "later-1"}]})
    service, phase_repo, project_repo, _, snapshot_repo = _make_service(
        make_project,
        make_phase,
        phase_status=PhaseStatus.NOT_STARTED,
        planned_job_results={
            "phase-build": [_summary()],
            "phase-review": [_summary(result_path="/artifacts/phase-review-pass.json", origin_stage=ReviewOriginStage.PHASE_REVIEW)],
        },
        artifact_store=artifact_store,
    )

    result = service.run_phase("demo-project", "phase-01")
    phase = phase_repo.get("demo-project", "phase-01")
    project = project_repo.get("demo-project")
    latest_snapshot = snapshot_repo.get_latest("demo-project", "phase-01")

    assert result.final_status == PhaseStatus.DONE
    assert project.status == ProjectStatus.PHASE_DONE
    assert latest_snapshot.decision.value == "PASS"
    assert phase.latest_gate_snapshot_id == latest_snapshot.snapshot_id
    assert phase.active_stage is None
    assert phase.active_job_id is None
    assert phase_repo.active_execution_events == [
        ("set", PhaseResumeStage.BUILD, "phase-build:demo-project:phase-01"),
        ("clear",),
        ("set", PhaseResumeStage.REVIEW, "phase-review:demo-project:phase-01"),
        ("clear",),
        ("set", PhaseResumeStage.APPEND_BACKLOG, "append-backlog:demo-project:phase-01"),
        ("clear",),
        ("set", PhaseResumeStage.CLOSE_PHASE, "close-phase:demo-project:phase-01"),
        ("clear",),
    ]


def test_phase_review_conditional_pass_creates_close_phase_approval(make_project, make_phase) -> None:
    artifact_store = InMemoryArtifactStore()
    artifact_store.seed_json(
        "/artifacts/phase-review-conditional.json",
        {"decision": "CONDITIONAL_PASS", "important_items": [{"id": "important-1"}]},
    )
    service, phase_repo, _, approval_repo, snapshot_repo = _make_service(
        make_project,
        make_phase,
        phase_status=PhaseStatus.CONTRACT_APPROVED,
        planned_job_results={
            "phase-build": [_summary()],
            "phase-review": [_summary(result_path="/artifacts/phase-review-conditional.json", origin_stage=ReviewOriginStage.PHASE_REVIEW)],
        },
        artifact_store=artifact_store,
    )

    result = service.run_phase("demo-project", "phase-01")
    approval = approval_repo.get(result.pending_approval_id)
    phase = phase_repo.get("demo-project", "phase-01")

    assert result.final_status == PhaseStatus.BLOCKED_ON_HUMAN
    assert approval.approval_type == ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN
    assert snapshot_repo.get_latest("demo-project", "phase-01").decision.value == "CONDITIONAL_PASS"
    assert phase.latest_approval_id == approval.approval_id


def test_phase_review_fail_path_blocks_on_open_blockers_and_persists_snapshot(make_project, make_phase) -> None:
    artifact_store = InMemoryArtifactStore()
    artifact_store.seed_json("/artifacts/phase-review-fail.json", {"decision": "FAIL", "blockers": [{"id": "blocker-1"}]})
    service, _, _, _, snapshot_repo = _make_service(
        make_project,
        make_phase,
        phase_status=PhaseStatus.CONTRACT_APPROVED,
        planned_job_results={
            "phase-build": [_summary()],
            "phase-review": [_summary(result_path="/artifacts/phase-review-fail.json", origin_stage=ReviewOriginStage.PHASE_REVIEW)],
        },
        artifact_store=artifact_store,
    )

    result = service.run_phase("demo-project", "phase-01")

    assert result.final_status == PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS
    assert snapshot_repo.get_latest("demo-project", "phase-01").decision.value == "FAIL"


@pytest.mark.parametrize(
    ("planned_summary", "payload", "expected_status"),
    [
        (_summary(result_path="/artifacts/phase-review-invalid.json", origin_stage=ReviewOriginStage.PHASE_REVIEW), {"decision": "INVALID_FORMAT"}, PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT),
        (_summary(artifact_passed=False, result_path="/artifacts/phase-review-missing.json", origin_stage=ReviewOriginStage.PHASE_REVIEW), None, PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT),
        (_summary(status=JobStatus.FAILED, result_path="/artifacts/phase-review-worker-failed.json", reason="worker failed", origin_stage=ReviewOriginStage.PHASE_REVIEW), None, PhaseStatus.BLOCKED_ON_WORKER_FAILURE),
    ],
)
def test_phase_review_invalid_missing_and_worker_failure_paths(
    make_project,
    make_phase,
    planned_summary,
    payload,
    expected_status,
) -> None:
    artifact_store = InMemoryArtifactStore()
    if payload is not None:
        artifact_store.seed_json(planned_summary.result_path, payload)
    service, phase_repo, _, _, _ = _make_service(
        make_project,
        make_phase,
        phase_status=PhaseStatus.CONTRACT_APPROVED,
        planned_job_results={
            "phase-build": [_summary()],
            "phase-review": [planned_summary],
        },
        artifact_store=artifact_store,
    )

    result = service.run_phase("demo-project", "phase-01")
    phase = phase_repo.get("demo-project", "phase-01")

    assert result.final_status == expected_status
    assert phase.last_failed_stage == PhaseResumeStage.REVIEW


def test_phase_fix_recheck_pass_path_uses_latest_snapshot_and_finishes_closeout(make_project, make_phase) -> None:
    artifact_store = InMemoryArtifactStore()
    artifact_store.seed_json("/artifacts/phase-review-fail.json", {"decision": "FAIL", "blockers": [{"id": "blocker-1"}]})
    artifact_store.seed_json("/artifacts/phase-recheck-pass.json", {"decision": "PASS"})
    service, phase_repo, project_repo, _, snapshot_repo = _make_service(
        make_project,
        make_phase,
        phase_status=PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
        planned_job_results={
            "phase-fix-blockers": [_summary()],
            "phase-recheck": [_summary(result_path="/artifacts/phase-recheck-pass.json", origin_stage=ReviewOriginStage.PHASE_RECHECK)],
        },
        artifact_store=artifact_store,
    )
    seed_snapshot = PhaseGateSnapshot(
        snapshot_id="snapshot-fail-1",
        project_name="demo-project",
        phase_name="phase-01",
        decision=GateDecisionType.FAIL,
        source_job_id="phase-review:demo-project:phase-01",
        origin_stage=ReviewOriginStage.PHASE_REVIEW,
        result_path="/artifacts/phase-review-fail.json",
        blocker_count=1,
        important_count=0,
        later_count=0,
    )
    snapshot_repo.save(seed_snapshot)
    phase_repo.set_latest_gate_ref("demo-project", "phase-01", seed_snapshot.snapshot_id, seed_snapshot.result_path, seed_snapshot.origin_stage)

    result = service.run_phase("demo-project", "phase-01")
    project = project_repo.get("demo-project")

    assert result.final_status == PhaseStatus.DONE
    assert project.status == ProjectStatus.PHASE_DONE
    assert snapshot_repo.get_latest("demo-project", "phase-01").origin_stage == ReviewOriginStage.PHASE_RECHECK


@pytest.mark.parametrize(
    ("planned_worker_inputs", "expected_status", "expected_approval_type"),
    [
        (
            {
                "phase-build": [{"review_payload": {"decision": "PASS"}}],
                "phase-review": [{}],
            },
            PhaseStatus.DONE,
            None,
        ),
        (
            {
                "phase-build": [
                    {
                        "review_payload": {
                            "decision": "CONDITIONAL_PASS",
                            "important_items": [{"id": "important-1"}],
                        }
                    }
                ],
                "phase-review": [{}],
            },
            PhaseStatus.BLOCKED_ON_HUMAN,
            ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN,
        ),
        (
            {
                "phase-build": [{"review_payload": {"decision": "FAIL", "blockers": [{"id": "blocker-1"}]}}],
                "phase-review": [{}],
            },
            PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
            None,
        ),
        (
            {
                "phase-build": [{"review_payload": ["invalid-payload"]}],
                "phase-review": [{}],
            },
            PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
            None,
        ),
        (
            {
                "phase-build": [{"omit_review_output": True}],
                "phase-review": [{}],
            },
            PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
            None,
        ),
    ],
)
def test_phase_local_subprocess_execution_paths(
    make_project,
    make_phase,
    tmp_path: Path,
    planned_worker_inputs,
    expected_status,
    expected_approval_type,
) -> None:
    service, _, project_repo, approval_repo, snapshot_repo = _make_real_service(
        make_project,
        make_phase,
        tmp_path,
        phase_status=PhaseStatus.NOT_STARTED,
        planned_worker_inputs=planned_worker_inputs,
    )

    result = service.run_phase("demo-project", "phase-01")

    assert result.final_status == expected_status
    if expected_status == PhaseStatus.DONE:
        assert project_repo.get("demo-project").status == ProjectStatus.PHASE_DONE
        assert snapshot_repo.get_latest("demo-project", "phase-01").decision.value == "PASS"
    if expected_approval_type is None:
        assert result.pending_approval_id is None
        return

    approval = approval_repo.get(result.pending_approval_id)
    assert approval.approval_type == expected_approval_type
