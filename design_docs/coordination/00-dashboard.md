# Coordination Dashboard

## Current Snapshot

- Project: `agent-orchestrator`
- Active branch: `feat/phase-03-worker-execution-mvp`
- Active phase: `phase-03`
- Status: `PHASE_01_CLOSED / PHASE_02_MERGED / PHASE_03_APPROVED`
- Owner: `Codex`
- Reviewer: `Claude Code`
- Repository landing branch: `main`
- Next step: merge Phase 03 to main and kickoff Phase 04
- Baseline docs:
  - `design_docs/agent-orchestrator-spec-v1.2.md`
  - `design_docs/agent-orchestrator-interface-design-v1.2.md`

## Phase Summary

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 01 | Closed | Accepted / merged / closeout completed |
| Phase 02 | Merged / closed | Minimal control flow 已 merged 到 `main` 并完成 closeout |
| Phase 03 | Approved / pending merge | 单机真实 worker 执行 MVP 已通过 review，准备 merge |

## Phase 03 Status

- State: `approved_pending_merge`
- Goal: 单机真实 worker 执行 MVP
- Plan: [design_docs/coordination/phase-03/codex-plan.md](phase-03/codex-plan.md)
- Status log: [design_docs/coordination/phase-03/codex-status.md](phase-03/codex-status.md)
- Handoff: [design_docs/coordination/phase-03/codex-handoff.md](phase-03/codex-handoff.md)

- 在 Phase 02 的最小控制链路之上，已新增真实 worker execution 抽象、文件系统 artifact store 与本地 subprocess runner。
- bootstrap 已打通真实执行链：`bootstrap-repo` -> `bootstrap-review` -> gate 路由。
- phase 已打通真实执行链：`phase-build` -> `phase-review` -> gate / close-path。
- 继续保留 stub mode、内存 repo、现有 approval / close-path / state machine 语义。
- 明确不进入远程执行、分布式锁、durable DB persistence、对象存储与外部 SaaS 编排。

## Phase 02 Status

- State: `merged / closed`
- Goal: 最小控制链路
- Plan: [design_docs/coordination/phase-02/codex-plan.md](phase-02/codex-plan.md)
- Status log: [design_docs/coordination/phase-02/codex-status.md](phase-02/codex-status.md)
- Handoff: [design_docs/coordination/phase-02/codex-handoff.md](phase-02/codex-handoff.md)
- Merge summary: [design_docs/coordination/phase-02/merge-summary.md](phase-02/merge-summary.md)
- Reviewer archive: `design_docs/reviews/phase-02-claude-review.md`

- Phase 02 minimal control flow 已 merged 到 `main`。
- Phase 02 closeout 已完成；本轮不再继续做 Phase 02 收尾。
- 已冻结的控制语义将直接作为 Phase 03 的基线。

## Phase 01 Status and Scope

- State: `accepted / closed`
- Merge summary: [design_docs/coordination/phase-01/merge-summary.md](phase-01/merge-summary.md)
- Gate conclusion: Phase 01 已关闭，允许进入 Phase 02 kickoff；Phase 02 当前处于 kickoff started 状态。

- 建立最小 Python 工程骨架。
- 先落状态机门禁、repository 白名单与 application guard。
- 固化 `run_bootstrap()` / `run_phase()` 顺序骨架。
- 提供 `RunLockRepository` 本地最小实现与互斥测试。
- 固化 approval 工厂职责与 close-path 预留接口位。

## Status Tracking

