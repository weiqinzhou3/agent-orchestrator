# Phase 03 Codex Handoff

**Status:** `approved_pending_merge`
**Branch:** `feat/phase-03-worker-execution-mvp`

## 本轮定位

本轮已把 agent-orchestrator 从“Phase 02 的最小控制链路 + stub execution”推进到“Phase 03 的单机真实 worker 执行 MVP”。实现保持在单机、本地、文件系统与 subprocess 边界内，没有引入远程执行、分布式 lease 或 durable persistence。

## 交付摘要

- 新增 Phase 03 coordination 文档：
  - `design_docs/coordination/phase-03/codex-plan.md`
  - `design_docs/coordination/phase-03/codex-status.md`
  - `design_docs/coordination/phase-03/codex-handoff.md`
- 更新 `design_docs/coordination/00-dashboard.md`，将 Phase 02 标记为 merged / closed，并将 active phase 切到 Phase 03。
- `ArtifactStore` 从纯内存推进到文件系统 MVP：
  - 新增 `FileArtifactStore`
  - 为内存实现补齐 `write_text` / `write_json`
  - 增加 `resolve_path` 以支持本地 subprocess worker 访问 artifact 文件
- 建立真实 worker 执行抽象：
  - `WorkerRunSpec`
  - `WorkerRunner`
  - `SubprocessRunner`
- 新增本地 worker contract 与 entry module：
  - `LocalSubprocessJobFactory`
  - build-like worker 写 JSON artifact
  - review-like worker 读 build artifact 后写 review payload
- `InMemorySchedulerService` 保留 stub mode，同时新增 local-subprocess mode。
- bootstrap 真实执行链已跑通：
  - `bootstrap-repo`
  - `bootstrap-review`
  - PASS / CONDITIONAL_PASS / FAIL / invalid payload / missing artifact
- phase 真实执行链已跑通：
  - `phase-build`
  - `phase-review`
  - PASS / CONDITIONAL_PASS / FAIL / invalid payload / missing artifact
  - PASS 路径继续沿用现有 close-path 到 `DONE`

## 关键文件

- `agent_orchestrator/application/scheduler_service.py`
- `agent_orchestrator/domain/results.py`
- `agent_orchestrator/infra/execution/subprocess_runner.py`
- `agent_orchestrator/infra/fs/artifact_store.py`
- `agent_orchestrator/infra/workers/base.py`
- `agent_orchestrator/infra/workers/local.py`
- `tests/test_artifact_store.py`
- `tests/test_subprocess_runner.py`
- `tests/test_scheduler_service.py`
- `tests/test_bootstrap_control_flow.py`
- `tests/test_phase_control_flow.py`

## 验证摘要

- `pytest -q` -> `397 passed in 4.05s`
- 新增覆盖：
  - 文件系统 artifact store round-trip
  - subprocess runner 成功 / 非零退出 / stdout / stderr / result_path
  - scheduler real local worker execution
  - bootstrap local subprocess PASS / CONDITIONAL_PASS / FAIL / invalid payload / missing artifact
  - phase local subprocess PASS / CONDITIONAL_PASS / FAIL / invalid payload / missing artifact

## 明确延后项

- 远程 worker / 多机调度 / 容器编排
- durable DB persistence / 对象存储 / 复杂 artifact 生命周期
- `phase-fix-blockers` / `phase-recheck` 的真实 subprocess 化
- 生产级 observability、审计、外部审批系统集成

## Reviewer 关注点

- `InMemorySchedulerService` 的双模式是否完整保留了 Phase 02 stub 测试语义。
- `BLOCKED_ON_HUMAN` 是否仍只由 `ApprovalService` 产生。
- `READY_TO_CLOSE` 是否仍是唯一 close-path 入口态。
- 本地 worker contract 是否足够简单且不会把仓库拖向“伪分布式 orchestrator”。
