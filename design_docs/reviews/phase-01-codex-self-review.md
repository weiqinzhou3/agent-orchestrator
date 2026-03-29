# Phase 01 Codex Self-Review

## 1. 本轮改动摘要

- 新建 Python 工程骨架与 `agent_orchestrator/` 包。
- 新建 `cli/`、`application/`、`domain/`、`infra/` 目录与基础文件。
- 落地状态枚举、实体、结果对象、错误类型与状态机白名单。
- 落地内存版 repository，并在 `update_status()` 中执行 project/phase 白名单校验。
- 落地 `ProjectService.on_phase_done()` guard 与 `advance()` 的 `BOOTSTRAP_READY -> RELEASE_READY` 空 phase plan 边缘路径。
- 落地 `BootstrapService.run_bootstrap()` / `PhaseService.run_phase()` 固定骨架顺序：
  1. acquire lock
  2. reconcile inflight
  3. normalize failed entry
  4. waterfall
- 落地 `ApprovalService.create_*()` 工厂职责，统一执行 approval 创建与 `BLOCKED_ON_HUMAN` 状态切换。
- 落地 `FileRunLockRepository` 本地最小实现，并通过测试验证 scope 互斥。
- 落地 close-path active execution 最小 stub，可对 `APPEND_BACKLOG` / `CLOSE_PHASE` 设置并清理 active execution。
- 将测试扩展到状态机合法/非法迁移、服务级锁并发、approval caller 去重与 close-path active execution。
- 新增 phase 文档与 coordination dashboard。

## 2. 与 spec/interface docs 的映射

- spec 2.11 / interface 13:
  - `agent_orchestrator/application/approval_service.py`
  - `create_*()` 统一负责 approval 创建、关联写入与 `BLOCKED_ON_HUMAN` 切换。
- spec 2.10 / interface 2.2, 7:
  - `agent_orchestrator/infra/fs/run_locks.py`
  - 提供 project / phase 级本地锁实现。
- spec 2.5, 2.6, 7.2 / interface 2.1, 2.4, 10:
  - `agent_orchestrator/application/bootstrap_service.py`
  - `agent_orchestrator/application/phase_service.py`
  - 固定 `run_*` 顺序，保留 close-path active execution 与 `dedupe_scope` / `close_marker` 参数位。
- spec 1, 2.8, 8.1 / interface 4, 14, 15:
  - `agent_orchestrator/domain/enums.py`
  - `agent_orchestrator/domain/state_machine.py`
  - `agent_orchestrator/infra/db/repositories.py`
  - `agent_orchestrator/application/project_service.py`
  - 枚举、白名单、repository 校验与 application guard 已对齐。
- interface 3, 5, 6, 7:
  - `agent_orchestrator/domain/entities.py`
  - `agent_orchestrator/domain/results.py`
  - `agent_orchestrator/infra/db/repositories.py`
  - 基础领域对象、结果对象与 repository stub 已落地。

## 3. 未完成项

- bootstrap repo/review、phase build/review/fix/recheck/close 的真实 worker 路径仍为 skeleton/stub。
- `PhaseGateSnapshotRepository`、`JobRepository`、`ArtifactStore` 目前只有最小实现，未接入真实持久化。
- close-path 的真正幂等去重与 close marker 落库尚未实现；当前只有 fake job id + active execution stub。
- CLI 目前只完成命令结构与解析，尚未接入真实容器与持久化环境。
- 以下内容故意延后到 phase-02 之后：
  - 真实 worker 集成
  - artifact / gate payload 真实解析
  - lease freshness 与 stale reconciliation 的真实 job 恢复
  - durable backlog dedupe / close marker 副作用

## 4. 风险 / 待 Reviewer 重点检查项

- `run_phase()` waterfall 当前是 skeleton；请确认 reviewer 将重点放在顺序、门禁和扩展点，而非缺失的业务 path。
- `FileRunLockRepository` 采用本地 lock file 最小实现，满足单机互斥测试，但尚未解决 crash 后 stale lock 清理。
- `StubContractService` 为便于骨架推进返回默认 valid contract；后续接入真实 contract 校验时，需确认不改动已冻结的状态语义。
- `PhaseService._run_close_path()` 现在只提供 fake close-path 执行与 active execution 生命周期，没有提前补真实副作用。

## 5. 测试结果

- `pytest -q`
  - 结果：`358 passed`
- `python3 -m agent_orchestrator.cli.main --help`
  - 结果：CLI 顶层命令成功展示 `project` / `bootstrap` / `phase` / `approvals`

## 6. 关于重复 `update_status(BLOCKED_ON_HUMAN)` 的明确声明

- 明确声明：当前代码中不存在“调用方重复 `update_status(BLOCKED_ON_HUMAN)`”的违规链路。
- 证据：
  - `rg -n "update_status\\(.*BLOCKED_ON_HUMAN" agent_orchestrator`
  - 命中仅位于 `agent_orchestrator/application/approval_service.py`
- 结论：
  - `BLOCKED_ON_HUMAN` 切换责任仅存在于 `ApprovalService.create_contract_approval()`
  - `ApprovalService.create_close_phase_with_important_open()`
  - `ApprovalService.create_bootstrap_ready_with_important_open()`
  - `ApprovalService.create_release_ready_confirm()`

## 7. Post-Merge Archive Note

- Phase 01 代码已于 `2026-03-29` 通过 PR `#1` 合入 `main`。
- 当前 dashboard、phase 主文档与 merge summary 已完成收口；本自检文档继续保留，但用途已转为归档参考材料。
- 现阶段唯一剩余 reviewer 风险为低优先级 stale lock 残留问题，不影响 Phase 01 关闭与 Phase 02 kickoff 准备。
