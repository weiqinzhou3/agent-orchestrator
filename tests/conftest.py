from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_orchestrator.domain.entities import Phase, Project
from agent_orchestrator.domain.enums import PhaseStatus, ProjectStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def make_project():
    def _make_project(
        status: ProjectStatus,
        *,
        project_name: str = "demo-project",
        current_phase: str | None = None,
    ) -> Project:
        now = utc_now()
        return Project(
            project_name=project_name,
            repo_root="/tmp/demo-project",
            status=status,
            current_phase=current_phase,
            active_bootstrap_job_id=None,
            active_bootstrap_stage=None,
            active_bootstrap_started_at=None,
            last_failed_bootstrap_stage=None,
            last_failed_job_id=None,
            last_failed_result_path=None,
            last_failed_reason=None,
            created_at=now,
            updated_at=now,
        )

    return _make_project


@pytest.fixture
def make_phase():
    def _make_phase(
        status: PhaseStatus,
        *,
        project_name: str = "demo-project",
        phase_name: str = "phase-01",
    ) -> Phase:
        now = utc_now()
        return Phase(
            project_name=project_name,
            phase_name=phase_name,
            contract_path="/tmp/demo-project/contracts/phase-01.md",
            status=status,
            latest_gate_snapshot_id=None,
            latest_gate_result_path=None,
            latest_gate_origin_stage=None,
            latest_approval_id=None,
            active_job_id=None,
            active_stage=None,
            active_job_started_at=None,
            last_failed_stage=None,
            last_failed_job_id=None,
            last_failed_result_path=None,
            last_failed_reason=None,
            created_at=now,
            updated_at=now,
        )

    return _make_phase
