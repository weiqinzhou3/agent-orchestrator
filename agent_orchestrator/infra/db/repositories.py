from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import count
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from agent_orchestrator.domain.entities import Approval, Job, Phase, PhaseGateSnapshot, Project, utc_now
from agent_orchestrator.domain.enums import (
    ApprovalStatus,
    ApprovalType,
    BootstrapResumeStage,
    JobStatus,
    PhaseResumeStage,
    PhaseStatus,
    ProjectStatus,
    ReviewOriginStage,
)
from agent_orchestrator.domain.state_machine import ensure_phase_transition, ensure_project_transition


class ProjectRepository(ABC):
    @abstractmethod
    def get(self, project_name: str) -> Project:
        raise NotImplementedError

    @abstractmethod
    def update_status(self, project_name: str, status: ProjectStatus) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_current_phase(self, project_name: str, phase_name: Optional[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_active_bootstrap_execution(
        self,
        project_name: str,
        stage: BootstrapResumeStage,
        job_id: str,
        started_at,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_active_bootstrap_execution(self, project_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_failure_context(
        self,
        project_name: str,
        stage: BootstrapResumeStage,
        job_id: Optional[str],
        result_path: Optional[str],
        reason: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_failure_context(self, project_name: str) -> None:
        raise NotImplementedError


class PhaseRepository(ABC):
    @abstractmethod
    def get(self, project_name: str, phase_name: str) -> Phase:
        raise NotImplementedError

    @abstractmethod
    def update_status(self, project_name: str, phase_name: str, status: PhaseStatus) -> None:
        raise NotImplementedError

    @abstractmethod
    def attach_latest_approval(self, project_name: str, phase_name: str, approval_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_latest_gate_ref(
        self,
        project_name: str,
        phase_name: str,
        snapshot_id: str,
        result_path: str,
        origin_stage: ReviewOriginStage,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_active_execution(
        self,
        project_name: str,
        phase_name: str,
        stage: PhaseResumeStage,
        job_id: str,
        started_at,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_active_execution(self, project_name: str, phase_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_failure_context(
        self,
        project_name: str,
        phase_name: str,
        stage: PhaseResumeStage,
        job_id: Optional[str],
        result_path: Optional[str],
        reason: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_failure_context(self, project_name: str, phase_name: str) -> None:
        raise NotImplementedError


class PhaseGateSnapshotRepository(ABC):
    @abstractmethod
    def save(self, snapshot: PhaseGateSnapshot) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_latest(self, project_name: str, phase_name: str) -> PhaseGateSnapshot:
        raise NotImplementedError


class JobRepository(ABC):
    @abstractmethod
    def get(self, job_id: str) -> Job:
        raise NotImplementedError

    @abstractmethod
    def save(self, job: Job) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_status(self, job_id: str, status: JobStatus, reason: Optional[str] = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def mark_stale_failed(self, job_id: str, reason: str) -> None:
        raise NotImplementedError


class ApprovalRepository(ABC):
    @abstractmethod
    def get(self, approval_id: str) -> Approval:
        raise NotImplementedError

    @abstractmethod
    def list_pending(self, project_name: str) -> List[Approval]:
        raise NotImplementedError

    @abstractmethod
    def create(
        self,
        project_name: str,
        phase_name: Optional[str],
        approval_type: ApprovalType,
        origin_stage: Optional[ReviewOriginStage],
        related_files: Optional[List[str]] = None,
    ) -> Approval:
        raise NotImplementedError

    @abstractmethod
    def save(self, approval: Approval) -> None:
        raise NotImplementedError

    @abstractmethod
    def mark_approved(self, approval_id: str, actor: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def mark_rejected(self, approval_id: str, actor: str) -> None:
        raise NotImplementedError


class ProjectPlanRepository(ABC):
    @abstractmethod
    def list_ordered_phases(self, project_name: str) -> List[str]:
        raise NotImplementedError


class InMemoryProjectRepository(ProjectRepository):
    def __init__(self, projects: Optional[Mapping[str, Project]] = None):
        self._projects: Dict[str, Project] = dict(projects or {})

    def get(self, project_name: str) -> Project:
        return self._projects[project_name]

    def update_status(self, project_name: str, status: ProjectStatus) -> None:
        project = self.get(project_name)
        ensure_project_transition(project.status, status)
        project.status = status
        project.updated_at = utc_now()

    def set_current_phase(self, project_name: str, phase_name: Optional[str]) -> None:
        project = self.get(project_name)
        project.current_phase = phase_name
        project.updated_at = utc_now()

    def set_active_bootstrap_execution(self, project_name: str, stage: BootstrapResumeStage, job_id: str, started_at) -> None:
        project = self.get(project_name)
        project.active_bootstrap_stage = stage
        project.active_bootstrap_job_id = job_id
        project.active_bootstrap_started_at = started_at
        project.updated_at = utc_now()

    def clear_active_bootstrap_execution(self, project_name: str) -> None:
        project = self.get(project_name)
        project.active_bootstrap_stage = None
        project.active_bootstrap_job_id = None
        project.active_bootstrap_started_at = None
        project.updated_at = utc_now()

    def update_failure_context(
        self,
        project_name: str,
        stage: BootstrapResumeStage,
        job_id: Optional[str],
        result_path: Optional[str],
        reason: str,
    ) -> None:
        project = self.get(project_name)
        project.last_failed_bootstrap_stage = stage
        project.last_failed_job_id = job_id
        project.last_failed_result_path = result_path
        project.last_failed_reason = reason
        project.updated_at = utc_now()

    def clear_failure_context(self, project_name: str) -> None:
        project = self.get(project_name)
        project.last_failed_bootstrap_stage = None
        project.last_failed_job_id = None
        project.last_failed_result_path = None
        project.last_failed_reason = None
        project.updated_at = utc_now()


class InMemoryPhaseRepository(PhaseRepository):
    def __init__(self, phases: Optional[Mapping[Tuple[str, str], Phase]] = None):
        self._phases: Dict[Tuple[str, str], Phase] = dict(phases or {})

    def get(self, project_name: str, phase_name: str) -> Phase:
        return self._phases[(project_name, phase_name)]

    def update_status(self, project_name: str, phase_name: str, status: PhaseStatus) -> None:
        phase = self.get(project_name, phase_name)
        ensure_phase_transition(phase.status, status)
        phase.status = status
        phase.updated_at = utc_now()

    def attach_latest_approval(self, project_name: str, phase_name: str, approval_id: str) -> None:
        phase = self.get(project_name, phase_name)
        phase.latest_approval_id = approval_id
        phase.updated_at = utc_now()

    def set_latest_gate_ref(
        self,
        project_name: str,
        phase_name: str,
        snapshot_id: str,
        result_path: str,
        origin_stage: ReviewOriginStage,
    ) -> None:
        phase = self.get(project_name, phase_name)
        phase.latest_gate_snapshot_id = snapshot_id
        phase.latest_gate_result_path = result_path
        phase.latest_gate_origin_stage = origin_stage
        phase.updated_at = utc_now()

    def set_active_execution(self, project_name: str, phase_name: str, stage: PhaseResumeStage, job_id: str, started_at) -> None:
        phase = self.get(project_name, phase_name)
        phase.active_stage = stage
        phase.active_job_id = job_id
        phase.active_job_started_at = started_at
        phase.updated_at = utc_now()

    def clear_active_execution(self, project_name: str, phase_name: str) -> None:
        phase = self.get(project_name, phase_name)
        phase.active_stage = None
        phase.active_job_id = None
        phase.active_job_started_at = None
        phase.updated_at = utc_now()

    def update_failure_context(
        self,
        project_name: str,
        phase_name: str,
        stage: PhaseResumeStage,
        job_id: Optional[str],
        result_path: Optional[str],
        reason: str,
    ) -> None:
        phase = self.get(project_name, phase_name)
        phase.last_failed_stage = stage
        phase.last_failed_job_id = job_id
        phase.last_failed_result_path = result_path
        phase.last_failed_reason = reason
        phase.updated_at = utc_now()

    def clear_failure_context(self, project_name: str, phase_name: str) -> None:
        phase = self.get(project_name, phase_name)
        phase.last_failed_stage = None
        phase.last_failed_job_id = None
        phase.last_failed_result_path = None
        phase.last_failed_reason = None
        phase.updated_at = utc_now()


class InMemoryPhaseGateSnapshotRepository(PhaseGateSnapshotRepository):
    def __init__(self):
        self._snapshots: Dict[Tuple[str, str], List[PhaseGateSnapshot]] = {}

    def save(self, snapshot: PhaseGateSnapshot) -> None:
        key = (snapshot.project_name, snapshot.phase_name)
        self._snapshots.setdefault(key, []).append(snapshot)

    def get_latest(self, project_name: str, phase_name: str) -> PhaseGateSnapshot:
        return self._snapshots[(project_name, phase_name)][-1]


class InMemoryJobRepository(JobRepository):
    def __init__(self, jobs: Optional[Mapping[str, Job]] = None):
        self._jobs: Dict[str, Job] = dict(jobs or {})

    def get(self, job_id: str) -> Job:
        return self._jobs[job_id]

    def save(self, job: Job) -> None:
        self._jobs[job.job_id] = job

    def update_status(self, job_id: str, status: JobStatus, reason: Optional[str] = None) -> None:
        job = self.get(job_id)
        job.status = status
        job.updated_at = utc_now()
        if reason is not None:
            job.context_refs["status_reason"] = reason

    def mark_stale_failed(self, job_id: str, reason: str) -> None:
        self.update_status(job_id, JobStatus.FAILED, reason=reason)


class InMemoryApprovalRepository(ApprovalRepository):
    def __init__(self):
        self._approvals: Dict[str, Approval] = {}
        self._seq = count(1)

    def get(self, approval_id: str) -> Approval:
        return self._approvals[approval_id]

    def list_pending(self, project_name: str) -> List[Approval]:
        return [
            approval
            for approval in self._approvals.values()
            if approval.project_name == project_name and approval.status == ApprovalStatus.PENDING
        ]

    def create(
        self,
        project_name: str,
        phase_name: Optional[str],
        approval_type: ApprovalType,
        origin_stage: Optional[ReviewOriginStage],
        related_files: Optional[List[str]] = None,
    ) -> Approval:
        approval_id = f"approval-{next(self._seq):04d}"
        approval = Approval(
            approval_id=approval_id,
            project_name=project_name,
            phase_name=phase_name,
            approval_type=approval_type,
            status=ApprovalStatus.PENDING,
            origin_stage=origin_stage,
            related_files=list(related_files or []),
        )
        self._approvals[approval_id] = approval
        return approval

    def save(self, approval: Approval) -> None:
        approval.updated_at = utc_now()
        self._approvals[approval.approval_id] = approval

    def mark_approved(self, approval_id: str, actor: str) -> None:
        approval = self.get(approval_id)
        approval.status = ApprovalStatus.APPROVED
        approval.updated_at = utc_now()
        approval.related_files = list(approval.related_files)

    def mark_rejected(self, approval_id: str, actor: str) -> None:
        approval = self.get(approval_id)
        approval.status = ApprovalStatus.REJECTED
        approval.updated_at = utc_now()
        approval.related_files = list(approval.related_files)


class InMemoryProjectPlanRepository(ProjectPlanRepository):
    def __init__(self, phases_by_project: Optional[Mapping[str, Iterable[str]]] = None):
        self._plans: Dict[str, List[str]] = {
            project_name: list(phases)
            for project_name, phases in dict(phases_by_project or {}).items()
        }

    def list_ordered_phases(self, project_name: str) -> List[str]:
        return list(self._plans.get(project_name, []))
