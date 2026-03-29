# agent-orchestrator Interface Design v1.2

**Status:** Draft  
**Based on Spec:** `agent-orchestrator Spec v1.2`  
**Target Version:** v1.2

---

## 1. 文档目标

v1.2 在 v1.1 的基础上继续把“approval 工厂职责”和项目级边缘路径收口到能直接落代码的粒度。本版重点拍板 4 件事：

1. `ApprovalService.create_*()` 统一成为 approval 创建与阻塞态切换的唯一责任方，调用方不得再重复 `update_status()`；
2. `ApprovalService`、调用方、repository 接口重新对齐，恢复 `related_files` 等调用上下文；
3. `ProjectService.advance()` 补齐 `BOOTSTRAP_READY -> RELEASE_READY` 的空 phase plan 边缘路径；
4. `ProjectService.on_phase_done()` 与 repository `update_status()` 继续保持双重状态机校验。

---

## 2. 核心设计决策

### 2.1 run 命令统一采用“加锁 -> 协调 inflight -> 归一化失败入口 -> waterfall”

`run_bootstrap()` 与 `run_phase()` 都遵循同一个骨架：

1. 获取 scope 锁；
2. 读取当前状态；
3. 若当前为执行中态，则先做 inflight reconciliation；
4. 若当前为失败阻塞态，则先做 failed-entry normalization；
5. 再进入 waterfall 主链。

### 2.2 scope 互斥是强约束，不是“可选优化”

- `bootstrap run`：按 `project` 互斥；
- `phase run`：按 `(project, phase)` 互斥。

实现上必须至少提供一个 advisory lock 机制。  
若拿不到锁，必须抛 `AlreadyRunningError` 或等价错误，而不是继续乐观执行。

### 2.3 bootstrap 与 phase 的恢复模型保持对称

bootstrap 侧现在具备与 phase 侧对等的能力：

- 执行中状态可作为合法入口重入；
- stale / interrupted inflight job 可被识别并翻译成失败阻塞态；
- 恢复逻辑不直接执行业务 path，只做状态归一化。

### 2.4 close-path 不引入新 phase 状态，但必须有 active execution

`READY_TO_CLOSE` 仍保持为唯一 close-path 入口态。  
但以下 active stage 必须被持久化：

- `APPEND_BACKLOG`
- `CLOSE_PHASE`

这使得系统能够区分：

- `READY_TO_CLOSE` 且当前无人运行；
- `READY_TO_CLOSE` 但其实已有 close-path job 在跑；
- `READY_TO_CLOSE` 且上一次 close-path job 已 stale / interrupted。

### 2.5 close-path 的正确性依赖幂等语义

close-path 重入时允许从头再跑，但前提是：

- `append-backlog` 使用去重键 upsert backlog 项；
- `close-phase` 检测 close marker 或等价幂等标记。

---

## 3. 模块划分

```text
agent_orchestrator/
  cli/
    main.py
    project.py
    bootstrap.py
    phase.py
    approvals.py

  application/
    project_service.py
    bootstrap_service.py
    phase_service.py
    contract_service.py
    approval_service.py
    scheduler_service.py

  domain/
    enums.py
    entities.py
    state_machine.py
    recovery.py
    review_parser.py
    validators.py
    results.py
    errors.py

  infra/
    db/repositories.py
    fs/artifact_store.py
    fs/run_locks.py
    prompts/jinja_renderer.py
    workers/base.py
    execution/subprocess_runner.py
    config/loader.py
```

---

## 4. 枚举

```python
class ProjectStatus(str, Enum):
    INIT = "INIT"
    DESIGN_READY = "DESIGN_READY"
    BOOTSTRAP_RUNNING = "BOOTSTRAP_RUNNING"
    BOOTSTRAP_REVIEW_PENDING = "BOOTSTRAP_REVIEW_PENDING"
    BOOTSTRAP_READY = "BOOTSTRAP_READY"
    PHASE_ACTIVE = "PHASE_ACTIVE"
    PHASE_DONE = "PHASE_DONE"
    RELEASE_READY = "RELEASE_READY"
    CLOSED = "CLOSED"
    BLOCKED_ON_HUMAN = "BLOCKED_ON_HUMAN"
    BLOCKED_ON_OPEN_BLOCKERS = "BLOCKED_ON_OPEN_BLOCKERS"
    BLOCKED_ON_MISSING_ARTIFACT = "BLOCKED_ON_MISSING_ARTIFACT"
    BLOCKED_ON_WORKER_FAILURE = "BLOCKED_ON_WORKER_FAILURE"
```

```python
class PhaseStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    CONTRACT_VALIDATED = "CONTRACT_VALIDATED"
    CONTRACT_APPROVED = "CONTRACT_APPROVED"
    BUILDING = "BUILDING"
    REVIEW_PENDING = "REVIEW_PENDING"
    BLOCKER_FIXING = "BLOCKER_FIXING"
    RECHECK_PENDING = "RECHECK_PENDING"
    READY_TO_CLOSE = "READY_TO_CLOSE"
    DONE = "DONE"
    BLOCKED_ON_HUMAN = "BLOCKED_ON_HUMAN"
    BLOCKED_ON_OPEN_BLOCKERS = "BLOCKED_ON_OPEN_BLOCKERS"
    BLOCKED_ON_MISSING_ARTIFACT = "BLOCKED_ON_MISSING_ARTIFACT"
    BLOCKED_ON_WORKER_FAILURE = "BLOCKED_ON_WORKER_FAILURE"
```

```python
class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    DONE_WITH_CONCERNS = "DONE_WITH_CONCERNS"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
```

```python
class GateDecisionType(str, Enum):
    PASS = "PASS"
    CONDITIONAL_PASS = "CONDITIONAL_PASS"
    FAIL = "FAIL"
    INVALID_FORMAT = "INVALID_FORMAT"
```

```python
class ReviewOriginStage(str, Enum):
    PHASE_REVIEW = "PHASE_REVIEW"
    PHASE_RECHECK = "PHASE_RECHECK"
    BOOTSTRAP_REVIEW = "BOOTSTRAP_REVIEW"
```

```python
class BootstrapResumeStage(str, Enum):
    BOOTSTRAP_REPO = "BOOTSTRAP_REPO"
    BOOTSTRAP_REVIEW = "BOOTSTRAP_REVIEW"
```

```python
class PhaseResumeStage(str, Enum):
    BUILD = "BUILD"
    REVIEW = "REVIEW"
    FIX_BLOCKERS = "FIX_BLOCKERS"
    RECHECK = "RECHECK"
    APPEND_BACKLOG = "APPEND_BACKLOG"
    CLOSE_PHASE = "CLOSE_PHASE"
```

```python
class ApprovalType(str, Enum):
    CONTRACT_APPROVAL = "CONTRACT_APPROVAL"
    SCOPE_CHANGE = "SCOPE_CHANGE"
    CLOSE_PHASE_WITH_IMPORTANT_OPEN = "CLOSE_PHASE_WITH_IMPORTANT_OPEN"
    BOOTSTRAP_READY_WITH_IMPORTANT_OPEN = "BOOTSTRAP_READY_WITH_IMPORTANT_OPEN"
    RELEASE_READY_CONFIRM = "RELEASE_READY_CONFIRM"
```

```python
class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
```

---

## 5. 核心实体

