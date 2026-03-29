# agent-orchestrator Spec v1.2

**Status:** Draft  
**Version:** v1.2  
**Supersedes:** v1.1

---

## 1. 文档目标

v1.2 在 v1.1 基础上继续收口“approval 工厂职责”和项目级边缘路径。这一版重点修正 4 个会直接影响运行时正确性的点：

1. 明确 `ApprovalService.create_*()` 是 **approval 创建 + 状态切换** 的唯一责任方，调用方不得重复执行同一阻塞态更新；
2. 让 `ApprovalService` 的公开签名、调用方传参、repository 接口重新完全一致；
3. 补齐 `BOOTSTRAP_READY -> RELEASE_READY` 的合法边缘路径，用于“bootstrap 存在但 phase plan 为空”的项目；
4. 再次强调 `ProjectService.on_phase_done()` 与 repository `update_status()` 都必须执行状态机白名单校验。

---

## 2. v1.2 拍板结论

### 2.1 phase 失败恢复仍采用“入口归一化 + waterfall”

`phase run` 的高层控制流保持不变：

1. 先校验入口是否合法；
2. 若当前处于执行中状态，则先做 **inflight reconciliation**；
3. 若当前处于失败阻塞态，则先做 **failed-entry normalization**；
4. 归一化完成后，再进入统一 waterfall 主链。

> 失败恢复只负责把状态翻译回一个“正常入口态”，**不直接执行业务 path**。

### 2.2 review-only / recheck-only 继续作为一等恢复路径

`REVIEW` 失败恢复必须回到 `REVIEW_PENDING`；  
`RECHECK` 失败恢复必须回到 `RECHECK_PENDING`；  
不能再把这两类恢复粗暴回退到 `BUILD` 或 `FIX_BLOCKERS`。

### 2.3 `PhaseGateSnapshotRepository` 与 `PhaseGateSnapshot` 仍是权威 gate 来源

恢复、close-path、fix-blockers 的输入都优先读取最近一次 `PhaseGateSnapshot`。  
artifact 文件继续作为：

- 审计证据；
- 原始结构化 payload；
- must-fix / backlog 生成时的补充上下文。

### 2.4 project 状态继续保持粗粒度

`project.status` 只表达项目级阶段，不镜像 phase 的每一次阻塞。  
phase 级阻塞、失败、审批等待都应通过：

- `current_phase`
- `current_phase.status`
- pending approvals
- 最近失败上下文

来展示，而不是强行上浮到 `project.status`。

### 2.5 bootstrap 也必须支持 inflight / stale reconciliation

以下 project 状态既是“执行中态”，也是 `bootstrap run` 的合法入口：

- `BOOTSTRAP_RUNNING`
- `BOOTSTRAP_REVIEW_PENDING`

当 orchestrator 在 bootstrap 期间被 kill、OOM、机器重启或人工中断时，下一次 `bootstrap run` 必须先判断：

- active job 是否仍在运行；
- 还是一个 stale / interrupted inflight job。

若确认 stale / interrupted，则 project 必须先进入：

- `BLOCKED_ON_WORKER_FAILURE` 或
- `BLOCKED_ON_MISSING_ARTIFACT`

并记录失败恢复上下文，再进入标准恢复链路。

### 2.6 close-path 必须显式跟踪 active execution

虽然 close-path 不再引入新的 phase 状态，但以下逻辑阶段必须被持久化为 active execution：

- `APPEND_BACKLOG`
- `CLOSE_PHASE`

其目的有两个：

1. 在 job 仍活跃时阻止第二个调用并发进入；
2. 在 crash 后知道“上次到底跑到了 close-path 的哪一步”。

### 2.7 close-path 的 job 必须幂等

`append-backlog` 与 `close-phase` 必须按幂等方式实现。  
至少满足：

- `append-backlog` 不能因为重入而产生重复 backlog 项；
- `close-phase` 重入不会重复写出冲突性的关闭副作用。

推荐做法：

- `append-backlog` 使用 `(project, phase, gate_snapshot_id, item_fingerprint)` 作为去重键；
- `close-phase` 使用 `phase_name` + `close marker` 做幂等检测。

### 2.8 phase run 的合法入口态必须与 v0.9 的 stale 结论一致

