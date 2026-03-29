from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .enums import (
    ApprovalStatus,
    ApprovalType,
    BootstrapResumeStage,
    GateDecisionType,
    JobStatus,
    PhaseResumeStage,
    PhaseStatus,
    ProjectStatus,
    ReviewOriginStage,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class GateDecision:
    decision: GateDecisionType
    blocker_count: int = 0
    important_count: int = 0
    later_count: int = 0
    blockers: List[Dict[str, Any]] = field(default_factory=list)
    important_items: List[Dict[str, Any]] = field(default_factory=list)
    later_items: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PhaseGateSnapshot:
    snapshot_id: str
    project_name: str
    phase_name: str
    decision: GateDecisionType
    source_job_id: str
    origin_stage: ReviewOriginStage
    result_path: str
    blocker_count: int
    important_count: int
    later_count: int
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Project:
    project_name: str
    repo_root: str
    status: ProjectStatus
    current_phase: Optional[str] = None
    active_bootstrap_job_id: Optional[str] = None
    active_bootstrap_stage: Optional[BootstrapResumeStage] = None
    active_bootstrap_started_at: Optional[datetime] = None
    last_failed_bootstrap_stage: Optional[BootstrapResumeStage] = None
    last_failed_job_id: Optional[str] = None
    last_failed_result_path: Optional[str] = None
    last_failed_reason: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Phase:
    project_name: str
    phase_name: str
    contract_path: Optional[str]
    status: PhaseStatus
    latest_gate_snapshot_id: Optional[str] = None
    latest_gate_result_path: Optional[str] = None
    latest_gate_origin_stage: Optional[ReviewOriginStage] = None
    latest_approval_id: Optional[str] = None
    active_job_id: Optional[str] = None
    active_stage: Optional[PhaseResumeStage] = None
    active_job_started_at: Optional[datetime] = None
    last_failed_stage: Optional[PhaseResumeStage] = None
    last_failed_job_id: Optional[str] = None
    last_failed_result_path: Optional[str] = None
    last_failed_reason: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Job:
    job_id: str
    project_name: str
    phase_name: Optional[str]
    job_type: str
    status: JobStatus
    expected_outputs: List[str] = field(default_factory=list)
    parent_job_id: Optional[str] = None
    review_origin_stage: Optional[ReviewOriginStage] = None
    context_refs: Dict[str, str] = field(default_factory=dict)
    result_path: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Approval:
    approval_id: str
    project_name: str
    phase_name: Optional[str]
    approval_type: ApprovalType
    status: ApprovalStatus
    origin_stage: Optional[ReviewOriginStage] = None
    related_files: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
