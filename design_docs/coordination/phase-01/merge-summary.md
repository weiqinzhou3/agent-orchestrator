# Phase 01 Merge Summary / Closeout

## 1. Merge 基本信息

- Phase 名称：`phase-01`
- Merge 事实：Phase 01 已通过 PR #1 合入 `main`，本阶段代码已成为当前主线基线。
- Feature branch：`feat/phase-01-gates-and-skeleton`
- Review branch：`review/phase-01-claude-review`
  - 说明：该 review 分支在仓库中可见；其审查文档内容已同步到 feature branch 后，再随 PR #1 合入 `main`。
- PR 编号：`#1`，标题为 `[codex] phase-01 gates and skeleton baseline`
- Merge commit SHA：`abedccb1d16afe40bd4aa35924f9c292a6639836`

## 2. 本阶段目标回顾

- 建立最小但正确的 Python 工程骨架，为后续 phase 业务实现提供稳定底座。
- 先落状态机白名单、repository 门禁与 application guard，冻结 v1.2 语义边界。
- 固化 `run_bootstrap()` / `run_phase()` 的固定执行顺序，避免后续演进破坏调度骨架。
- 提供最小可测试的 `RunLockRepository`，先满足本地 scope 互斥。
- 固化 `ApprovalService.create_*()` 的工厂职责，并为 close-path 预留必要接口位。

## 3. 实际完成内容

- 工程骨架：`agent_orchestrator/` 包目录、CLI 入口、application/domain/infra 基础结构与最小项目配置已落地。
- 状态机白名单：`ALLOWED_PROJECT_TRANSITIONS` 与 `ALLOWED_PHASE_TRANSITIONS` 已落地，并由实现与测试共同锁定。
- Repository 门禁：project/phase repository 的 `update_status()` 已执行白名单校验，拒绝非法跳转。
- Application guard：`ProjectService.on_phase_done()` 与 `ProjectService.advance()` 保留显式 guard，不退化为单层 repository 防护。
- Run skeleton 顺序：`run_bootstrap()` 与 `run_phase()` 已固定为 lock -> reconcile inflight -> normalize failed entry -> waterfall。
- `RunLockRepository`：本地最小实现已满足 project 与 phase scope 互斥，并具备对应测试。
- Approval 工厂职责：`ApprovalService.create_*()` 已统一承担 approval 创建、关联写入与 `BLOCKED_ON_HUMAN` 切换责任。
- Close-path active execution stub：`APPEND_BACKLOG` / `CLOSE_PHASE` 已具备最小 set/clear active execution 行为，并保留 `dedupe_scope` / `close_marker` 参数位。
- 测试覆盖：状态机、repository 门禁、application guard、run skeleton 顺序、approval 职责、close-path stub 与 run lock 互斥均已覆盖。
- Review 文档纳入 feature 分支并完成合并：Claude review 报告来源于 `review/phase-01-claude-review` 路径上的审查产物，已在合并前同步到 feature branch 并随 PR #1 进入 `main`。

## 4. 明确未完成但属于刻意延后

- 真实 worker 执行链路仍未实现。
- 持久化 `JobRepository` / snapshot store 仍未接线。
- stale lease、stale job 与真实恢复流程仍未实现。
- durable close-path 幂等副作用与真实 close marker 落库仍未实现。
- 外部执行接线、配置装配与真实依赖容器仍未接入。
- 其他 Phase 02 及之后的业务细化内容继续留在后续 kickoff 中处理。

## 5. 审查结论摘要

- `design_docs/reviews/phase-01-claude-review.md` 的审查结论为 `APPROVED`。
- 当前仅保留一个低优先级风险：`FileRunLockRepository` 在异常崩溃后的 stale lock 残留风险。
- 该风险不影响 Phase 01 验收，也不阻塞 Phase 02 启动；它属于后续实现阶段可控处理项。

## 6. Gate 结论

- `Phase 01: accepted / closed`
- `Phase 02: allowed to start`
- 说明：Phase 02 仍需单独 kickoff；本 closeout 仅确认 Phase 01 已完成收口，并不表示 Phase 02 已开始编码。

## 7. 后续建议

- 在 Phase 02 kickoff 中先明确持久化边界，优先确定 `JobRepository` 与 snapshot store 的职责切分。
- 在扩展真实 worker 前，保持 `run_bootstrap()` / `run_phase()` 固定顺序不变，只在既有骨架内补行为。
- 为 `FileRunLockRepository` 制定 stale lock 处理策略，避免后续把低优先级风险升级成恢复阻塞点。
- 将 close-path 的 durable idempotency 设计为在现有 `dedupe_scope` / `close_marker` 接口位上增量演进，而不是重写语义。
- 在接入外部执行前，继续保持 approval 工厂为唯一阻塞态切换责任方，避免 Phase 01 已冻结的职责边界被破坏。