```python
@dataclass
class GateDecision:
    decision: GateDecisionType
    blocker_count: int
    important_count: int
    later_count: int
    blockers: list[dict]
    important_items: list[dict]
    later_items: list[dict]
```

```python
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
    created_at: datetime
```

```python
@dataclass
class Project:
    project_name: str
    repo_root: str
    status: ProjectStatus
    current_phase: str | None

    active_bootstrap_job_id: str | None
    active_bootstrap_stage: BootstrapResumeStage | None
    active_bootstrap_started_at: datetime | None

    last_failed_bootstrap_stage: BootstrapResumeStage | None
    last_failed_job_id: str | None
    last_failed_result_path: str | None
    last_failed_reason: str | None

    created_at: datetime
    updated_at: datetime
```

```python
@dataclass
class Phase:
    project_name: str
    phase_name: str
    contract_path: str | None
    status: PhaseStatus

    latest_gate_snapshot_id: str | None
    latest_gate_result_path: str | None
    latest_gate_origin_stage: ReviewOriginStage | None
    latest_approval_id: str | None

    active_job_id: str | None
    active_stage: PhaseResumeStage | None
    active_job_started_at: datetime | None

    last_failed_stage: PhaseResumeStage | None
    last_failed_job_id: str | None
    last_failed_result_path: str | None
    last_failed_reason: str | None

    created_at: datetime
    updated_at: datetime
```

```python
@dataclass
class Job:
    job_id: str
    project_name: str
    phase_name: str | None
    job_type: str
    status: JobStatus
    expected_outputs: list[str]
    parent_job_id: str | None
    review_origin_stage: ReviewOriginStage | None
    context_refs: dict[str, str]
    result_path: str | None
    last_heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime
```

```python
@dataclass
class Approval:
    approval_id: str
    project_name: str
    phase_name: str | None
    approval_type: ApprovalType
    status: ApprovalStatus
    origin_stage: ReviewOriginStage | None
    related_files: list[str]
    created_at: datetime
    updated_at: datetime
```

---

## 6. 结果对象

```python
@dataclass
class JobCompletion:
    status: JobStatus
    reason: str
    concern_codes: list[str]
```

```python
@dataclass
class JobExecutionSummary:
    job_id: str
    completion: JobCompletion
    gate_decision: GateDecision | None
    artifact_validation: ArtifactValidationResult
    review_origin_stage: ReviewOriginStage | None
    result_path: str | None
```

```python
@dataclass
class BootstrapRunResult:
    project_name: str
    final_status: ProjectStatus
    executed_job_ids: list[str]
    pending_approval_id: str | None
    message: str
```

```python
@dataclass
class PhaseRunResult:
    project_name: str
    phase_name: str
    final_status: PhaseStatus
    executed_job_ids: list[str]
    pending_approval_id: str | None
    message: str
```

```python
@dataclass
class ApprovalOutcome:
    approval_id: str
    approval_type: ApprovalType
    new_project_status: ProjectStatus | None
    new_phase_status: PhaseStatus | None
    resume_command: str | None
```

---

## 7. Repository 与 Store 接口

> `ProjectRepository.update_status()` 与 `PhaseRepository.update_status()` 的实现必须强制执行状态机白名单校验；application service 侧的 guard 仍然保留，作为防御性双保险。

```python
class ProjectRepository:
    def get(self, project_name: str) -> Project: ...
    def update_status(self, project_name: str, status: ProjectStatus) -> None: ...
    def set_current_phase(self, project_name: str, phase_name: str | None) -> None: ...

    def set_active_bootstrap_execution(
        self,
        project_name: str,
        stage: BootstrapResumeStage,
        job_id: str,
        started_at: datetime,
    ) -> None: ...

    def clear_active_bootstrap_execution(self, project_name: str) -> None: ...

    def update_failure_context(
        self,
        project_name: str,
        stage: BootstrapResumeStage,
        job_id: str | None,
        result_path: str | None,
        reason: str,
    ) -> None: ...

    def clear_failure_context(self, project_name: str) -> None: ...
```

```python
class PhaseRepository:
    def get(self, project_name: str, phase_name: str) -> Phase: ...
    def update_status(self, project_name: str, phase_name: str, status: PhaseStatus) -> None: ...
    def attach_latest_approval(self, project_name: str, phase_name: str, approval_id: str) -> None: ...

    def set_latest_gate_ref(
        self,
        project_name: str,
        phase_name: str,
        snapshot_id: str,
        result_path: str,
        origin_stage: ReviewOriginStage,
    ) -> None: ...

    def set_active_execution(
        self,
        project_name: str,
        phase_name: str,
        stage: PhaseResumeStage,
        job_id: str,
        started_at: datetime,
    ) -> None: ...

    def clear_active_execution(self, project_name: str, phase_name: str) -> None: ...

    def update_failure_context(
        self,
        project_name: str,
        phase_name: str,
        stage: PhaseResumeStage,
        job_id: str | None,
        result_path: str | None,
        reason: str,
    ) -> None: ...

    def clear_failure_context(self, project_name: str, phase_name: str) -> None: ...
```

```python
class PhaseGateSnapshotRepository:
    def save(self, snapshot: PhaseGateSnapshot) -> None: ...
    def get_latest(self, project_name: str, phase_name: str) -> PhaseGateSnapshot: ...
```

```python
class JobRepository:
    def get(self, job_id: str) -> Job: ...
    def save(self, job: Job) -> None: ...
    def update_status(self, job_id: str, status: JobStatus, reason: str | None = None) -> None: ...
    def mark_stale_failed(self, job_id: str, reason: str) -> None: ...
```

```python
class ApprovalRepository:
    def get(self, approval_id: str) -> Approval: ...
    def list_pending(self, project_name: str) -> list[Approval]: ...
    def create(
        self,
        project_name: str,
        phase_name: str | None,
        approval_type: ApprovalType,
        origin_stage: ReviewOriginStage | None,
        related_files: list[str] | None = None,
    ) -> Approval: ...
    def save(self, approval: Approval) -> None: ...
    def mark_approved(self, approval_id: str, actor: str) -> None: ...
    def mark_rejected(self, approval_id: str, actor: str) -> None: ...
```

```python
class ProjectPlanRepository:
    def list_ordered_phases(self, project_name: str) -> list[str]: ...
```

```python
class RunLockRepository:
    @contextmanager
    def acquire_project_lock(self, project_name: str): ...
    @contextmanager
    def acquire_phase_lock(self, project_name: str, phase_name: str): ...
```

```python
class ArtifactStore:
    def read_text(self, path: str) -> str: ...
    def read_json(self, path: str) -> dict: ...
    def exists(self, path: str) -> bool: ...
```

---

## 8. Application Service 接口

```python
class BootstrapService:
    def run_bootstrap(self, project_name: str, force_full: bool = False) -> BootstrapRunResult: ...
```

```python
class PhaseService:
    def run_phase(self, project_name: str, phase_name: str) -> PhaseRunResult: ...
```

