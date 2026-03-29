from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .entities import GateDecision
from .enums import ApprovalType, JobStatus, PhaseStatus, ProjectStatus, ReviewOriginStage


@dataclass
class ArtifactValidationResult:
    passed: bool
    reason: Optional[str] = None


@dataclass
class ContractValidationResult:
    valid: bool
    contract_path: Optional[str]
    reason: Optional[str] = None


@dataclass
class JobCompletion:
    status: JobStatus
    reason: str
    concern_codes: List[str] = field(default_factory=list)


@dataclass
class JobExecutionSummary:
    job_id: str
    completion: JobCompletion
    gate_decision: Optional[GateDecision]
    artifact_validation: ArtifactValidationResult
    review_origin_stage: Optional[ReviewOriginStage]
    result_path: Optional[str]


@dataclass
class BootstrapRunResult:
    project_name: str
    final_status: ProjectStatus
    executed_job_ids: List[str]
    pending_approval_id: Optional[str]
    message: str


@dataclass
class PhaseRunResult:
    project_name: str
    phase_name: str
    final_status: PhaseStatus
    executed_job_ids: List[str]
    pending_approval_id: Optional[str]
    message: str


@dataclass
class ApprovalOutcome:
    approval_id: str
    approval_type: ApprovalType
    new_project_status: Optional[ProjectStatus]
    new_phase_status: Optional[PhaseStatus]
    resume_command: Optional[str]