| Item | Status | Notes |
| --- | --- | --- |
| Phase 01 closeout | Done | Accepted / closed / merged to `main` |
| Phase 02 kickoff docs | Done | `codex-plan.md` / `codex-status.md` / `codex-handoff.md` 已归档 |
| Phase 02 implementation | Done | 最小控制链路已落地并通过全量测试 |
| Phase 02 review handoff | Done | reviewer 文档已归档到 `design_docs/reviews/phase-02-claude-review.md` |
| Phase 02 Claude review | Done | `APPROVED`；无高/中优先级问题，仅保留低优先级人工复核项 |
| Phase 02 closeout docs | Done | dashboard / status / handoff / merge summary 已同步到 merged 状态 |
| Phase 02 merge to main | Done | 已 fast-forward 到 `main@07ff8ad` |
| Phase 03 kickoff docs | Done | `codex-plan.md` / `codex-status.md` / `codex-handoff.md` 已建立并同步到 review 前状态 |
| Phase 03 worker execution MVP | Approved | 文件系统 artifact store / subprocess runner / bootstrap & phase 真实执行链已通过 review |
| Read spec/interface docs | Done | 已确认 v1.2 门禁与骨架约束 |
| Write phase-01 phase doc | Done | `design_docs/phases/phase-01-gates-and-skeleton.md` 已转为完成阶段档案 |
| Create package skeleton | Done | `agent_orchestrator/` 与 `tests/` 已随 PR #1 合入 `main` |
| Add state machine guards | Done | repository 白名单 + `ProjectService` guard 已合入 `main` |
| Add run lock implementation | Done | 本地文件锁实现已合入；仅剩低优先级 stale lock 风险 |
| Add minimal tests | Done | 相关状态机、approval、close-path、run lock 测试已合入 |
| Add close-path active execution stub | Done | `APPEND_BACKLOG` / `CLOSE_PHASE` set/clear active execution 已合入 |
| Write self-review | Done | `design_docs/reviews/phase-01-codex-self-review.md` 已保留为归档材料 |
| Claude review completed | Done | `APPROVED`；仅剩低优先级 stale lock 风险 |
| Code merged to main | Done | PR `#1` merged as `abedccb1d16afe40bd4aa35924f9c292a6639836` |
| Closeout completed | Done | merge summary、dashboard、phase doc 状态已完成收口 |

## Reviewer Inputs Completed

- Claude review 已完成，并确认实现严格遵守 v1.2 文档语义。
- Phase 02 review 结论为 `APPROVED`，无高优先级问题、无中优先级问题。
- `BootstrapService._ensure_runtime_dependencies` 已人工复核；当前实现无需为了“更简洁”调整 waterfall 顺序。
- `PhaseService` 中 `blockers_entry` / `recheck_entry` 恢复入口已人工复核；当前实现满足恢复场景边界。
- Approval 工厂作为唯一阻塞态切换责任方的约束已完成审查。
- `run_phase()` / `run_bootstrap()` 固定顺序已完成审查。
- close-path stub 的边界已确认停留在 Phase 01，不越界到真实 worker 集成。

## Deliverables Completed

- Minimal code skeleton in `agent_orchestrator/`
- Test suite in `tests/`
- Self-review in `design_docs/reviews/phase-01-codex-self-review.md`
- Claude review in `design_docs/reviews/phase-01-claude-review.md`
- Merge summary in `design_docs/coordination/phase-01/merge-summary.md`
- Phase closeout status updates in dashboard and phase archive

## Phase 02 Deliverables

- Kickoff plan in `design_docs/coordination/phase-02/codex-plan.md`
- Status tracker in `design_docs/coordination/phase-02/codex-status.md`
- Handoff tracker in `design_docs/coordination/phase-02/codex-handoff.md`
- Merge summary in `design_docs/coordination/phase-02/merge-summary.md`
- Claude review archive in `design_docs/reviews/phase-02-claude-review.md`
- Minimal control flow implementation and coverage on branch `feat/phase-02-minimal-control-flow`

## Deferred Beyond Phase 02

- Real worker execution and orchestration integration
- Persistent job / snapshot stores and lease recovery
- Durable close-path idempotency side effects
- Phase 03 kickoff and Phase 03 implementation work

## Deferred Beyond Phase 03 MVP

- Remote workers and multi-host scheduling
- Durable DB persistence and distributed leases
- Object storage, archival policy, and production-grade observability
- External SaaS orchestration, enterprise approvals, and UI layers
