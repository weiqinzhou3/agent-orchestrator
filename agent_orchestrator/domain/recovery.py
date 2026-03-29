from __future__ import annotations

from .enums import BootstrapResumeStage, PhaseResumeStage, PhaseStatus, ProjectStatus


EXECUTING_BOOTSTRAP_STATES = {
    ProjectStatus.BOOTSTRAP_RUNNING,
    ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
}

FAILED_BLOCKING_BOOTSTRAP_STATES = {
    ProjectStatus.BLOCKED_ON_WORKER_FAILURE,
    ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT,
}

ALLOWED_BOOTSTRAP_ENTRY = {
    ProjectStatus.DESIGN_READY,
    ProjectStatus.BOOTSTRAP_RUNNING,
    ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
    ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS,
    ProjectStatus.BLOCKED_ON_WORKER_FAILURE,
    ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT,
}

EXECUTING_PHASE_STATES = {
    PhaseStatus.BUILDING,
    PhaseStatus.REVIEW_PENDING,
    PhaseStatus.BLOCKER_FIXING,
    PhaseStatus.RECHECK_PENDING,
}

FAILED_BLOCKING_PHASE_STATES = {
    PhaseStatus.BLOCKED_ON_WORKER_FAILURE,
    PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
}

ALLOWED_PHASE_ENTRY = {
    PhaseStatus.NOT_STARTED,
    PhaseStatus.CONTRACT_VALIDATED,
    PhaseStatus.CONTRACT_APPROVED,
    PhaseStatus.BUILDING,
    PhaseStatus.REVIEW_PENDING,
    PhaseStatus.BLOCKER_FIXING,
    PhaseStatus.RECHECK_PENDING,
    PhaseStatus.READY_TO_CLOSE,
    PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
    PhaseStatus.BLOCKED_ON_WORKER_FAILURE,
    PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
}

CLOSE_PATH_ACTIVE_STAGES = {
    PhaseResumeStage.APPEND_BACKLOG,
    PhaseResumeStage.CLOSE_PHASE,
}


def bootstrap_stage_from_status(status: ProjectStatus) -> BootstrapResumeStage:
    if status == ProjectStatus.BOOTSTRAP_RUNNING:
        return BootstrapResumeStage.BOOTSTRAP_REPO
    if status == ProjectStatus.BOOTSTRAP_REVIEW_PENDING:
        return BootstrapResumeStage.BOOTSTRAP_REVIEW
    raise ValueError(f"unsupported bootstrap status {status.value}")


def phase_stage_from_status(status: PhaseStatus) -> PhaseResumeStage:
    if status == PhaseStatus.BUILDING:
        return PhaseResumeStage.BUILD
    if status == PhaseStatus.REVIEW_PENDING:
        return PhaseResumeStage.REVIEW
    if status == PhaseStatus.BLOCKER_FIXING:
        return PhaseResumeStage.FIX_BLOCKERS
    if status == PhaseStatus.RECHECK_PENDING:
        return PhaseResumeStage.RECHECK
    raise ValueError(f"unsupported phase status {status.value}")
