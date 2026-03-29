# Phase 02 Codex Handoff

**Status:** `awaiting review`
**Branch:** `feat/phase-02-minimal-control-flow`

## 本轮定位

本轮已把 agent-orchestrator 从“Phase 01 的门禁与骨架”推进到“Phase 02 的最小控制链路”，但仍严格停留在 stub execution 边界，没有越界到真实 worker / 真实 runtime / 真实 side effect。

## 交付摘要

- 新增 Phase 02 coordination 文档，并把 dashboard 切到 `phase-02` 活跃状态。
- 提供最小可用的 `InMemorySchedulerService`，支持 stub job 入队、执行和 lease freshness 判断。
- 提供 `InMemoryArtifactStore` 与最小 review payload parser，使 fake review artifact 能驱动 gate 路由。
- 将 `BootstrapService` 从空 path 推进到最小闭环：
  - `DESIGN_READY`
  - `BOOTSTRAP_RUNNING`
  - `bootstrap-repo`
  - `BOOTSTRAP_REVIEW_PENDING`
  - `bootstrap-review`
  - gate 路由到 ready / human / blockers / missing artifact / worker failure
- 将 `PhaseService` 从合同入口 + close-path stub 推进到最小闭环：
  - contract approval
  - build / review
  - latest gate snapshot 写回
  - conditional pass approval
  - fail / invalid format / missing artifact / worker failure 路由
  - fix / recheck
  - close-path -> `DONE` -> `ProjectService.on_phase_done(...)`
- 扩展 approval 回流与 project advance 的可测试覆盖。

## 验证摘要

- `pytest -q` -> `382 passed`
- `python3 -m agent_orchestrator.cli.main --help` -> 成功展示 `project` / `bootstrap` / `phase` / `approvals`

## 未完成项 / 已知边界

- 真实 worker runtime、subprocess、真实 artifact / review parser、真实 adapter side effect 仍未接入。
- durable 持久化、MySQL / `CREATE DATABASE`、远端锁、stale lease 的真实恢复仍明确延后。
- backlog 持久化副作用、close marker durable 幂等、外部控制面接线仍留给后续阶段。

## Reviewer 使用说明

- Claude Code 本轮仅作为 reviewer；请优先检查：
  - Phase 01 guardrails 是否保持不变
  - bootstrap / phase gate 路由是否真实写回 active execution、failure context、snapshot ref、latest approval
  - `BLOCKED_ON_HUMAN` 是否仍只由 approval 工厂负责切换
  - 实现是否仍停留在 stub execution，而非真实 worker 集成

## 恢复工作入口

- 建议先读 `design_docs/coordination/phase-02/codex-plan.md`
- 然后看 `design_docs/coordination/phase-02/codex-status.md`
- 再运行 `pytest -q` 复核当前基线
