# Phase 03 Codex Plan: Local Worker Execution MVP

**Last updated:** `2026-03-29 23:20:56 +0800`
**Owner:** `Codex`
**Reviewer:** `Claude Code`
**Status:** `awaiting review`

## 1. 本阶段目标

Phase 03 的目标是在不突破 Phase 01 / Phase 02 已冻结控制边界的前提下，把 orchestrator 从“最小控制链路 + stub execution”推进到“单机可运行的真实 worker 执行 MVP”。

本阶段完成后，系统至少应具备以下能力：

- 能为 bootstrap / phase 真实构造 worker job 输入，而不是只消费 planned summary。
- 能通过本地 subprocess 或等价 runner 执行 worker job，并回填退出码、stdout、stderr、artifact 路径与执行摘要。
- 能把 build / review 结果写入文件系统 artifact store，并从 artifact 读取 review payload 驱动既有 gate 路由。
- 能让 bootstrap 与 phase 至少各有一条真实执行链跑通，同时保留 stub mode 以兼容 Phase 02 测试。

## 2. In Scope

- 新建 Phase 03 coordination 文档，并把 dashboard 更新到 `phase-03` kickoff 状态。
- 在保留内存实现的前提下，为 artifact store 新增最小文件系统实现：
  - `write_text`
  - `write_json`
  - `read_text`
  - `read_json`
  - `exists`
- 建立真实 worker 执行抽象：
  - `WorkerRunner` 或等价接口
  - `SubprocessRunner` 最小实现
  - 单个 job 的输入准备、命令执行、stdout/stderr 捕获、artifact 路径回填
- 将 `SchedulerService` 从纯 planned summary 扩展为双模式：
  - `stub`
  - `local-subprocess`
- 建立最小 I/O contract：
  - job input payload
  - build artifact payload
  - review result payload
  - build / review worker 的本地可复现输入输出协议
- 打通 bootstrap 的一条真实执行链：
  - `bootstrap-repo`
  - `bootstrap-review`
  - gate 路由到 ready / human / blockers / missing artifact
- 打通 phase 的一条真实执行链：
  - `phase-build`
  - `phase-review`
  - PASS / CONDITIONAL_PASS / FAIL / invalid payload / missing artifact
- 保留并回归验证既有 guardrail：
  - run skeleton 顺序
  - approval 工厂唯一 `BLOCKED_ON_HUMAN` owner
  - repository 白名单
  - `READY_TO_CLOSE` 作为唯一 close-path 入口态
  - run lock 仍有效

## 3. Out of Scope

- 远程 worker、远程 agent 调度、外部 SaaS 编排。
- Docker / K8s / 多机调度 / 分布式 lease / 分布式锁。
- durable DB 持久化、对象存储、复杂归档策略。
- Web UI、MCP / Deep Agent 接线、企业审批系统集成。
- 复杂 prompt 模板系统、插件生态、生产级日志监控审计。
- 为了真实执行而重写现有 Phase 01 / 02 状态机、waterfall 顺序或 approval 职责。

## 4. 与 Phase 02 的衔接关系

- Phase 02 已 merged 到 `main`，并已完成 closeout；其交付是“最小控制链路 + stub execution”。
- Phase 03 不改动 Phase 02 已冻结的控制语义，只把 job 执行面从 stub 向前推进一层。
- `run_bootstrap()` / `run_phase()` 的 waterfall 顺序保持不变，仍由 service 层掌控控制流。
- `ApprovalService` 继续作为唯一 `BLOCKED_ON_HUMAN` owner；真实 worker 不直接改人审状态。
- `READY_TO_CLOSE` 继续是 close-path 唯一入口态；本轮真实执行不把 close-path 改造成新状态机分支。

## 5. 本轮真实执行 MVP 范围

### 5.1 Worker 执行抽象

- 用统一 runner 抽象描述“准备输入 -> 执行命令 -> 采集输出 -> 产出 artifact -> 回填 summary”。
- Phase 03 只做本地 subprocess runner；不引入容器、远程执行、lease 协调。
- scheduler 仍然负责 enqueue / execute / lease freshness，但 execute 允许走真实本地执行路径。

### 5.2 Contract MVP

- build-like worker 输入至少包含：
  - job metadata
  - project / phase identity
  - output artifact 目标路径
  - 上游 result_path（若存在）
- build-like worker 输出至少生成一个文本或 JSON artifact。
- review-like worker 输入至少包含：
  - 待审 artifact 路径
  - review origin stage
  - output review payload 路径
