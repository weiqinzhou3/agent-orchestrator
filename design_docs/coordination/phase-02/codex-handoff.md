# Phase 02 Codex Handoff

**Status:** `approved_pending_merge`
**Branch:** `feat/phase-02-minimal-control-flow`

## 本轮定位

本轮已把 agent-orchestrator 从“Phase 01 的门禁与骨架”推进到“Phase 02 的最小控制链路”，并已完成 reviewer 后收口。当前分支已停留在 stub execution 边界，没有越界到真实 worker / 真实 runtime / 真实 side effect，下一步应为 merge 到 `main`，而不是继续扩功能或提前进入 Phase 03。

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

## Reviewer 结果摘要

- reviewer 文档：`design_docs/reviews/phase-02-claude-review.md`
- 审查结论：`APPROVED`
- 高优先级问题：无
- 中优先级问题：无
- 低优先级建议处理结果：
  - `BootstrapService._ensure_runtime_dependencies`：已人工复核，无需修复；当前调用点虽然可再压缩，但不值得为“更简洁”而调整 waterfall 顺序。
  - `PhaseService.blockers_entry` / `recheck_entry`：已人工复核，当前入口锁存逻辑满足恢复场景边界；fix path 成功后会在同一轮内部衔接到 recheck，不需要重写 waterfall。
- 当前结论：本分支已进入可 merge 状态。

## 未完成项 / 已知边界

- 真实 worker runtime、subprocess、真实 artifact / review parser、真实 adapter side effect 仍未接入。
- durable 持久化、MySQL / `CREATE DATABASE`、远端锁、stale lease 的真实恢复仍明确延后。
- backlog 持久化副作用、close marker durable 幂等、外部控制面接线仍留给后续阶段。
- Phase 03 kickoff 尚未开始，本次 handoff 不包含任何 Phase 03 代码变更。

## Merge 前说明

- Phase 02 minimal control flow 已通过 reviewer，当前收口文档已同步到 approved / pending merge 状态。
- merge 前无需继续扩功能；若仅做额外检查，应继续限定在文档核对或不改语义的人工复核。
- merge 完成后，才进入单独的 Phase 03 kickoff。

## 恢复工作入口

- 建议先读 `design_docs/coordination/phase-02/codex-plan.md`
- merge 前 closeout 可直接读 `design_docs/coordination/phase-02/merge-summary.md`
- 然后看 `design_docs/coordination/phase-02/codex-status.md`
- 再运行 `pytest -q` 复核当前基线
