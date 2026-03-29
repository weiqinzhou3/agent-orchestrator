# Phase 01: Gates and Skeleton

## 1. 目标

在不扩展 `agent-orchestrator Spec v1.2` 与 `agent-orchestrator Interface Design v1.2` 语义的前提下，先建立最小但正确的工程骨架、状态机门禁、运行骨架与本地锁实现，为后续 phase 业务路径补全提供稳定底座。

## 2. In Scope

- 建立 Python 工程骨架与 `agent_orchestrator/` 包目录：
  - `cli/`
  - `application/`
  - `domain/`
  - `infra/`
- 提供 main CLI 入口与子命令挂接占位：
  - `project`
  - `bootstrap`
  - `phase`
  - `approvals`
- 落地基础领域定义：
  - `ProjectStatus`
  - `PhaseStatus`
  - `JobStatus`
  - `GateDecisionType`
  - `ReviewOriginStage`
  - `BootstrapResumeStage`
  - `PhaseResumeStage`
  - `ApprovalType`
  - `ApprovalStatus`
  - errors / entities / results
- 落地状态机白名单：
  - `ALLOWED_PROJECT_TRANSITIONS`
  - `ALLOWED_PHASE_TRANSITIONS`
- 落地 repository 门禁：
  - `ProjectRepository.update_status()` 白名单校验
  - `PhaseRepository.update_status()` 白名单校验
- 落地 application service guard：
  - `ProjectService.on_phase_done()`
  - `ProjectService.advance()`
- 落地 `run_bootstrap()` / `run_phase()` 的骨架与固定顺序：
  1. acquire lock
  2. reconcile inflight
  3. normalize failed entry
  4. waterfall
- 落地 `RunLockRepository` 最小可用实现，优先满足本地互斥与可测试性。
- 落地 `ApprovalService.create_*()` 工厂职责：
  - approval 创建
  - 关联写入
  - 阻塞态切换
  - 统一携带 `related_files` / `origin_stage` / `approval_type`
- 为 close-path 预留幂等参数位：
  - `dedupe_scope`
  - `close_marker`
- 落地 close-path active execution 的最小 stub 行为：
  - `APPEND_BACKLOG`
  - `CLOSE_PHASE`
  - set / clear active execution
  - fake job id 占位
- 补最小测试，覆盖门禁、顺序与锁行为。

## 3. Out of Scope

- 真实 worker 调度、artifact 解析、review parser、prompt 渲染与 subprocess 执行。
- bootstrap repo/review、phase build/review/fix/recheck/close 的完整业务实现。
- 数据库持久化、远程锁、分布式 lease 与多进程外部协调。
- backlog item 指纹生成、close marker 落库的最终幂等实现。
- close-path 与 review/build/fix/recheck 的真实 job 持久化与 worker 执行。
- 真实审批流 UI、外部通知、审计报表。
- 超出 v1.2 文档定义的新增状态、新增命令语义或额外恢复路径。

## 4. 设计约束

- 严格遵守 v1.2 文档，不得自行改写状态名、入口态、恢复语义与 approval 语义。
- `run_bootstrap()` / `run_phase()` 只能按以下顺序组织：
  1. acquire lock
  2. reconcile inflight
  3. normalize failed entry
  4. waterfall
- waterfall 必须保留连续推进能力，不能改成互斥 `elif` 分支模型。
- `READY_TO_CLOSE` 不新增 phase 状态；close-path 通过 `PhaseResumeStage.APPEND_BACKLOG` 与 `PhaseResumeStage.CLOSE_PHASE` 表达 active execution。
- `ApprovalService.create_*()` 是 approval 创建与 `BLOCKED_ON_HUMAN` 切换的唯一责任方；调用方不得重复执行同一阻塞态更新。
- `ProjectService.on_phase_done()` 必须保留 application guard；repository 白名单校验同时保留。
- `RunLockRepository` 不是可选项；phase-01 必须能验证同 scope 互斥。
- 仅实现骨架与门禁，不提前补业务细节。

## 5. 文件改动计划

- 新增 `pyproject.toml`：定义最小 Python 项目与测试依赖。
- 新增 `.gitignore`：忽略缓存、测试输出与系统文件。
- 新增 `agent_orchestrator/cli/`：
  - `main.py`
  - `project.py`
  - `bootstrap.py`
  - `phase.py`
  - `approvals.py`
- 新增 `agent_orchestrator/application/`：
  - `bootstrap_service.py`
  - `phase_service.py`
  - `project_service.py`
  - `approval_service.py`
  - `contract_service.py`
  - `scheduler_service.py`
- 新增 `agent_orchestrator/domain/`：
  - `enums.py`
  - `entities.py`
  - `results.py`
  - `errors.py`
  - `state_machine.py`
  - `validators.py`
  - `recovery.py`
  - `review_parser.py`
- 新增 `agent_orchestrator/infra/`：
  - `db/repositories.py`
  - `fs/run_locks.py`
  - `fs/artifact_store.py`
  - `config/loader.py`
  - `execution/subprocess_runner.py`
  - `prompts/jinja_renderer.py`
  - `workers/base.py`