以下 phase 状态既是执行中态，也是 `phase run` 的合法入口态：

- `BUILDING`
- `REVIEW_PENDING`
- `BLOCKER_FIXING`
- `RECHECK_PENDING`

本结论对 spec 与 interface design 同时生效，不允许再出现“正文一个说法、入口表另一个说法”的情况。

### 2.9 bootstrap 默认“就地修复后复审”，但必须支持 `--force-full`

当 bootstrap 因 review `FAIL` 而进入 `BLOCKED_ON_OPEN_BLOCKERS` 时：

- 默认恢复策略：Human Owner 已直接修复 bootstrap 产物，因此下一次 `bootstrap run` 默认回到 `BOOTSTRAP_REVIEW_PENDING`；
- 若 Human Owner 修改的是 design docs / 模板 / 输入材料，则必须通过 `--force-full` 强制从 `bootstrap-repo` 全量重跑。

### 2.10 当前版本必须提供单 scope 互斥保证

v1.0 不允许同一时刻有两个 orchestrator run 同时操作同一个 scope：

- `bootstrap run` 的 scope = `project`
- `phase run` 的 scope = `(project, phase)`

实现上至少要提供一种 advisory lock 机制（数据库锁、文件锁或等价实现）。  
若当前 scope 已被另一个调用持有锁，本次命令必须快速失败并提示“已有运行中的实例”。


### 2.11 approval 工厂是阻塞态切换的唯一责任方

以下 approval 工厂方法一旦成功返回，就必须已经完成对应的状态切换：

- `create_contract_approval(...)`：phase -> `BLOCKED_ON_HUMAN`
- `create_close_phase_with_important_open(...)`：phase -> `BLOCKED_ON_HUMAN`
- `create_bootstrap_ready_with_important_open(...)`：project -> `BLOCKED_ON_HUMAN`
- `create_release_ready_confirm(...)`：project -> `BLOCKED_ON_HUMAN`

调用方不得在 `create_*()` 返回后再次重复执行同一状态更新。  
重复执行 `BLOCKED_ON_HUMAN -> BLOCKED_ON_HUMAN` 这类自跳转会破坏状态机白名单，是实现错误，不是可接受冗余。

---

## 3. 生命周期状态

### 3.1 Project 状态

- `INIT`
- `DESIGN_READY`
- `BOOTSTRAP_RUNNING`
- `BOOTSTRAP_REVIEW_PENDING`
- `BOOTSTRAP_READY`
- `PHASE_ACTIVE`
- `PHASE_DONE`
- `RELEASE_READY`
- `CLOSED`
- `BLOCKED_ON_HUMAN`
- `BLOCKED_ON_OPEN_BLOCKERS`
- `BLOCKED_ON_MISSING_ARTIFACT`
- `BLOCKED_ON_WORKER_FAILURE`

### 3.2 Phase 状态

- `NOT_STARTED`
- `CONTRACT_VALIDATED`
- `CONTRACT_APPROVED`
- `BUILDING`
- `REVIEW_PENDING`
- `BLOCKER_FIXING`
- `RECHECK_PENDING`
- `READY_TO_CLOSE`
- `DONE`
- `BLOCKED_ON_HUMAN`
- `BLOCKED_ON_OPEN_BLOCKERS`
- `BLOCKED_ON_MISSING_ARTIFACT`
- `BLOCKED_ON_WORKER_FAILURE`

说明：`BUILDING`、`REVIEW_PENDING`、`BLOCKER_FIXING`、`RECHECK_PENDING` 既是执行中状态，也是失败恢复与 stale reconciliation 的合法入口态。  
说明：`BOOTSTRAP_RUNNING`、`BOOTSTRAP_REVIEW_PENDING` 既是执行中状态，也是 bootstrap 失败恢复与 stale reconciliation 的合法入口态。

---

## 4. Approval 类型

- `CONTRACT_APPROVAL`
- `SCOPE_CHANGE`
- `CLOSE_PHASE_WITH_IMPORTANT_OPEN`
- `BOOTSTRAP_READY_WITH_IMPORTANT_OPEN`
- `RELEASE_READY_CONFIRM`

---

## 5. 失败恢复与执行中断上下文

