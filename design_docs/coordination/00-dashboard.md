# Coordination Dashboard

## Current Snapshot

- Project: `agent-orchestrator`
- Active branch: `feat/phase-01-gates-and-skeleton`
- Active phase: `phase-01`
- Status: `READY_FOR_REVIEW`
- Owner: `Codex`
- Reviewer: `Claude Code`
- Baseline docs:
  - `design_docs/agent-orchestrator-spec-v1.2.md`
  - `design_docs/agent-orchestrator-interface-design-v1.2.md`

## Phase 01 Scope

- 建立最小 Python 工程骨架。
- 先落状态机门禁、repository 白名单与 application guard。
- 固化 `run_bootstrap()` / `run_phase()` 顺序骨架。
- 提供 `RunLockRepository` 本地最小实现与互斥测试。
- 固化 approval 工厂职责与 close-path 预留接口位。

## Status Tracking

| Item | Status | Notes |
| --- | --- | --- |
| Read spec/interface docs | Done | 已确认 v1.2 门禁与骨架约束 |
| Write phase-01 phase doc | Done | `design_docs/phases/phase-01-gates-and-skeleton.md` |
| Create package skeleton | Done | `agent_orchestrator/` 与 `tests/` 已建立 |
| Add state machine guards | Done | repository 白名单 + `ProjectService` guard |
| Add run lock implementation | Done | 本地文件锁实现，可测试 scope 互斥 |
| Add minimal tests | Done | 已扩展到 `pytest` 358 项通过 |
| Add close-path active execution stub | Done | `APPEND_BACKLOG` / `CLOSE_PHASE` 可 set/clear active execution |
| Write self-review | Done | `design_docs/reviews/phase-01-codex-self-review.md` |

## Reviewer Inputs

- 重点审查是否严格遵守 v1.2 文档语义。
- 重点审查 approval 工厂是否为唯一阻塞态切换责任方。
- 重点审查 `run_phase()` / `run_bootstrap()` 顺序是否被破坏。
- 重点审查 close-path stub 是否止步于 phase-01，不越界到真实 worker 集成。

## Deliverables Planned

- Minimal code skeleton in `agent_orchestrator/`
- Test suite in `tests/`
- Self-review in `design_docs/reviews/phase-01-codex-self-review.md`
- One commit on branch `feat/phase-01-gates-and-skeleton`

## Deferred Beyond Phase 02

- Real worker execution and orchestration integration
- Persistent job / snapshot stores and lease recovery
- Durable close-path idempotency side effects