```python
class ApprovalService:
    def create_contract_approval(
        self,
        project_name: str,
        phase_name: str,
        approval_type: ApprovalType,
        related_files: list[str] | None = None,
        origin_stage: ReviewOriginStage | None = None,
    ) -> Approval: ...

    def create_close_phase_with_important_open(
        self,
        project_name: str,
        phase_name: str,
        origin_stage: ReviewOriginStage,
        related_files: list[str] | None = None,
    ) -> Approval: ...

    def create_bootstrap_ready_with_important_open(
        self,
        project_name: str,
        origin_stage: ReviewOriginStage = ReviewOriginStage.BOOTSTRAP_REVIEW,
        related_files: list[str] | None = None,
    ) -> Approval: ...

    def create_release_ready_confirm(
        self,
        project_name: str,
        related_files: list[str] | None = None,
    ) -> Approval: ...

    def approve(self, approval_id: str, actor: str) -> ApprovalOutcome: ...
    def reject(self, approval_id: str, actor: str) -> ApprovalOutcome: ...
```

```python
class ProjectService:
    def on_phase_done(self, project_name: str, phase_name: str) -> None: ...
    def advance(self, project_name: str) -> None: ...
    def request_close(self, project_name: str) -> str: ...
```

```python
class ContractService:
    def validate(self, project_name: str, phase_name: str) -> ContractValidationResult: ...
    def resolve_approval_type(self, project_name: str, phase_name: str, contract_path: str) -> ApprovalType | None: ...
```

```python
class SchedulerService:
    def enqueue(self, job: Job) -> None: ...
    def execute_job(self, job_id: str) -> JobExecutionSummary: ...
    def is_job_lease_fresh(self, job_id: str) -> bool: ...
```

---

## 9. `run_bootstrap()` 设计

### 9.1 允许入口

```python
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
```

### 9.2 执行中入口协调

```python
def _stage_from_bootstrap_status(status: ProjectStatus) -> BootstrapResumeStage:
    if status == ProjectStatus.BOOTSTRAP_RUNNING:
        return BootstrapResumeStage.BOOTSTRAP_REPO
    if status == ProjectStatus.BOOTSTRAP_REVIEW_PENDING:
        return BootstrapResumeStage.BOOTSTRAP_REVIEW
    raise InvalidProjectTransitionError(...)
```

```python
def _reconcile_inflight_bootstrap_entry(project_name: str) -> None:
    project = project_repo.get(project_name)
    if project.status not in EXECUTING_BOOTSTRAP_STATES:
        return

    failed_stage = _stage_from_bootstrap_status(project.status)

    if project.active_bootstrap_job_id is None:
        project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_WORKER_FAILURE)
        project_repo.update_failure_context(
            project_name,
            failed_stage,
            None,
            None,
            f"inflight {project.status.value} without active job; treating as interrupted bootstrap",
        )
        project_repo.clear_active_bootstrap_execution(project_name)
        return

    job = job_repo.get(project.active_bootstrap_job_id)

    if job.status == JobStatus.RUNNING and scheduler.is_job_lease_fresh(job.job_id):
        raise BootstrapAlreadyRunningError(...)

    if job.status == JobStatus.RUNNING:
        job_repo.mark_stale_failed(job.job_id, "stale inflight bootstrap job detected during resume")

    blocked_status = (
        ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT
        if failed_stage == BootstrapResumeStage.BOOTSTRAP_REVIEW and not bool(job.result_path)
        else ProjectStatus.BLOCKED_ON_WORKER_FAILURE
    )
    project_repo.update_status(project_name, blocked_status)
    project_repo.update_failure_context(
        project_name,
        failed_stage,
        job.job_id,
        job.result_path,
        f"inflight {project.status.value} interrupted or stale; last job status={job.status.value}",
    )
    project_repo.clear_active_bootstrap_execution(project_name)
```

### 9.3 失败入口归一化

```python
def _normalize_failed_bootstrap_entry(project_name: str, force_full: bool) -> None:
    project = project_repo.get(project_name)

    if project.status == ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS:
        target = ProjectStatus.BOOTSTRAP_RUNNING if force_full else ProjectStatus.BOOTSTRAP_REVIEW_PENDING
        project_repo.update_status(project_name, target)
        return

    if project.status not in FAILED_BLOCKING_BOOTSTRAP_STATES:
        return

    if force_full:
        project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_RUNNING)
        return

    if project.last_failed_bootstrap_stage is None:
        raise MissingResumeContextError("missing bootstrap failure context")

    if project.last_failed_bootstrap_stage == BootstrapResumeStage.BOOTSTRAP_REPO:
        project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_RUNNING)
        return

    if project.last_failed_bootstrap_stage == BootstrapResumeStage.BOOTSTRAP_REVIEW:
        project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_REVIEW_PENDING)
        return

    raise MissingResumeContextError(...)
```

### 9.4 bootstrap waterfall 伪代码

```python
def run_bootstrap(project_name: str, force_full: bool = False) -> BootstrapRunResult:
    with run_lock_repo.acquire_project_lock(project_name):
        project = project_repo.get(project_name)
        if project.status not in ALLOWED_BOOTSTRAP_ENTRY:
            raise InvalidProjectTransitionError(...)

        executed: list[str] = []

        if project.status in EXECUTING_BOOTSTRAP_STATES:
            _reconcile_inflight_bootstrap_entry(project_name)
            project = project_repo.get(project_name)

        if project.status in FAILED_BLOCKING_BOOTSTRAP_STATES or project.status == ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS:
            _normalize_failed_bootstrap_entry(project_name, force_full)
            project = project_repo.get(project_name)

        if project.status == ProjectStatus.DESIGN_READY:
            project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_RUNNING)
            project = project_repo.get(project_name)

        if project.status == ProjectStatus.BOOTSTRAP_RUNNING:
            _run_bootstrap_repo_path(project_name, executed)
            project = project_repo.get(project_name)

        if project.status == ProjectStatus.BOOTSTRAP_REVIEW_PENDING:
            _run_bootstrap_review_path(project_name, executed)
            project = project_repo.get(project_name)

        return BootstrapRunResult(project_name, project.status, executed, None, "bootstrap run completed")
```

### 9.5 bootstrap repo / review path

```python
def _run_bootstrap_repo_path(project_name: str, executed: list[str]) -> None:
    bootstrap_job = job_factory.create_bootstrap_repo(...)
    scheduler.enqueue(bootstrap_job)

    project_repo.set_active_bootstrap_execution(
        project_name,
        BootstrapResumeStage.BOOTSTRAP_REPO,
        bootstrap_job.job_id,
        clock.now(),
    )
    bootstrap_exec = scheduler.execute_job(bootstrap_job.job_id)
    executed.append(bootstrap_job.job_id)
    project_repo.clear_active_bootstrap_execution(project_name)

    if bootstrap_exec.completion.status != JobStatus.SUCCEEDED:
        project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_WORKER_FAILURE)
        project_repo.update_failure_context(
            project_name,
            BootstrapResumeStage.BOOTSTRAP_REPO,
            bootstrap_job.job_id,
            bootstrap_exec.result_path,
            "bootstrap-repo failed",
        )
        return

    project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_REVIEW_PENDING)
```