v1.0 在 v0.9 的基础上，把 **active execution context** 扩展到 bootstrap 与 close-path。  
系统至少要持久化两类上下文：project 级与 phase 级。

### 5.1 project active execution / 恢复上下文

project 至少要持久化：

- `active_bootstrap_job_id`
- `active_bootstrap_stage`（`BOOTSTRAP_REPO` / `BOOTSTRAP_REVIEW`）
- `active_bootstrap_started_at`
- `last_failed_bootstrap_stage`
- `last_failed_job_id`
- `last_failed_result_path`
- `last_failed_reason`

### 5.2 phase active execution / 恢复上下文

phase 至少要持久化：

- `active_job_id`
- `active_stage`
  - `BUILD`
  - `REVIEW`
  - `FIX_BLOCKERS`
  - `RECHECK`
  - `APPEND_BACKLOG`
  - `CLOSE_PHASE`
- `active_job_started_at`
- `last_failed_stage`
  - `BUILD`
  - `REVIEW`
  - `FIX_BLOCKERS`
  - `RECHECK`
  - `APPEND_BACKLOG`
  - `CLOSE_PHASE`
- `last_failed_job_id`
- `last_failed_result_path`
- `last_failed_reason`

### 5.3 job 心跳 / 租约上下文

job 至少要持久化：

- `status`
- `last_heartbeat_at`
- `result_path`（如有）
- `updated_at`

### 5.4 恢复原则

1. 恢复逻辑必须先做**入口归一化**，再进入统一 waterfall 主线；
2. 恢复上下文缺失时，命令必须报错，不能盲猜恢复点；
3. 恢复应尽量精确，避免无意义地回退到更早步骤；
4. 同一次调用内，恢复归一化完成后，允许继续跑完后续多步；
5. inflight / stale reconciliation 必须先于 failed-entry normalization 执行；
6. close-path 的 active execution 与 build/review/fix/recheck 一样，属于恢复的一部分，而不是“纯日志字段”。

---

## 6. Bootstrap 主线

### 6.1 允许入口状态

`bootstrap run` 允许从以下状态进入：

- `DESIGN_READY`
- `BOOTSTRAP_RUNNING`
- `BOOTSTRAP_REVIEW_PENDING`
- `BLOCKED_ON_OPEN_BLOCKERS`
- `BLOCKED_ON_WORKER_FAILURE`
- `BLOCKED_ON_MISSING_ARTIFACT`

### 6.2 bootstrap run 的统一控制流

`bootstrap run` 的高层执行顺序为：

1. 获取 project 级互斥锁；
2. 读取当前 project；
3. 若当前是执行中态，则先做 **bootstrap inflight reconciliation**；
4. 若当前是失败阻塞态，则先做 **bootstrap failed-entry normalization**；
5. 然后进入 bootstrap waterfall：
   - repo
   - review

因此，bootstrap 侧与 phase 侧一样，采用“先归一化，再连续推进”的统一模型。

### 6.3 默认恢复策略

- `BLOCKED_ON_WORKER_FAILURE` / `BLOCKED_ON_MISSING_ARTIFACT`：按失败上下文恢复；
- `BLOCKED_ON_OPEN_BLOCKERS`：
  - 默认 -> `BOOTSTRAP_REVIEW_PENDING`
  - `--force-full` -> 从 `BOOTSTRAP_REPO` 全量重跑
- `BOOTSTRAP_RUNNING` / `BOOTSTRAP_REVIEW_PENDING`：
  - 若 active job lease 新鲜 -> 视为已有 bootstrap 正在运行，拒绝本次调用；
  - 若 active job stale / interrupted -> 先翻译成失败阻塞态，再进入标准恢复链路。

### 6.4 正常路径

1. project -> `BOOTSTRAP_RUNNING`
2. 执行 `bootstrap-repo`
3. project -> `BOOTSTRAP_REVIEW_PENDING`
4. 执行 `review-bootstrap`
5. 根据 gate 决策：
   - `PASS` -> `BOOTSTRAP_READY`
   - `CONDITIONAL_PASS` -> 创建 approval，project -> `BLOCKED_ON_HUMAN`
   - `FAIL` -> `BLOCKED_ON_OPEN_BLOCKERS`
   - `INVALID_FORMAT` -> `BLOCKED_ON_MISSING_ARTIFACT`

