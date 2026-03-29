# Phase 02 Codex Plan: Minimal Control Flow

**Last updated:** `2026-03-29 18:25:26 +0800`
**Owner:** `Codex`
**Reviewer:** `Claude Code`
**Status:** `kickoff started`

## 1. 本阶段目标

Phase 02 的目标不是补齐全部业务，而是在 Phase 01 已冻结的门禁与骨架之上，把 orchestrator 推进到“最小控制链路可闭环、可验证、仍保持 stub 边界”的状态。

本阶段完成后，系统应至少具备以下能力：

- bootstrap 能从 `DESIGN_READY` 最小跑到 gate 路由结果，而不是停留在空 path。
- phase 能从 contract -> build/review -> close-path 跑通最小闭环，并把 gate/approval/failure context 写回仓储。
- job / snapshot / artifact / scheduler 能为服务层提供最小可调用支撑，但不接任何真实外部 runtime。
- project advance 与 approval approve/reject 能和 bootstrap / phase 结果形成最小回流。

## 2. In Scope

- 新建 Phase 02 coordination 文档，并在 dashboard 中正式启动 kickoff 状态。
- 将 `InMemoryJobRepository`、`InMemoryPhaseGateSnapshotRepository`、`InMemoryArtifactStore` 从纯占位推进到可被控制链路直接调用。
- 为 `SchedulerService` 提供最小可用的内存 stub，实现 `enqueue(job)`、`execute_job(job_id)`、`is_job_lease_fresh(job_id)`。
- 为 bootstrap 补最小控制闭环：
  - `DESIGN_READY`
  - `BOOTSTRAP_RUNNING`
  - `bootstrap-repo` stub job
  - `BOOTSTRAP_REVIEW_PENDING`
  - `bootstrap-review` stub job
  - gate 路由到 `BOOTSTRAP_READY` / `BLOCKED_ON_HUMAN` / `BLOCKED_ON_OPEN_BLOCKERS` / `BLOCKED_ON_MISSING_ARTIFACT` / `BLOCKED_ON_WORKER_FAILURE`
- 为 phase 补最小控制闭环：
  - contract validation / approval
  - build -> review
  - fail / conditional pass / invalid format / missing artifact / worker failure 分支
  - latest gate snapshot、latest approval、active execution、failure context 的真实写回
  - `READY_TO_CLOSE` 的最小 close-path -> `DONE` -> `ProjectService.on_phase_done(...)`
- 补 approval 回流、project advance、active execution、failure context、Phase 01 guardrails 的测试。

## 3. Out of Scope

- 真实 worker runtime、subprocess 调用、真实 adapter side effect。
- 真实 review artifact 文件解析、真实 artifact 目录结构与持久化管理。
- durable 数据库持久化、MySQL / `CREATE DATABASE`、远端锁、分布式 lease。
- backlog item 真正落库、副作用幂等持久化、close marker 最终实现。
- Deep Agent / MCP / 外部控制面接线。
- 任何超出 v1.2 定义的新状态、新命令语义或新恢复路径。

## 4. 与 Phase 01 的衔接关系

- Phase 01 已冻结的内容继续保持不变：状态机白名单、repository 门禁、application guard、run skeleton 顺序、approval 工厂职责、run lock 行为。
- Phase 02 只在既有 waterfall 内补最小行为，不改 `run_bootstrap()` / `run_phase()` 的顺序，也不改 `READY_TO_CLOSE` 的建模方式。
- Phase 01 为 close-path 预留的 `dedupe_scope` / `close_marker` 仍保持接口位语义；本阶段只赋予最小控制链路意义，不补 durable 副作用。
- Phase 01 的 reviewer 结论中唯一保留的 stale lock 风险继续视作低优先级背景项，不在本轮扩 scope 处理。

## 5. 本轮要实现的最小控制链路

### 5.1 控制链路基线

- 所有 job 仍是 stub job，但必须通过 repository + scheduler + service 的组合形成真实状态推进。
- 所有 review/recheck gate 仍来自 fake payload，但必须通过最小解析与 snapshot 写回形成权威 gate ref。
- 所有阻塞与失败都必须真实写入 `latest_approval_id`、`latest_gate_snapshot_id`、active execution、failure context；不能只改最终状态。

### 5.2 Bootstrap 最小闭环

- `DESIGN_READY` 进入 waterfall 后，先切到 `BOOTSTRAP_RUNNING`。
- `bootstrap-repo` job 由 scheduler 入队并执行，成功后清理 active bootstrap execution，并推进到 `BOOTSTRAP_REVIEW_PENDING`。
- `bootstrap-review` job 由 scheduler 入队并执行，结果按最小 gate 路由：
  - `PASS` -> `BOOTSTRAP_READY`
  - `CONDITIONAL_PASS` -> `ApprovalService.create_bootstrap_ready_with_important_open(...)` -> `BLOCKED_ON_HUMAN`
  - `FAIL` -> `BLOCKED_ON_OPEN_BLOCKERS`
  - `INVALID_FORMAT` 或 artifact 缺失 -> `BLOCKED_ON_MISSING_ARTIFACT`
  - worker 失败 -> `BLOCKED_ON_WORKER_FAILURE`

### 5.3 Phase 最小闭环