```python
def _run_bootstrap_review_path(project_name: str, executed: list[str]) -> None:
    review_job = job_factory.create_review_bootstrap(...)
    scheduler.enqueue(review_job)

    project_repo.set_active_bootstrap_execution(
        project_name,
        BootstrapResumeStage.BOOTSTRAP_REVIEW,
        review_job.job_id,
        clock.now(),
    )
    review_exec = scheduler.execute_job(review_job.job_id)
    executed.append(review_job.job_id)
    project_repo.clear_active_bootstrap_execution(project_name)

    gate = review_exec.gate_decision
    if gate is None:
        blocked_status = (
            ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT
            if not review_exec.artifact_validation.passed
            else ProjectStatus.BLOCKED_ON_WORKER_FAILURE
        )
        project_repo.update_status(project_name, blocked_status)
        project_repo.update_failure_context(
            project_name,
            BootstrapResumeStage.BOOTSTRAP_REVIEW,
            review_exec.job_id,
            review_exec.result_path,
            "bootstrap review did not produce a valid gate decision",
        )
        return

    project_repo.clear_failure_context(project_name)

    if gate.decision == GateDecisionType.INVALID_FORMAT:
        project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT)
        project_repo.update_failure_context(
            project_name,
            BootstrapResumeStage.BOOTSTRAP_REVIEW,
            review_exec.job_id,
            review_exec.result_path,
            "bootstrap review invalid format",
        )
        return

    if gate.decision == GateDecisionType.FAIL:
        project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS)
        return

    if gate.decision == GateDecisionType.CONDITIONAL_PASS:
        approval_service.create_bootstrap_ready_with_important_open(
            project_name,
            origin_stage=ReviewOriginStage.BOOTSTRAP_REVIEW,
            related_files=[review_exec.result_path] if review_exec.result_path else None,
        )
        return

    project_repo.update_status(project_name, ProjectStatus.BOOTSTRAP_READY)
```

---

## 10. `run_phase()` 总体设计

### 10.1 允许入口

```python
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
```

### 10.2 高层伪代码

```python
def run_phase(project_name: str, phase_name: str) -> PhaseRunResult:
    with run_lock_repo.acquire_phase_lock(project_name, phase_name):
        phase = phase_repo.get(project_name, phase_name)
        if phase.status not in ALLOWED_PHASE_ENTRY:
            raise InvalidPhaseTransitionError(...)

        executed: list[str] = []

        if phase.status in EXECUTING_PHASE_STATES:
            _reconcile_inflight_phase_entry(project_name, phase_name)
            phase = phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.READY_TO_CLOSE and phase.active_stage in {
            PhaseResumeStage.APPEND_BACKLOG,
            PhaseResumeStage.CLOSE_PHASE,
        }:
            _reconcile_ready_to_close_active_entry(project_name, phase_name)
            phase = phase_repo.get(project_name, phase_name)

        if phase.status in FAILED_BLOCKING_PHASE_STATES:
            _normalize_failed_phase_entry(project_name, phase_name)
            phase = phase_repo.get(project_name, phase_name)

        # 这是有意的 waterfall-if；不要改成 elif。
        if phase.status in {PhaseStatus.NOT_STARTED, PhaseStatus.CONTRACT_VALIDATED}:
            _enter_contract_path(project_name, phase_name, executed)
            phase = phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.CONTRACT_APPROVED:
            _run_build_review_path(project_name, phase_name, executed)
            phase = phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.REVIEW_PENDING:
            _run_review_only_path(project_name, phase_name, executed)
            phase = phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS:
            _run_fix_recheck_path(project_name, phase_name, executed)
            phase = phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.RECHECK_PENDING:
            _run_recheck_only_path(project_name, phase_name, executed)
            phase = phase_repo.get(project_name, phase_name)

        if phase.status == PhaseStatus.READY_TO_CLOSE:
            _run_close_path(project_name, phase_name, executed)
            phase = phase_repo.get(project_name, phase_name)

        return PhaseRunResult(project_name, phase_name, phase.status, executed, phase.latest_approval_id, "phase run completed")
```

### 10.3 执行中入口协调 + 失败归一化

```python
def _resume_stage_from_executing_status(status: PhaseStatus) -> PhaseResumeStage:
    if status == PhaseStatus.BUILDING:
        return PhaseResumeStage.BUILD
    if status == PhaseStatus.REVIEW_PENDING:
        return PhaseResumeStage.REVIEW
    if status == PhaseStatus.BLOCKER_FIXING:
        return PhaseResumeStage.FIX_BLOCKERS
    if status == PhaseStatus.RECHECK_PENDING:
        return PhaseResumeStage.RECHECK
    raise InvalidPhaseTransitionError(...)
```

```python
def _reconcile_inflight_phase_entry(project_name: str, phase_name: str) -> None:
    phase = phase_repo.get(project_name, phase_name)
    if phase.status not in EXECUTING_PHASE_STATES:
        return

    failed_stage = _resume_stage_from_executing_status(phase.status)

    if phase.active_job_id is None:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
        phase_repo.update_failure_context(
            project_name,
            phase_name,
            failed_stage,
            None,
            None,
            f"inflight {phase.status.value} without active job; treating as interrupted execution",
        )
        phase_repo.clear_active_execution(project_name, phase_name)
        return

    job = job_repo.get(phase.active_job_id)

    if job.status == JobStatus.RUNNING and scheduler.is_job_lease_fresh(job.job_id):
        raise PhaseAlreadyRunningError(...)

    if job.status == JobStatus.RUNNING:
        job_repo.mark_stale_failed(job.job_id, "stale inflight phase job detected during resume")

    blocked_status = (
        PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT
        if failed_stage in {PhaseResumeStage.REVIEW, PhaseResumeStage.RECHECK} and not bool(job.result_path)
        else PhaseStatus.BLOCKED_ON_WORKER_FAILURE
    )
    phase_repo.update_status(project_name, phase_name, blocked_status)
    phase_repo.update_failure_context(
        project_name,
        phase_name,
        failed_stage,
        job.job_id,
        job.result_path,
        f"inflight {phase.status.value} interrupted or stale; last job status={job.status.value}",
    )
    phase_repo.clear_active_execution(project_name, phase_name)
```

```python
def _reconcile_ready_to_close_active_entry(project_name: str, phase_name: str) -> None:
    phase = phase_repo.get(project_name, phase_name)
    if phase.status != PhaseStatus.READY_TO_CLOSE:
        return
    if phase.active_stage not in {PhaseResumeStage.APPEND_BACKLOG, PhaseResumeStage.CLOSE_PHASE}:
        return

    if phase.active_job_id is None:
        phase_repo.clear_active_execution(project_name, phase_name)
        return

    job = job_repo.get(phase.active_job_id)

    if job.status == JobStatus.RUNNING and scheduler.is_job_lease_fresh(job.job_id):
        raise PhaseAlreadyRunningError(...)

    if job.status == JobStatus.RUNNING:
        job_repo.mark_stale_failed(job.job_id, "stale close-path job detected during resume")
        phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
        phase_repo.update_failure_context(
            project_name,
            phase_name,
            phase.active_stage,
            job.job_id,
            job.result_path,
            f"close-path active stage {phase.active_stage.value} interrupted or stale",
        )
        phase_repo.clear_active_execution(project_name, phase_name)
        return

    # job 已经结束但 orchestrator 可能在清理或状态推进前崩溃；
    # 这里直接清理 active execution，然后允许 close-path 按幂等方式重跑。
    phase_repo.clear_active_execution(project_name, phase_name)
```