---

## 7. Phase 主线

### 7.1 允许入口状态

`phase run` 允许从以下状态进入：

- `NOT_STARTED`
- `CONTRACT_VALIDATED`
- `CONTRACT_APPROVED`
- `BUILDING`
- `REVIEW_PENDING`
- `BLOCKER_FIXING`
- `RECHECK_PENDING`
- `READY_TO_CLOSE`
- `BLOCKED_ON_OPEN_BLOCKERS`
- `BLOCKED_ON_WORKER_FAILURE`
- `BLOCKED_ON_MISSING_ARTIFACT`

### 7.2 phase run 的统一控制流

v1.0 明确规定，`phase run` 的高层执行顺序为：

1. 获取 `(project, phase)` 级互斥锁；
2. 读取当前 phase；
3. 若当前是执行中态，则先做 **inflight reconciliation**；
4. 若当前处于 `READY_TO_CLOSE` 且存在 close-path active execution，则先做 close-path inflight reconciliation；
5. 若当前是失败阻塞态，则先做 **恢复入口归一化**；
6. 然后进入 waterfall 主链；
7. waterfall 主链允许在一次调用内连续推进：
   - 合同
   - build
   - review
   - fix
   - recheck
   - close

因此，waterfall 结构是**有意的连续推进链**，不是互斥分支。

### 7.3 gate 决策路由

在 review 或 recheck 之后：

- `PASS` -> `READY_TO_CLOSE`
- `CONDITIONAL_PASS` -> 创建 approval，phase -> `BLOCKED_ON_HUMAN`
- `FAIL` -> `BLOCKED_ON_OPEN_BLOCKERS`
- `INVALID_FORMAT` -> `BLOCKED_ON_MISSING_ARTIFACT`

### 7.4 review-like 路径的失败收口

`review-only` 与 `recheck-only` 路径必须与 `build` / `fix-blockers` 路径一样，显式处理“worker 本身失败 / 产物缺失”：

- 若 review-like job 没有返回 `gate_decision`：
  - `artifact_validation.passed = False` -> `BLOCKED_ON_MISSING_ARTIFACT`
  - 否则 -> `BLOCKED_ON_WORKER_FAILURE`
- 失败恢复阶段按来源映射：
  - `PHASE_REVIEW` -> `PhaseResumeStage.REVIEW`
  - `PHASE_RECHECK` -> `PhaseResumeStage.RECHECK`
- 一次性 `recheck-format` 任务若自身失败，也按同一规则收口。

这意味着：
- `gate_decision is None` 绝不是允许继续调用 gate router 的结果；
- 任何“无 gate 的 review-like 执行结果”都必须先转成显式阻塞态。

### 7.5 `CONDITIONAL_PASS` 被 reject 后的语义

当 approval type = `CLOSE_PHASE_WITH_IMPORTANT_OPEN` 被 reject：

- phase -> `BLOCKED_ON_OPEN_BLOCKERS`
- 最近一次 gate snapshot 中的 `important_items` 被视作 must-fix 输入
- 下一次 `phase run` 进入 fix + recheck 路径

### 7.6 `INVALID_FORMAT` 的一次性修复

如 review / recheck 的输出为 `INVALID_FORMAT`：

- orchestrator 允许触发一次 `phase-recheck-format` 内部修复 job；
- 若修复成功，以修复后的结果继续路由；
- 若修复仍然非法，则记录为失败恢复上下文并进入 `BLOCKED_ON_MISSING_ARTIFACT`。

恢复阶段必须依赖来源：

- 来自 review -> `REVIEW`
- 来自 recheck -> `RECHECK`

### 7.7 需整改项提取

fix-blockers worker 的输入必须来自最近一次 `PhaseGateSnapshot`：

- `FAIL` snapshot -> 读取 blockers；
- `CONDITIONAL_PASS` + reject 回流 -> 只有在确认对应 approval 为 `CLOSE_PHASE_WITH_IMPORTANT_OPEN` 且状态为 `REJECTED` 时，才读取 `important_items` 并提升为 must-fix；
- 这份“需整改项清单”必须作为明确上下文传给 fix-blockers worker，而不是让 worker 自行猜测。

### 7.8 close-path