- contract path 保持现有入口，但后续不再停在空方法。
- build / review / fix / recheck job 均通过 scheduler 执行 fake 结果。
- review 与 recheck 至少支持：
  - `PASS` -> `READY_TO_CLOSE`
  - `CONDITIONAL_PASS` -> 创建 `CLOSE_PHASE_WITH_IMPORTANT_OPEN` approval -> `BLOCKED_ON_HUMAN`
  - `FAIL` -> `BLOCKED_ON_OPEN_BLOCKERS`
  - `INVALID_FORMAT` / artifact 缺失 -> `BLOCKED_ON_MISSING_ARTIFACT`
  - worker 失败 -> `BLOCKED_ON_WORKER_FAILURE`
- gate snapshot 在 review / recheck 有 gate 时必须真实写入 repo，并回填 phase 的 latest gate ref。
- `READY_TO_CLOSE` 的 close-path 继续使用 `APPEND_BACKLOG` / `CLOSE_PHASE` active execution，但需要具备最小“控制链路意义”：
  - 产生命令级 executed job id
  - 清理 failure context
  - 标记 `DONE`
  - 回调 `ProjectService.on_phase_done(...)`

### 5.4 Project / Approval 回流

- `BOOTSTRAP_READY` -> `project advance` -> 首 phase 或 `RELEASE_READY`
- `DONE` -> `on_phase_done(...)` -> `PHASE_DONE`
- `PHASE_DONE` -> `project advance` -> 下一 phase 或 `RELEASE_READY`
- `RELEASE_READY` -> `request_close()` -> `BLOCKED_ON_HUMAN`
- approval approve / reject 必须把 project / phase 拉回 v1.2 规定的目标状态

## 6. 文件改动计划

- 新增 `design_docs/coordination/phase-02/codex-plan.md`
- 新增 `design_docs/coordination/phase-02/codex-status.md`
- 新增 `design_docs/coordination/phase-02/codex-handoff.md`
- 更新 `design_docs/coordination/00-dashboard.md`
- 修改 `agent_orchestrator/infra/db/repositories.py`
  - 补最小可用的 in-memory job / snapshot 行为与辅助查询
- 修改 `agent_orchestrator/infra/fs/artifact_store.py`
  - 新增 `InMemoryArtifactStore`，通过预置 artifact 内容支撑服务层读取
- 修改 `agent_orchestrator/domain/review_parser.py`
  - 只解析 Phase 02 需要的 fake gate payload，不引入真实 artifact 语义
- 修改 `agent_orchestrator/application/scheduler_service.py`
  - 提供最小内存 scheduler stub 与 fake execution summary 驱动
- 修改 `agent_orchestrator/application/bootstrap_service.py`
  - 补 bootstrap repo/review 最小控制闭环
- 修改 `agent_orchestrator/application/phase_service.py`
  - 补 build/review/fix/recheck/close-path 最小控制闭环
- 可能轻量修改 `agent_orchestrator/application/project_service.py`
  - 仅在必要时补 Phase 02 回流细节，不放宽既有 guard
- 测试新增或扩展：
  - `tests/test_bootstrap_control_flow.py`
  - `tests/test_phase_control_flow.py`
  - `tests/test_scheduler_service.py`
  - `tests/test_artifact_store.py`
  - `tests/test_project_service.py`
  - `tests/test_approval_service.py`
  - `tests/test_close_path.py`
  - `tests/test_run_skeleton.py`
  - `tests/test_run_locks.py`
  - `tests/test_state_machine.py`

## 7. 测试计划

- 先写失败测试，再补最小实现；不允许先写生产代码再补测试。
- bootstrap 最小闭环：
  - PASS
  - CONDITIONAL_PASS
  - FAIL
  - INVALID_FORMAT / missing artifact / worker failure
- phase 最小闭环：
  - contract approval 路径
  - build -> review -> ready_to_close -> done
  - conditional pass -> approval -> blocked_on_human
  - fail -> blocked_on_open_blockers
  - invalid format / missing artifact / worker failure
  - close-path 完成后触发 `on_phase_done(...)`
- approval 回流：
  - contract / close phase / bootstrap ready / release ready 的 approve / reject 目标状态
- project advance：
  - `BOOTSTRAP_READY` 空 plan -> `RELEASE_READY`
  - `BOOTSTRAP_READY` 有第一 phase -> `PHASE_ACTIVE`
  - `PHASE_DONE` 有下一 phase -> `PHASE_ACTIVE`
  - `PHASE_DONE` 无下一 phase -> `RELEASE_READY`
- active execution / failure context：
  - bootstrap
  - phase
  - close-path
  - job failure reason/result path
- guardrails 回归：
  - run skeleton 顺序
  - approval 工厂仍是唯一 `BLOCKED_ON_HUMAN` owner
  - repository 白名单
  - run lock 互斥

## 8. Reviewer 关注点

- 是否严格维持 Phase 01 冻结的顺序、状态机和 approval 职责边界。
- scheduler / artifact / repository 是否只是最小控制链路支撑，而没有越界为真实外部集成。
- bootstrap / phase 的 gate 路由是否真实更新了 active execution、failure context、snapshot ref、latest approval。
- `CONDITIONAL_PASS` reject 后是否正确回流到 `BLOCKED_ON_OPEN_BLOCKERS`，并保留后续 fix/recheck 入口。
- `READY_TO_CLOSE` 是否继续保持唯一 close-path 入口态，没有被拆成新 phase 状态。