- 新增 `tests/`：
  - 状态机与 repository 白名单测试
  - `ProjectService` guard 测试
  - `ApprovalService` 唯一阻塞态职责测试
  - `PhaseService` / `BootstrapService` 固定调用顺序测试
  - `RunLockRepository` scope 互斥测试
- 新增 `design_docs/reviews/phase-01-codex-self-review.md`：本轮自检报告。
- 更新 `design_docs/coordination/00-dashboard.md`：记录 phase-01 状态。

## 6. 测试计划

- 先写失败测试，再写最小实现。
- 单元测试覆盖以下最小门禁：
  - repository 白名单接受全部合法 project/phase 状态跳转。
  - repository 白名单拒绝非法 project/phase 状态跳转。
  - `ProjectService.on_phase_done()` 在 `project.status != PHASE_ACTIVE` 时拒绝推进。
  - `ProjectService.advance()` 支持 `BOOTSTRAP_READY -> RELEASE_READY` 空 phase plan 边缘路径。
  - `ApprovalService.create_*()` 完成 approval 创建与阻塞态切换，调用方不需要也不允许重复切换。
  - `PhaseService` contract caller 与 `ProjectService.request_close()` 不重复执行 `BLOCKED_ON_HUMAN`。
  - `run_bootstrap()` 顺序固定为 lock -> inflight -> normalize -> waterfall。
  - `run_phase()` 顺序固定为 lock -> inflight -> normalize -> waterfall，且 close-path 活动阶段保留接口位。
  - `RunLockRepository` 对相同 project 或 `(project, phase)` scope 实现互斥，第二次获取快速失败。
  - service 级 `bootstrap run` / `phase run` 并发进入同一 scope 时快速失败。
  - close-path `APPEND_BACKLOG` / `CLOSE_PHASE` 能设置并清理 active execution。
- CLI 做最小冒烟测试：
  - `python -m agent_orchestrator.cli.main --help`
  - 子命令解析不报错。

## 7. 验收标准

- 仓库存在最小可运行 Python 工程骨架，目录与接口设计文档一致。
- 枚举、实体、结果对象、错误类型齐备，命名与文档一致。
- `ALLOWED_PROJECT_TRANSITIONS` 与 `ALLOWED_PHASE_TRANSITIONS` 已落地并被 repository 使用。
- repository `update_status()` 实际执行白名单校验。
- `ProjectService` 保留显式 guard，不依赖 repository 单层防护。
- `run_bootstrap()` / `run_phase()` 的实现与测试共同证明固定顺序未被改变。
- `RunLockRepository` 最小本地实现可通过互斥测试。
- `ApprovalService.create_*()` 是唯一执行阻塞态切换的入口，测试能证明不存在外层重复 `update_status(BLOCKED_ON_HUMAN)`。
- `READY_TO_CLOSE` 不新增 phase 状态，但 close-path 接口包含 `APPEND_BACKLOG` / `CLOSE_PHASE` 与 `dedupe_scope` / `close_marker` 预留位。
- close-path 最小 stub 已能设置/清理 active execution，并为 stale reconciliation 与幂等重跑保留测试入口。
- phase-01 文档、dashboard、自检报告均已更新。

## 10. 当前实现状态

### 10.1 已完成

- phase-01 门禁、骨架、状态机、repository 白名单、application guard 已落地。
- `run_bootstrap()` / `run_phase()` 固定顺序已由测试锁定。
- 四类 approval 工厂职责已落地，并有测试证明 `BLOCKED_ON_HUMAN` 不会被调用方重复切换。
- close-path active execution 已具备最小 stub 逻辑，可设置/清理 `APPEND_BACKLOG` 与 `CLOSE_PHASE`。
- 当前验证结果为 `pytest -q` 全量 `358 passed`。

### 10.2 故意延后到 phase-02 之后

- 真实 worker 集成、artifact 产物校验与 review payload 解析。
- `JobRepository` / `PhaseGateSnapshotRepository` 的真实持久化与 lease 管理。
- stale reconciliation 的真实 job 级恢复细节。
- close-path 去重键、close marker 的真实幂等副作用与持久化。
- CLI 到真实容器装配、配置加载与外部依赖接线。

## 8. 风险点

- 当前仓库无既有工程基线，phase-01 需要同时确定包结构、测试框架与最小内存仓储实现，存在路径命名偏差风险。
- 文件锁实现只能覆盖本地单机语义；后续若迁移到数据库锁，接口必须保持兼容。
- 由于本轮只做骨架，部分 service 方法会以 stub 形式存在，reviewer 需区分“未实现业务”与“门禁缺失”。
- close-path 幂等仅预留参数位，真正的幂等持久化要在后续阶段补齐。

## 9. Reviewer 关注点

- 状态名、入口态、恢复顺序是否与两份 v1.2 文档逐项一致。
- repository 白名单校验与 application guard 是否双层同时存在。
- `run_phase()` 是否错误使用 `elif`，破坏 waterfall 连续推进能力。
- 是否遗漏 `RunLockRepository` 或把锁实现降级成无测试占位。
- 是否存在调用方重复 `update_status(BLOCKED_ON_HUMAN)` 的违规链路。
- `READY_TO_CLOSE` 是否被错误扩展成新的 phase 状态，或被当成纯静态状态忽略 active execution。