- review-like worker 输出必须是最小结构化 JSON，可被 `review_parser` 消费。
- review payload 仍以 `PASS` / `CONDITIONAL_PASS` / `FAIL` / `INVALID_FORMAT` 为权威 gate 语义。

### 5.3 Bootstrap MVP

- `bootstrap-repo` 真实生成 artifact。
- `bootstrap-review` 真实读取 bootstrap artifact，并写出结构化 review payload。
- orchestrator 从 artifact store 读取 review payload，并沿用既有 gate 路由：
  - `PASS` -> `BOOTSTRAP_READY`
  - `CONDITIONAL_PASS` -> `BLOCKED_ON_HUMAN`
  - `FAIL` -> `BLOCKED_ON_OPEN_BLOCKERS`
  - 无 artifact / 非法 payload -> `BLOCKED_ON_MISSING_ARTIFACT`
  - worker 执行失败 -> `BLOCKED_ON_WORKER_FAILURE`

### 5.4 Phase MVP

- `phase-build` 真实生成 build artifact。
- `phase-review` 真实读取 build artifact，并写出 review payload。
- PASS 路径先打通到 `READY_TO_CLOSE` / close-path / `DONE`。
- 再补 `CONDITIONAL_PASS` / `FAIL` / invalid payload / missing artifact 最小分支。
- `phase-fix-blockers` / `phase-recheck` 本轮允许继续 stub，但 contract 必须保持一致，可在后续接到同一 runner。

## 6. 文件改动计划

- 新增 `design_docs/coordination/phase-03/codex-plan.md`
- 新增 `design_docs/coordination/phase-03/codex-status.md`
- 新增 `design_docs/coordination/phase-03/codex-handoff.md`
- 更新 `design_docs/coordination/00-dashboard.md`
- 修改 `agent_orchestrator/infra/fs/artifact_store.py`
  - 增加 `FileArtifactStore`
  - 为内存实现补齐 write/read contract
- 修改 `agent_orchestrator/infra/execution/subprocess_runner.py`
  - 实现真实本地 subprocess runner
- 可能新增 `agent_orchestrator/infra/workers/*.py`
  - 放置最小本地 build / review worker 脚本或 helper
- 修改 `agent_orchestrator/application/scheduler_service.py`
  - 引入真实执行模式与 summary 回填
- 修改 `agent_orchestrator/application/bootstrap_service.py`
  - 接入 bootstrap 真实 build / review 执行链
- 修改 `agent_orchestrator/application/phase_service.py`
  - 接入 phase 真实 build / review 执行链
- 修改 `agent_orchestrator/domain/review_parser.py`
  - 使 parser 能稳健消费文件系统 artifact payload
- 如有必要修改：
  - `agent_orchestrator/domain/results.py`
  - `agent_orchestrator/domain/entities.py`
  - `agent_orchestrator/infra/workers/base.py`
- 测试新增或扩展：
  - `tests/test_artifact_store.py`
  - `tests/test_scheduler_service.py`
  - `tests/test_bootstrap_control_flow.py`
  - `tests/test_phase_control_flow.py`
  - 相关 guardrail regression tests

## 7. 测试计划

- 坚持 TDD：先写失败测试，再补最小实现。
- Artifact store：
  - 文件系统 text write/read
  - 文件系统 json write/read
  - `exists`
  - 与内存实现语义对齐
- Subprocess runner：
  - 成功执行命令
  - 非零退出码
  - stdout / stderr 捕获
  - artifact 输出路径回填
- Bootstrap 真实执行：
  - PASS
  - CONDITIONAL_PASS
  - FAIL
  - 缺失 artifact
  - 非法 payload
- Phase 真实执行：
  - build + review PASS
  - review CONDITIONAL_PASS
  - review FAIL
  - invalid payload / missing artifact
- Guardrail 回归：
  - run skeleton 顺序
  - approval 工厂职责
  - repository 白名单
  - `READY_TO_CLOSE` 唯一入口态
  - run lock

## 8. Reviewer 关注点

- 真实 runner 是否只扩 execution 面，而没有突破 Phase 01 / 02 已冻结的控制职责边界。
- stub mode 是否完整保留，既有 Phase 02 测试是否仍成立。
- artifact / payload / review parser contract 是否足够简单、可测试、可本地复现。
- bootstrap / phase 真实执行是否都真正从文件系统 artifact 读取 payload，而不是退回 planned gate。
- `BLOCKED_ON_HUMAN` 是否仍只由 approval 工厂产生，`READY_TO_CLOSE` 是否仍是唯一 close-path 入口。