```python
def _normalize_failed_phase_entry(project_name: str, phase_name: str) -> None:
    phase = phase_repo.get(project_name, phase_name)
    if phase.last_failed_stage is None:
        raise MissingResumeContextError("missing phase failure context")

    if phase.last_failed_stage == PhaseResumeStage.BUILD:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.CONTRACT_APPROVED)
        return

    if phase.last_failed_stage == PhaseResumeStage.REVIEW:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.REVIEW_PENDING)
        return

    if phase.last_failed_stage == PhaseResumeStage.FIX_BLOCKERS:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS)
        return

    if phase.last_failed_stage == PhaseResumeStage.RECHECK:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.RECHECK_PENDING)
        return

    if phase.last_failed_stage in {PhaseResumeStage.APPEND_BACKLOG, PhaseResumeStage.CLOSE_PHASE}:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.READY_TO_CLOSE)
        return

    raise MissingResumeContextError(...)
```

### 10.4 合同路径

```python
def _enter_contract_path(project_name: str, phase_name: str, executed: list[str]) -> None:
    contract_result = contract_service.validate(project_name, phase_name)
    if not contract_result.valid:
        raise ContractInvalidError(...)

    phase_repo.update_status(project_name, phase_name, PhaseStatus.CONTRACT_VALIDATED)

    approval_type = contract_service.resolve_approval_type(
        project_name,
        phase_name,
        contract_result.contract_path,
    )
    if approval_type is None:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.CONTRACT_APPROVED)
        return

    approval_service.create_contract_approval(
        project_name,
        phase_name,
        approval_type,
        related_files=[contract_result.contract_path],
    )
```

### 10.5 build + review 路径

```python
def _run_build_review_path(project_name: str, phase_name: str, executed: list[str]) -> None:
    build_job = job_factory.create_phase_build(...)
    scheduler.enqueue(build_job)

    phase_repo.update_status(project_name, phase_name, PhaseStatus.BUILDING)
    phase_repo.set_active_execution(project_name, phase_name, PhaseResumeStage.BUILD, build_job.job_id, clock.now())

    build_exec = scheduler.execute_job(build_job.job_id)
    executed.append(build_job.job_id)
    phase_repo.clear_active_execution(project_name, phase_name)

    if build_exec.completion.status != JobStatus.SUCCEEDED:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
        phase_repo.update_failure_context(
            project_name,
            phase_name,
            PhaseResumeStage.BUILD,
            build_job.job_id,
            build_exec.result_path,
            "build failed",
        )
        return

    phase_repo.update_status(project_name, phase_name, PhaseStatus.REVIEW_PENDING)
    _run_review_only_path(project_name, phase_name, executed)
```

### 10.6 review-only / recheck-only 失败收口

```python
def _resume_stage_from_origin(origin_stage: ReviewOriginStage) -> PhaseResumeStage:
    if origin_stage == ReviewOriginStage.PHASE_REVIEW:
        return PhaseResumeStage.REVIEW
    if origin_stage == ReviewOriginStage.PHASE_RECHECK:
        return PhaseResumeStage.RECHECK
    raise UnsupportedOriginStageError(...)
```

```python
def _block_review_like_failure(
    project_name: str,
    phase_name: str,
    exec_summary: JobExecutionSummary,
    origin_stage: ReviewOriginStage,
    reason: str,
) -> bool:
    if exec_summary.gate_decision is not None:
        return False

    blocked_status = (
        PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT
        if not exec_summary.artifact_validation.passed
        else PhaseStatus.BLOCKED_ON_WORKER_FAILURE
    )
    phase_repo.update_status(project_name, phase_name, blocked_status)
    phase_repo.update_failure_context(
        project_name,
        phase_name,
        _resume_stage_from_origin(origin_stage),
        exec_summary.job_id,
        exec_summary.result_path,
        reason,
    )
    return True
```

```python
def _run_review_only_path(project_name: str, phase_name: str, executed: list[str]) -> None:
    review_job = job_factory.create_phase_review(review_origin_stage=ReviewOriginStage.PHASE_REVIEW, ...)
    scheduler.enqueue(review_job)

    phase_repo.set_active_execution(project_name, phase_name, PhaseResumeStage.REVIEW, review_job.job_id, clock.now())
    review_exec = scheduler.execute_job(review_job.job_id)
    executed.append(review_job.job_id)
    phase_repo.clear_active_execution(project_name, phase_name)

    if _block_review_like_failure(
        project_name,
        phase_name,
        review_exec,
        ReviewOriginStage.PHASE_REVIEW,
        "review worker failed before producing a gate",
    ):
        return

    final_exec = _repair_invalid_review_once_if_needed(review_exec, executed)
    if _block_review_like_failure(
        project_name,
        phase_name,
        final_exec,
        ReviewOriginStage.PHASE_REVIEW,
        "review format-repair failed before producing a gate",
    ):
        return

    _route_gate_after_review(project_name, phase_name, final_exec, ReviewOriginStage.PHASE_REVIEW)
```

```python
def _run_recheck_only_path(project_name: str, phase_name: str, executed: list[str]) -> None:
    snapshot = gate_snapshot_repo.get_latest(project_name, phase_name)
    recheck_job = job_factory.create_phase_recheck(
        review_origin_stage=ReviewOriginStage.PHASE_RECHECK,
        source_review_result_path=snapshot.result_path,
        ...
    )
    scheduler.enqueue(recheck_job)

    phase_repo.set_active_execution(project_name, phase_name, PhaseResumeStage.RECHECK, recheck_job.job_id, clock.now())
    recheck_exec = scheduler.execute_job(recheck_job.job_id)
    executed.append(recheck_job.job_id)
    phase_repo.clear_active_execution(project_name, phase_name)

    if _block_review_like_failure(
        project_name,
        phase_name,
        recheck_exec,
        ReviewOriginStage.PHASE_RECHECK,
        "recheck worker failed before producing a gate",
    ):
        return

    final_exec = _repair_invalid_review_once_if_needed(recheck_exec, executed)
    if _block_review_like_failure(
        project_name,
        phase_name,
        final_exec,
        ReviewOriginStage.PHASE_RECHECK,
        "recheck format-repair failed before producing a gate",
    ):
        return

    _route_gate_after_review(project_name, phase_name, final_exec, ReviewOriginStage.PHASE_RECHECK)
```

### 10.7 review / recheck 路由

```python
def _route_gate_after_review(
    project_name: str,
    phase_name: str,
    final_exec: JobExecutionSummary,
    origin_stage: ReviewOriginStage,
) -> None:
    gate = final_exec.gate_decision
    if gate is None:
        raise MissingGateDecisionError(...)

    snapshot = PhaseGateSnapshot(
        snapshot_id=id_gen.new(),
        project_name=project_name,
        phase_name=phase_name,
        decision=gate.decision,
        source_job_id=final_exec.job_id,
        origin_stage=origin_stage,
        result_path=final_exec.result_path,
        blocker_count=gate.blocker_count,
        important_count=gate.important_count,
        later_count=gate.later_count,
        created_at=clock.now(),
    )
    gate_snapshot_repo.save(snapshot)
    phase_repo.set_latest_gate_ref(project_name, phase_name, snapshot.snapshot_id, final_exec.result_path, origin_stage)
    phase_repo.clear_failure_context(project_name, phase_name)

    if gate.decision == GateDecisionType.INVALID_FORMAT:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT)
        phase_repo.update_failure_context(
            project_name,
            phase_name,
            _resume_stage_from_origin(origin_stage),
            final_exec.job_id,
            final_exec.result_path,
            f"{origin_stage.value} invalid format",
        )
        return

    if gate.decision == GateDecisionType.FAIL:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS)
        return

    if gate.decision == GateDecisionType.CONDITIONAL_PASS:
        approval_service.create_close_phase_with_important_open(
            project_name,
            phase_name,
            origin_stage=origin_stage,
            related_files=[final_exec.result_path] if final_exec.result_path else None,
        )
        return

    phase_repo.update_status(project_name, phase_name, PhaseStatus.READY_TO_CLOSE)
```