当 phase = `READY_TO_CLOSE` 时：

1. orchestrator 可按配置决定是否先执行 `append-backlog`；
2. 然后执行 `close-phase`；
3. `append-backlog` 与 `close-phase` 都必须写入 active execution；
4. 这两个 job 必须幂等，允许因为 crash / stale reconciliation / 人工重试而被安全重入。

---

## 8. Project 推进

### 8.1 phase 完成后的 project 推进

`close-phase` 成功后：

1. phase -> `DONE`
2. `PhaseService` 必须调用 `ProjectService.on_phase_done(project_name, phase_name)`
3. `on_phase_done()` 必须先校验 `project.status == PHASE_ACTIVE`
4. 校验通过后 project -> `PHASE_DONE`

> 该 guard 不能省略。即使 repository 层也实现了状态机白名单校验，application service 仍应做显式防御。

### 8.2 显式项目级动作

#### `project advance`

`project advance` 必须接受两个入口态：

- `BOOTSTRAP_READY`
- `PHASE_DONE`

当 project = `BOOTSTRAP_READY`：

- 读取项目 phase plan 的第一项
- 若存在第一 phase：
  - 设置 `current_phase = first_phase`
  - project -> `PHASE_ACTIVE`
- 若 phase plan 为空：
  - 清空 `current_phase`
  - project -> `RELEASE_READY`

当 project = `PHASE_DONE`：

- 若存在下一 phase -> 设置 `current_phase = next_phase`，project -> `PHASE_ACTIVE`
- 否则 -> `RELEASE_READY`，并清空 `current_phase`

#### `project request-close`

当 project = `RELEASE_READY`：

- 创建 `RELEASE_READY_CONFIRM` approval
- project -> `BLOCKED_ON_HUMAN`

审批通过：
- project -> `CLOSED`

审批拒绝：
- project -> `RELEASE_READY`

---

## 9. project 粗粒度状态与并发边界说明

### 9.1 project 仍是粗粒度状态机

v1.1 继续采用以下设计边界：

- project 只表达“项目级阶段”；
- phase 表达“执行级细粒度状态”；
- project 不镜像 phase 的每一次阻塞或失败。

因此，在 `PHASE_ACTIVE` 期间：

- 可能实际存在 `phase.BLOCKED_ON_HUMAN`
- 可能实际存在 `phase.BLOCKED_ON_WORKER_FAILURE`
- 可能实际存在 `phase.BLOCKED_ON_MISSING_ARTIFACT`

`project status` 输出应至少包含：

- project.status
- current_phase
- current_phase.status
- 若存在 pending approval，也应一并展示

### 9.2 当前版本的并发边界

v1.1 的设计前提是：同一 scope 同一时刻只允许一个执行实例。

- `bootstrap run`：按 project 互斥
- `phase run`：按 `(project, phase)` 互斥

如果无法拿到 scope 锁，命令必须快速失败，而不是乐观地继续执行。  
stale reconciliation 解决的是“上一次执行中断或失联”的问题；  
scope 互斥解决的是“两个新调用同时起跑”的问题。  
两者不可互相替代。

---

## 10. CLI

```bash
agent-orchestrator project status --project <name>
agent-orchestrator project advance --project <name>
agent-orchestrator project request-close --project <name>

agent-orchestrator bootstrap run --project <name>
agent-orchestrator bootstrap run --project <name> --force-full

agent-orchestrator phase run --project <name> --phase <phase_name>

agent-orchestrator approvals approve --project <name> --id <approval_id> --actor <actor_name>
agent-orchestrator approvals reject --project <name> --id <approval_id> --actor <actor_name>
```

---

## 11. 本版最重要的实现提醒

1. 不要把失败恢复写成另一套业务主链；
2. 不要把 inflight reconciliation 和 failed-entry normalization 的顺序写反；
3. 不要让 bootstrap 缺失与 phase 对等的 stale recovery；
4. 不要让 `append-backlog` 在重入时生成重复 backlog 项；
5. 不要把 `READY_TO_CLOSE` 的 active execution 当成“可有可无的日志字段”；
6. 不要假设 stale reconciliation 能替代 scope 互斥锁；
7. `bootstrap run --force-full` 必须真实生效，而不是只是 CLI 占位符。
