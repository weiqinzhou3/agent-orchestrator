from __future__ import annotations

import pytest

from agent_orchestrator.application.project_service import ProjectService
from agent_orchestrator.domain.enums import ProjectStatus
from agent_orchestrator.domain.errors import InvalidProjectTransitionError
from agent_orchestrator.infra.db.repositories import InMemoryProjectPlanRepository, InMemoryProjectRepository


def test_on_phase_done_requires_phase_active(make_project) -> None:
    project_repo = InMemoryProjectRepository({"demo-project": make_project(ProjectStatus.BOOTSTRAP_READY)})
    plan_repo = InMemoryProjectPlanRepository({"demo-project": []})
    service = ProjectService(project_repo=project_repo, project_plan_repo=plan_repo)

    with pytest.raises(InvalidProjectTransitionError):
        service.on_phase_done("demo-project", "phase-01")


def test_advance_supports_bootstrap_ready_without_phase_plan(make_project) -> None:
    project_repo = InMemoryProjectRepository({"demo-project": make_project(ProjectStatus.BOOTSTRAP_READY)})
    plan_repo = InMemoryProjectPlanRepository({"demo-project": []})
    service = ProjectService(project_repo=project_repo, project_plan_repo=plan_repo)

    service.advance("demo-project")

    project = project_repo.get("demo-project")
    assert project.status == ProjectStatus.RELEASE_READY
    assert project.current_phase is None


def test_advance_moves_bootstrap_ready_project_to_first_phase(make_project) -> None:
    project_repo = InMemoryProjectRepository({"demo-project": make_project(ProjectStatus.BOOTSTRAP_READY)})
    plan_repo = InMemoryProjectPlanRepository({"demo-project": ["phase-01", "phase-02"]})
    service = ProjectService(project_repo=project_repo, project_plan_repo=plan_repo)

    service.advance("demo-project")

    project = project_repo.get("demo-project")
    assert project.status == ProjectStatus.PHASE_ACTIVE
    assert project.current_phase == "phase-01"


def test_advance_moves_phase_done_project_to_next_phase(make_project) -> None:
    project_repo = InMemoryProjectRepository({"demo-project": make_project(ProjectStatus.PHASE_DONE, current_phase="phase-01")})
    plan_repo = InMemoryProjectPlanRepository({"demo-project": ["phase-01", "phase-02"]})
    service = ProjectService(project_repo=project_repo, project_plan_repo=plan_repo)

    service.advance("demo-project")

    project = project_repo.get("demo-project")
    assert project.status == ProjectStatus.PHASE_ACTIVE
    assert project.current_phase == "phase-02"


def test_advance_moves_phase_done_project_to_release_ready_when_no_next_phase(make_project) -> None:
    project_repo = InMemoryProjectRepository({"demo-project": make_project(ProjectStatus.PHASE_DONE, current_phase="phase-02")})
    plan_repo = InMemoryProjectPlanRepository({"demo-project": ["phase-01", "phase-02"]})
    service = ProjectService(project_repo=project_repo, project_plan_repo=plan_repo)

    service.advance("demo-project")

    project = project_repo.get("demo-project")
    assert project.status == ProjectStatus.RELEASE_READY
    assert project.current_phase is None