### 10.8 fix + recheck 路径

```python
def snapshot_blockers_or_important(
    snapshot: PhaseGateSnapshot,
    review_payload: dict,
    approval: Approval | None,
) -> list[dict]:
    if snapshot.decision == GateDecisionType.FAIL:
        return [
            {
                "severity": "blocker",
                "source": "blocker",
                "must_fix": True,
                **item,
            }
            for item in review_payload.get("blockers", [])
        ]

    if snapshot.decision == GateDecisionType.CONDITIONAL_PASS:
        if approval is None:
            raise InvalidRecheckSourceError("conditional pass snapshot requires an approval record")
        if approval.approval_type != ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN:
            raise InvalidRecheckSourceError("conditional pass snapshot must come from close-phase approval")
        if approval.status != ApprovalStatus.REJECTED:
            raise InvalidRecheckSourceError("conditional pass snapshot can enter fix path only after reject")
        return [
            {
                "severity": "important",
                "source": "important_promoted_to_must_fix",
                "must_fix": True,
                **item,
            }
            for item in review_payload.get("important_items", [])
        ]

    raise InvalidRecheckSourceError("fix path requires FAIL or rejected CONDITIONAL_PASS snapshot")
```

```python
def _run_fix_recheck_path(project_name: str, phase_name: str, executed: list[str]) -> None:
    phase = phase_repo.get(project_name, phase_name)
    snapshot = gate_snapshot_repo.get_latest(project_name, phase_name)
    review_payload = artifact_store.read_json(snapshot.result_path)
    approval = approval_repo.get(phase.latest_approval_id) if phase.latest_approval_id else None
    rework_items = snapshot_blockers_or_important(snapshot, review_payload, approval)

    fix_job = job_factory.create_phase_fix_blockers(
        source_review_result_path=snapshot.result_path,
        source_origin_stage=snapshot.origin_stage,
        rework_items=rework_items,
        ...
    )
    scheduler.enqueue(fix_job)

    phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKER_FIXING)
    phase_repo.set_active_execution(project_name, phase_name, PhaseResumeStage.FIX_BLOCKERS, fix_job.job_id, clock.now())

    fix_exec = scheduler.execute_job(fix_job.job_id)
    executed.append(fix_job.job_id)
    phase_repo.clear_active_execution(project_name, phase_name)

    if fix_exec.completion.status != JobStatus.SUCCEEDED:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
        phase_repo.update_failure_context(
            project_name,
            phase_name,
            PhaseResumeStage.FIX_BLOCKERS,
            fix_job.job_id,
            fix_exec.result_path,
            "fix blockers failed",
        )
        return

    phase_repo.update_status(project_name, phase_name, PhaseStatus.RECHECK_PENDING)
    _run_recheck_only_path(project_name, phase_name, executed)
```

### 10.9 close-path

```python
def _load_latest_gate_snapshot(project_name: str, phase_name: str) -> PhaseGateSnapshot:
    return gate_snapshot_repo.get_latest(project_name, phase_name)
```

```python
def _append_backlog_dedupe_key(snapshot: PhaseGateSnapshot, item: dict) -> str:
    return f"{snapshot.project_name}:{snapshot.phase_name}:{snapshot.snapshot_id}:{fingerprint(item)}"
```

```python
def _run_close_path(project_name: str, phase_name: str, executed: list[str]) -> None:
    snapshot = _load_latest_gate_snapshot(project_name, phase_name)

    if config.rules.auto_append_later_to_backlog and snapshot.later_count > 0:
        backlog_job = job_factory.create_append_backlog(
            source_review_result_path=snapshot.result_path,
            dedupe_scope=f"{snapshot.project_name}:{snapshot.phase_name}:{snapshot.snapshot_id}",
            ...
        )
        scheduler.enqueue(backlog_job)

        phase_repo.set_active_execution(project_name, phase_name, PhaseResumeStage.APPEND_BACKLOG, backlog_job.job_id, clock.now())
        backlog_exec = scheduler.execute_job(backlog_job.job_id)
        executed.append(backlog_job.job_id)
        phase_repo.clear_active_execution(project_name, phase_name)

        if backlog_exec.completion.status != JobStatus.SUCCEEDED:
            phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
            phase_repo.update_failure_context(
                project_name,
                phase_name,
                PhaseResumeStage.APPEND_BACKLOG,
                backlog_job.job_id,
                backlog_exec.result_path,
                "append backlog failed",
            )
            return

    close_job = job_factory.create_close_phase(
        close_marker=f"{project_name}:{phase_name}",
        ...
    )
    scheduler.enqueue(close_job)

    phase_repo.set_active_execution(project_name, phase_name, PhaseResumeStage.CLOSE_PHASE, close_job.job_id, clock.now())
    close_exec = scheduler.execute_job(close_job.job_id)
    executed.append(close_job.job_id)
    phase_repo.clear_active_execution(project_name, phase_name)

    if close_exec.completion.status != JobStatus.SUCCEEDED:
        phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_WORKER_FAILURE)
        phase_repo.update_failure_context(
            project_name,
            phase_name,
            PhaseResumeStage.CLOSE_PHASE,
            close_job.job_id,
            close_exec.result_path,
            "close phase failed",
        )
        return

    phase_repo.clear_failure_context(project_name, phase_name)
    phase_repo.update_status(project_name, phase_name, PhaseStatus.DONE)
    project_service.on_phase_done(project_name, phase_name)
```

---

## 11. `INVALID_FORMAT` 一次性修复

```python
def _repair_invalid_review_once_if_needed(current_exec: JobExecutionSummary, executed: list[str]) -> JobExecutionSummary:
    gate = current_exec.gate_decision
    if gate is None:
        raise MissingGateDecisionError(...)

    if gate.decision != GateDecisionType.INVALID_FORMAT:
        return current_exec

    format_job = job_factory.create_phase_recheck_format(
        parent_job_id=current_exec.job_id,
        review_origin_stage=current_exec.review_origin_stage,
        source_review_result_path=current_exec.result_path,
        ...
    )
    scheduler.enqueue(format_job)
    format_exec = scheduler.execute_job(format_job.job_id)
    executed.append(format_job.job_id)
    # 若 format job 自身失败，调用方必须把“无 gate 结果”收口成阻塞态，不能直接进入 gate router。
    return format_exec
```

---

## 12. 单 job 生命周期

