# Coordination Dashboard

## Current Snapshot

- Project: `agent-orchestrator`
- Active branch: `feat/phase-02-minimal-control-flow`
- Active phase: `phase-02`
- Status: `PHASE_01_CLOSED / PHASE_02_AWAITING_REVIEW`
- Owner: `Codex`
- Reviewer: `Claude Code`
- Repository landing branch: `main`
- Next step: Claude review of phase-02 minimal control flow
- Baseline docs:
  - `design_docs/agent-orchestrator-spec-v1.2.md`
  - `design_docs/agent-orchestrator-interface-design-v1.2.md`

## Phase Summary

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 01 | Closed | Accepted / merged / closeout completed |
| Phase 02 | Awaiting review | Minimal control flow implemented on `feat/phase-02-minimal-control-flow` |

## Phase 02 Kickoff

- State: `implementation complete / awaiting review`
- Goal: 最小控制链路
- Plan: [design_docs/coordination/phase-02/codex-plan.md](phase-02/codex-plan.md)
- Status log: [design_docs/coordination/phase-02/codex-status.md](phase-02/codex-status.md)
- Handoff: [design_docs/coordination/phase-02/codex-handoff.md](phase-02/codex-handoff.md)

- 已在 Phase 01 骨架之上补最小 bootstrap / phase / approval / project 控制闭环。
- 已把 job / snapshot / artifact / scheduler 推进到最小可用内存实现。
- 真实 worker、真实 artifact、真实 adapter side effect 与 durable 持久化仍继续延后。

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
| Phase 02 kickoff docs | Done | `codex-plan.md` / `codex-status.md` / `codex-handoff.md` 已建立并更新 |
| Phase 02 implementation | Done | 最小控制链路已落地并通过全量测试 |
| Phase 02 review handoff | In Progress | 当前等待 Claude Code review |
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
- Minimal control flow implementation and coverage on branch `feat/phase-02-minimal-control-flow`

## Deferred Beyond Phase 02

- Real worker execution and orchestration integration
- Persistent job / snapshot stores and lease recovery
- Durable close-path idempotency side effects