```python
def complete_job(exec_result, artifact_result, gate_decision=None) -> JobCompletion:
    if exec_result.exit_code != 0:
        return JobCompletion(JobStatus.FAILED, "worker exit code != 0", [])

    if not artifact_result.passed:
        return JobCompletion(JobStatus.FAILED, "required outputs missing or invalid", [])

    if gate_decision is not None and gate_decision.decision == GateDecisionType.INVALID_FORMAT:
        return JobCompletion(JobStatus.FAILED, "review invalid format", [])

    if gate_decision is not None and gate_decision.decision == GateDecisionType.CONDITIONAL_PASS:
        return JobCompletion(
            JobStatus.DONE_WITH_CONCERNS,
            "review passed with unresolved IMPORTANT items",
            ["REVIEW_HAS_UNRESOLVED_IMPORTANT"],
        )

    # 有意设计：FAIL gate 仍然记为 SUCCEEDED。
    return JobCompletion(JobStatus.SUCCEEDED, "ok", [])
```

---

## 13. Approval 工厂与回流

> 设计约束：`create_*()` 一旦成功返回，就必须已经完成 approval 持久化、关联引用写入，以及目标 scope 进入 `BLOCKED_ON_HUMAN`。调用方不得再重复执行同一状态更新。


```python
def create_contract_approval(
    project_name: str,
    phase_name: str,
    approval_type: ApprovalType,
    related_files: list[str] | None = None,
    origin_stage: ReviewOriginStage | None = None,
) -> Approval:
    approval = approval_repo.create(
        project_name=project_name,
        phase_name=phase_name,
        approval_type=approval_type,
        origin_stage=origin_stage,
        related_files=related_files,
    )
    phase_repo.attach_latest_approval(project_name, phase_name, approval.approval_id)
    phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_HUMAN)
    return approval
```

```python
def create_close_phase_with_important_open(
    project_name: str,
    phase_name: str,
    origin_stage: ReviewOriginStage,
    related_files: list[str] | None = None,
) -> Approval:
    approval = approval_repo.create(
        project_name=project_name,
        phase_name=phase_name,
        approval_type=ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN,
        origin_stage=origin_stage,
        related_files=related_files,
    )
    phase_repo.attach_latest_approval(project_name, phase_name, approval.approval_id)
    phase_repo.update_status(project_name, phase_name, PhaseStatus.BLOCKED_ON_HUMAN)
    return approval
```

```python
def create_bootstrap_ready_with_important_open(
    project_name: str,
    origin_stage: ReviewOriginStage = ReviewOriginStage.BOOTSTRAP_REVIEW,
    related_files: list[str] | None = None,
) -> Approval:
    approval = approval_repo.create(
        project_name=project_name,
        phase_name=None,
        approval_type=ApprovalType.BOOTSTRAP_READY_WITH_IMPORTANT_OPEN,
        origin_stage=origin_stage,
        related_files=related_files,
    )
    project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_HUMAN)
    return approval
```

```python
def create_release_ready_confirm(
    project_name: str,
    related_files: list[str] | None = None,
) -> Approval:
    approval = approval_repo.create(
        project_name=project_name,
        phase_name=None,
        approval_type=ApprovalType.RELEASE_READY_CONFIRM,
        origin_stage=None,
        related_files=related_files,
    )
    project_repo.update_status(project_name, ProjectStatus.BLOCKED_ON_HUMAN)
    return approval
```

### 13.1 Approval 回流

```python
def approve(approval_id: str, actor: str) -> ApprovalOutcome:
    approval = approval_repo.get(approval_id)
    approval_repo.mark_approved(approval_id, actor)

    if approval.approval_type in {ApprovalType.CONTRACT_APPROVAL, ApprovalType.SCOPE_CHANGE}:
        phase_repo.update_status(approval.project_name, approval.phase_name, PhaseStatus.CONTRACT_APPROVED)
        return ApprovalOutcome(approval_id, approval.approval_type, None, PhaseStatus.CONTRACT_APPROVED, f"agent-orchestrator phase run --project {approval.project_name} --phase {approval.phase_name}")

    if approval.approval_type == ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN:
        phase_repo.update_status(approval.project_name, approval.phase_name, PhaseStatus.READY_TO_CLOSE)
        return ApprovalOutcome(approval_id, approval.approval_type, None, PhaseStatus.READY_TO_CLOSE, f"agent-orchestrator phase run --project {approval.project_name} --phase {approval.phase_name}")

    if approval.approval_type == ApprovalType.BOOTSTRAP_READY_WITH_IMPORTANT_OPEN:
        project_repo.update_status(approval.project_name, ProjectStatus.BOOTSTRAP_READY)
        return ApprovalOutcome(approval_id, approval.approval_type, ProjectStatus.BOOTSTRAP_READY, None, f"agent-orchestrator project advance --project {approval.project_name}")

    if approval.approval_type == ApprovalType.RELEASE_READY_CONFIRM:
        project_repo.update_status(approval.project_name, ProjectStatus.CLOSED)
        return ApprovalOutcome(approval_id, approval.approval_type, ProjectStatus.CLOSED, None, None)

    raise UnsupportedApprovalTypeError(...)
```

```python
def reject(approval_id: str, actor: str) -> ApprovalOutcome:
    approval = approval_repo.get(approval_id)
    approval_repo.mark_rejected(approval_id, actor)

    if approval.approval_type in {ApprovalType.CONTRACT_APPROVAL, ApprovalType.SCOPE_CHANGE}:
        phase_repo.update_status(approval.project_name, approval.phase_name, PhaseStatus.CONTRACT_VALIDATED)
        return ApprovalOutcome(approval_id, approval.approval_type, None, PhaseStatus.CONTRACT_VALIDATED, f"agent-orchestrator phase run --project {approval.project_name} --phase {approval.phase_name}")

    if approval.approval_type == ApprovalType.CLOSE_PHASE_WITH_IMPORTANT_OPEN:
        phase_repo.update_status(approval.project_name, approval.phase_name, PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS)
        return ApprovalOutcome(approval_id, approval.approval_type, None, PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS, f"agent-orchestrator phase run --project {approval.project_name} --phase {approval.phase_name}")

    if approval.approval_type == ApprovalType.BOOTSTRAP_READY_WITH_IMPORTANT_OPEN:
        project_repo.update_status(approval.project_name, ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS)
        return ApprovalOutcome(approval_id, approval.approval_type, ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS, None, f"agent-orchestrator bootstrap run --project {approval.project_name}")

    if approval.approval_type == ApprovalType.RELEASE_READY_CONFIRM:
        project_repo.update_status(approval.project_name, ProjectStatus.RELEASE_READY)
        return ApprovalOutcome(approval_id, approval.approval_type, ProjectStatus.RELEASE_READY, None, f"agent-orchestrator project request-close --project {approval.project_name}")

    raise UnsupportedApprovalTypeError(...)
```

---

## 14. Project 推进

> `project advance` 现在既承担“bootstrap 完成后进入第一 phase”的职责，也承担“当前 phase 完成后进入下一 phase / release-ready”的职责。

```python
def on_phase_done(project_name: str, phase_name: str) -> None:
    project = project_repo.get(project_name)
    if project.status != ProjectStatus.PHASE_ACTIVE:
        raise InvalidProjectTransitionError(
            f"project {project_name} is {project.status}, expected PHASE_ACTIVE before on_phase_done"
        )
    project_repo.update_status(project_name, ProjectStatus.PHASE_DONE)
```

> `on_phase_done()` 的 application guard 不能省略；repository `update_status()` 也必须独立执行白名单校验。两者是双保险，不可只保留一层。

```python
def advance(project_name: str) -> None:
    phases = project_plan_repo.list_ordered_phases(project_name)
    project = project_repo.get(project_name)

    if project.status == ProjectStatus.BOOTSTRAP_READY:
        first_phase = phases[0] if phases else None
        if first_phase is None:
            # 边缘路径：项目只需要 bootstrap，不定义任何 phase。
            project_repo.update_status(project_name, ProjectStatus.RELEASE_READY)
            project_repo.set_current_phase(project_name, None)
            return

        project_repo.set_current_phase(project_name, first_phase)
        project_repo.update_status(project_name, ProjectStatus.PHASE_ACTIVE)
        return

    if project.status != ProjectStatus.PHASE_DONE:
        raise InvalidProjectTransitionError(
            f"project {project_name} is {project.status}, expected BOOTSTRAP_READY or PHASE_DONE"
        )

    next_phase = _find_next_phase_after(project.current_phase, phases)
    if next_phase is None:
        project_repo.update_status(project_name, ProjectStatus.RELEASE_READY)
        project_repo.set_current_phase(project_name, None)
        return

    project_repo.set_current_phase(project_name, next_phase)
    project_repo.update_status(project_name, ProjectStatus.PHASE_ACTIVE)
```

---

## 15. 状态机白名单

### 15.1 Phase

```python
ALLOWED_PHASE_TRANSITIONS = {
    PhaseStatus.NOT_STARTED: {PhaseStatus.CONTRACT_VALIDATED},
    PhaseStatus.CONTRACT_VALIDATED: {PhaseStatus.CONTRACT_APPROVED, PhaseStatus.BLOCKED_ON_HUMAN},
    PhaseStatus.CONTRACT_APPROVED: {PhaseStatus.BUILDING},
    PhaseStatus.BUILDING: {PhaseStatus.REVIEW_PENDING, PhaseStatus.BLOCKED_ON_WORKER_FAILURE},
    PhaseStatus.REVIEW_PENDING: {
        PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
        PhaseStatus.BLOCKED_ON_HUMAN,
        PhaseStatus.READY_TO_CLOSE,
        PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
        PhaseStatus.BLOCKED_ON_WORKER_FAILURE,
    },
    PhaseStatus.BLOCKED_ON_HUMAN: {
        PhaseStatus.CONTRACT_APPROVED,
        PhaseStatus.READY_TO_CLOSE,
        PhaseStatus.CONTRACT_VALIDATED,
        PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
    },
    PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS: {
        PhaseStatus.BLOCKER_FIXING,
        PhaseStatus.RECHECK_PENDING,
        PhaseStatus.BLOCKED_ON_WORKER_FAILURE,
        PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
    },
    PhaseStatus.BLOCKER_FIXING: {PhaseStatus.RECHECK_PENDING, PhaseStatus.BLOCKED_ON_WORKER_FAILURE},
    PhaseStatus.RECHECK_PENDING: {
        PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
        PhaseStatus.BLOCKED_ON_HUMAN,
        PhaseStatus.READY_TO_CLOSE,
        PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT,
        PhaseStatus.BLOCKED_ON_WORKER_FAILURE,
    },
    PhaseStatus.READY_TO_CLOSE: {PhaseStatus.DONE, PhaseStatus.BLOCKED_ON_WORKER_FAILURE},
    PhaseStatus.BLOCKED_ON_WORKER_FAILURE: {
        PhaseStatus.CONTRACT_APPROVED,
        PhaseStatus.REVIEW_PENDING,
        PhaseStatus.BLOCKED_ON_OPEN_BLOCKERS,
        PhaseStatus.RECHECK_PENDING,
        PhaseStatus.READY_TO_CLOSE,
    },
    PhaseStatus.BLOCKED_ON_MISSING_ARTIFACT: {
        PhaseStatus.REVIEW_PENDING,
        PhaseStatus.RECHECK_PENDING,
    },
}
```

### 15.2 Project

```python
ALLOWED_PROJECT_TRANSITIONS = {
    ProjectStatus.INIT: {ProjectStatus.DESIGN_READY},
    ProjectStatus.DESIGN_READY: {ProjectStatus.BOOTSTRAP_RUNNING},

    ProjectStatus.BOOTSTRAP_RUNNING: {
        ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
        ProjectStatus.BLOCKED_ON_WORKER_FAILURE,
    },
    ProjectStatus.BOOTSTRAP_REVIEW_PENDING: {
        ProjectStatus.BOOTSTRAP_READY,
        ProjectStatus.BLOCKED_ON_HUMAN,
        ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS,
        ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT,
        ProjectStatus.BLOCKED_ON_WORKER_FAILURE,
    },

    ProjectStatus.BLOCKED_ON_OPEN_BLOCKERS: {
        ProjectStatus.BOOTSTRAP_RUNNING,
        ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
    },
    ProjectStatus.BLOCKED_ON_WORKER_FAILURE: {
        ProjectStatus.BOOTSTRAP_RUNNING,
        ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
    },
    ProjectStatus.BLOCKED_ON_MISSING_ARTIFACT: {
        ProjectStatus.BOOTSTRAP_RUNNING,
        ProjectStatus.BOOTSTRAP_REVIEW_PENDING,
    },

    ProjectStatus.BLOCKED_ON_HUMAN: {
        ProjectStatus.BOOTSTRAP_READY,
        ProjectStatus.RELEASE_READY,
        ProjectStatus.CLOSED,
    },

    ProjectStatus.BOOTSTRAP_READY: {ProjectStatus.PHASE_ACTIVE, ProjectStatus.RELEASE_READY},
    ProjectStatus.PHASE_ACTIVE: {ProjectStatus.PHASE_DONE},
    ProjectStatus.PHASE_DONE: {ProjectStatus.PHASE_ACTIVE, ProjectStatus.RELEASE_READY},
    ProjectStatus.RELEASE_READY: {ProjectStatus.BLOCKED_ON_HUMAN},
}
```

> 说明：`project.status` 仍然是粗粒度视图。phase 级阻塞不会自动上浮到 project 状态。  
> 说明：允许 `BOOTSTRAP_READY -> RELEASE_READY` 是为了支持“bootstrap 存在但 phase plan 为空”的项目。

---

## 16. CLI 映射

```bash
agent-orchestrator project status --project <name>
agent-orchestrator project advance --project <name>
agent-orchestrator project request-close --project <name>

agent-orchestrator bootstrap run --project <name>
agent-orchestrator bootstrap run --project <name> --force-full

agent-orchestrator phase run --project <name> --phase <phase_name>

agent-orchestrator approvals approve --project <name> --id <approval_id> --actor <actor_name>
agent-orchestrator approvals reject --project <name> --id <approval_id> --actor <actor_name>
```

---

## 17. 本版最重要的实现提醒

1. 不要省略 `RunLockRepository`，否则“两个新调用同时起跑”的问题依旧存在；
2. 不要只给 phase 做 stale reconciliation，而漏掉 bootstrap；
3. 不要让 `_normalize_failed_*` 直接执行业务 path；
4. 不要让 `append-backlog` 依赖“不会重跑”的假设；
5. 若 close-path active job 已结束但状态清理未完成，应清理 active execution 后允许幂等重跑；
6. `READY_TO_CLOSE` 不是“永远静态”的状态，它也可能携带 active close-path 上下文。
