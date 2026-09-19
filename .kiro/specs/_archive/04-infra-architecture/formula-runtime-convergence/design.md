# Technical Design

## Overview

本设计将已有公式能力收敛为可执行、可写入、可回滚、可审计的运行时。核心原则：

1. ACNR 只负责规范解析，`FormulaValueLoader` 负责批量取值；
2. 求值只进入 `formula_management.engine` 所委托的单一 kernel；
3. 四个领域通过同一 `DomainMutationAdapter` 协议 prepare/apply/restore；
4. 业务值、快照、审计和 outbox 在同一事务中提交；
5. rollback 反向调用 adapter 恢复真实业务值；
6. 共享高冲突文件只由后续串行 integration task 修改。

## Parallel Agent Delivery Design

### Wave model

实现拆为“并行叶子能力 → 串行高冲突集成 → 强验收”三层：

| 层级 | 并行策略 | 文件边界 |
|---|---|---|
| Wave 0 | 最多 6 个子代理并行 | 基线测试、contracts、logic_check、reference、WpFormula service、migration/outbox 各自独占 |
| Wave 1 | 最多 5 个子代理并行 | ValueLoader 与四个 DomainMutationAdapter 各自独占，不共享 adapter 文件 |
| Wave 2–6 | 单代理串行 | engine → orchestrator → service → router → production UI 依次集成 |
| Wave 7–8 | 单代理验收收口 | PostgreSQL/Playwright → completion guard/状态更新 |

### Ownership contract

`tasks.md` 的 `Task Dependency Graph` 是子代理调度真源。每个任务必须提供：

- `dependsOn`：满足后才可启动；
- `ownerFiles`：该任务可修改的既有文件；
- `generatedFiles`：该任务唯一可创建的文件；
- `forbiddenSharedFiles`：即使发现缺口也不得修改的共享文件；
- `Validation`：代理退出前必须执行的定向验证。

调度器启动同一 Wave 前必须验证所有任务的 `ownerFiles ∪ generatedFiles` 两两不相交。`formula_runtime/adapters/__init__.py` 由 contract 任务预先创建，四个 adapter 子代理不得并发创建或修改它。迁移任务先通过 `migration_status` 获取实时版本，并且是该 Wave 唯一 migration/ORM owner。

### Serial integration boundary

以下文件禁止在并行 Wave 中修改，并按顺序由单一任务独占：

1. `formula_management/engine.py`；
2. `formula_management/draft_refresh_orchestrator.py`；
3. `draft_refresh_service.py`；
4. `routers/draft_refresh.py`。

前端共享 contract 由 UI 任务独占生成；路由任务只定义后端 Pydantic/OpenAPI contract，避免跨端文件所有权重叠。验收任务只修改测试/fixture，completion task 只修改治理脚本、CI 与 spec 状态，不回头修改生产源码。

## Architecture

```text
POST /draft-refresh
  → project ownership + role gate
  → revision fingerprint + advisory lock
  → DraftRefreshOrchestrator
  → FormulaRuntimeCoordinator
      → batch ACNR resolve
      → FormulaValueLoader.load_many
      → single formula kernel
      → DomainMutationAdapter.prepare_many
  → transaction policy
      → snapshot → apply_many → audit → outbox
  → COMMIT
  → outbox publisher → ACNR stale/invalidation

POST /draft-refresh/{run_id}/rollback
  → load snapshots in reverse order
  → adapter.restore_many + optimistic version check
  → marker/audit/outbox
  → COMMIT
```

### Transaction modes

- 默认 `all_or_nothing`：任一解析、求值、prepare 或 apply 失败，整批 rollback。
- 显式 `partial_success`：按 scope 建 savepoint；失败 scope 回滚，成功 scope 提交；响应必须列出失败项。
- 两种模式都禁止“catch 后假成功”。

## Components and Interfaces

### 1. Runtime contracts

新建 `backend/app/services/formula_runtime/contracts.py`：

```python
@dataclass(frozen=True)
class CanonicalFormulaTarget:
    domain: Literal["workpaper", "adjudication", "report", "note"]
    project_id: UUID
    year: int
    addr_id: str
    locator: Mapping[str, str]
    wp_id: UUID | None = None

@dataclass(frozen=True)
class FormulaMutation:
    target: CanonicalFormulaTarget
    before_value: JSONValue
    after_value: JSONValue
    expected_version: str | None
    source_formula_id: UUID | None
```

```python
class DomainMutationAdapter(Protocol):
    domain: str
    async def prepare_many(self, targets, values) -> list[FormulaMutation]: ...
    async def apply_many(self, mutations) -> list[AppliedMutation]: ...
    async def restore_many(self, snapshots) -> list[RestoredMutation]: ...
    async def read_versions(self, targets) -> dict[str, str]: ...
```

### 2. FormulaValueLoader

`formula_runtime/value_loader.py` 接收去重后的 canonical 地址集合，按 domain 分组并批量查询：

- `tb` 只读四表库，遵循 `get_active_filter`、借贷方向与损益发生额口径；
- `workpaper` 从结构化持久化值读取；
- `report` 按 report_type/row_code 批量读取；
- `note` 按 section/cell 批量读取。

加载结果为 `dict[addr_id, Decimal | str | None]`，同时返回 miss/ambiguous 问题。禁止引擎逐 ref 查询。

### 3. Four domain adapters

- `WorkpaperMutationAdapter`：写入实际底稿持久化载体；locator 必须含 wp_id/item/cell，校验 wp 属于 project。
- `AdjudicationMutationAdapter`：以 standard_account_code 定位 `trial_balance.audited_amount`，不接受 B5 类坐标冒充科目码。
- `ReportMutationAdapter`：以 report_type/row_code/period 定位报表值，保持 Decimal。
- `NoteMutationAdapter`：以 note_section/row/column 定位，仅允许 auto cell。

adapter 的 `prepare_many` 只读并构建 mutation；`apply_many` 才写值；`restore_many` 做 optimistic version check。

### 4. FormulaRuntimeCoordinator

新建 `formula_runtime/coordinator.py`，由 `DraftRefreshOrchestrator` 调用：

1. 收集 formula definitions 与 targets；
2. 批量 ACNR resolve + ownership/binding 校验；
3. `FormulaValueLoader.load_many` 构建 `FormulaContext`；
4. 调用 `formula_management.engine.execute_formula`；
5. 按 domain 交 adapter prepare；
6. 返回 mutation plan，不自行 commit。

### 5. Lifecycle correction

`WpFormulaService.save` 只保存定义并设置 `lifecycle_state='saved'`，不得写计算时间。成功执行并完成领域 apply 后，由 coordinator 将其更新为 `succeeded` 与 `last_computed_at=now()`；失败/rollback 不前推时间。

### 6. logic_check correction

- #2 必须比较独立毛利来源；若平台没有独立毛利行，则降为“营业收入、营业成本完整性/方向”真实检查，禁止自减自比。
- #5 比较所有者权益变动表期末与资产负债表权益，使用两个不同 REPORT addr_id。
- #7 直接判断货币资金 `>= 0`，不得把 tolerance 设为 `abs(cash)`。
- 每条规则必须有 pass/fail 负例，后端与前端降级模型等价。

### 7. Runtime reference

reference 公式保存 `reference_formula_id`，运行时递归解析当前源公式；用 visited set 防环，并返回 source_version/source_hash。源更新只更新自身 definition version，通过 outbox 标记引用方 stale，不复制 expression。

### 8. Persistence and outbox

执行时先调用 `migration_status`，基于实时最高版本创建 `V{N+1}`。迁移扩展：

- `draft_refresh_audit`：`revision_fingerprint`、`transaction_mode`、`idempotency_key`、`failure_detail`；
- `draft_refresh_snapshot`：`domain`、`target_locator`、`after_value`、`before_version`、`after_version`、`restored_at`；
- `wp_formula`：`lifecycle_state`、`definition_version`、`definition_hash`；
- 新表 `formula_runtime_outbox`：event_key unique、run_id、event_type、payload、attempts、delivered_at。

唯一约束：`(project_id, year, idempotency_key)`，防并发重复执行。

### 9. Fingerprint and concurrency

```text
revision_fingerprint = SHA256(
  project_id | year | normalized_scopes | transaction_mode |
  four_table_dataset_revision | formula_definition_revision |
  preset_revision | acnr_registry_version
)
```

事务开始后执行 `pg_advisory_xact_lock(hash(project_id, year, fingerprint))`，并由 DB unique constraint 二次保证。指纹变化才允许新运行；同指纹完成后返回 idempotent hit，进行中返回 409。

### 10. Ownership

路由角色门禁不替代 service ownership。`WpFormulaService.save/list/delete`、coordinator、每个 adapter 的 prepare/restore 均接收 project_id，并校验 wp/formula/target 归属；跨项目 reference 视为 403，不返回表达式或 locator。

### 11. API contract

`POST /api/workpapers/draft-refresh` 标准响应：

```json
{
  "status": "success|partial_success|idempotent_hit|failed",
  "run_id": "uuid",
  "transaction_mode": "all_or_nothing|partial_success",
  "affected_count": 12,
  "applied_count": 12,
  "failed_count": 0,
  "skipped_count": 0,
  "scopes": ["report"],
  "idempotent": false,
  "rollback_available": true,
  "warnings": [],
  "failures": [],
  "preset_application": {
    "preset_count": 3,
    "presetted_pages": ["report:*"],
    "pending_pages": []
  }
}
```

提供 rollback 端点，成功返回 restored_count/conflicts。前端类型置于独立 contract 文件并由契约测试与 OpenAPI schema 对比。

### 12. Production UI

`GtRefreshScopeDialog.vue` 挂到 `layouts/ThreeColumnLayout.vue`，与全局 FormulaManagerDialog 同层。宿主提供当前 projectId/year；刷新成功后触发数据失效/重载。UI 对 success/partial/failed 分色展示；失败明细不可被统一 success toast 覆盖。

## Data Models

### Execution run

沿用并扩展 `draft_refresh_audit` 作为 run：保存 fingerprint、transaction_mode、status、scopes、counts、failure_detail。`affected_count` 只等于已成功 apply 的领域 mutation 数。

### Mutation snapshot

`draft_refresh_snapshot` 保存 domain、target_locator、before_value、after_value、before_version、after_version；rollback 只在当前版本等于 after_version 时执行。

### Formula lifecycle

`wp_formula.lifecycle_state`：saved/validated/executing/succeeded/failed/stale/rolled_back。`definition_version` 单调递增，`definition_hash` 由影响执行的定义字段计算。保存定义只更新 definition 字段，不写 computed time。

### Outbox event

`formula_runtime_outbox(event_key UNIQUE, run_id, event_type, payload, attempts, delivered_at, last_error)`。publisher 使用 event_key 幂等；失败可重试。

## Correctness Properties

### Property 1: Canonical 去重解析

对任意含重复等价语法的引用集合，批量解析与加载每个 canonical 地址至多一次，结果与逐条正确解析相同。

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: 悬空引用零写入

对任意含悬空或跨项目引用的 all-or-nothing 批次，所有领域值与执行前相等。

**Validates: Requirements 2.4, 10.1, 10.2, 12.2**

### Property 3: 四领域写入 round-trip

对任意合法 mutation，adapter prepare→apply 后读值等于 after_value。

**Validates: Requirements 1.1, 1.2, 3.1, 3.2**

### Property 4: 真实回滚恒等

对任意未发生后续编辑的合法批次，rollback(apply(state)) == state，包含业务值和 marker。

**Validates: Requirements 4.1, 4.2, 4.4**

### Property 5: 保存定义不产生计算时间

对任意公式定义，save 前后 `last_computed_at` 不因保存动作前推。

**Validates: Requirements 5.1**

### Property 6: 仅成功 apply 前推计算时间

对任意成功、失败、跳过、回滚执行，只有成功 apply 的公式会前推 `last_computed_at`。

**Validates: Requirements 5.2, 5.3, 5.4**

### Property 7: logic_check 存在可失败输入

对每条内置勾稽规则，至少存在一个输入使其通过、一个输入使其失败；后端与前端降级结果一致。

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

### Property 8: reference 动态一致

对任意无环 reference 链，执行结果使用源公式当前版本；源 definition 变化后引用方结果随之变化且被标 stale。

**Validates: Requirements 7.1, 7.2, 7.4**

### Property 9: Outbox 原子性

对任意运行事务，业务写入提交当且仅当对应 outbox event 存在；事务回滚时两者均不存在。

**Validates: Requirements 8.1, 8.2**

### Property 10: Revision fingerprint 敏感性

对 fingerprint 的任一输入 revision 单独变化，输出 fingerprint 必须变化；相同输入保持确定性。

**Validates: Requirements 9.1, 9.2**

### Property 11: 并发单写者

对同 project/year/fingerprint 的任意并发请求，成功执行领域写入的 run 至多一个。

**Validates: Requirements 9.3, 9.4**

### Property 12: 事务模式守恒

all-or-nothing 模式任一失败时 applied=0；partial-success 模式 applied+failed+skipped 等于计划 mutation 总数。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

### Property 13: 项目隔离

对任意跨项目 wp/formula/reference/target，service 与 adapter 均拒绝且目标项目状态不变。

**Validates: Requirements 12.1, 12.2, 12.4**

### Property 14: 单一内核等价

任意受支持表达式经 runtime、legacy adapter 和 direct kernel 的 Decimal 结果/错误语义一致，且调用最终只进入同一 kernel。

**Validates: Requirements 11.1, 11.2**

### Property 15: API/UI 契约闭合

任意标准刷新响应都能被前端 contract 完整解析，不读取未定义字段；partial/failed 不显示 success。

**Validates: Requirements 13.2, 13.3, 13.4**

### Property 16: 强验收状态闭环

真实 PG 中 before→after→rollback 后值恢复，且同一 run_id 的 audit/snapshot/outbox 状态互相一致。

**Validates: Requirements 14.1, 14.4**

## Error Handling

| 场景 | 行为 |
|---|---|
| ACNR miss/ambiguous | prepare 前失败；all-or-nothing 零写入 |
| 跨项目目标/reference | 403，不泄露 locator/expression |
| definition/version 冲突 | 409，要求重新加载 |
| adapter apply 失败 | 默认整批回滚；partial 模式回滚当前 savepoint |
| rollback 后续人工编辑冲突 | 409，保留当前值并列出 conflict |
| outbox 发布失败 | 提交不回滚；记录 last_error 并幂等重试 |
| reference 环/悬空 | Issue + failed mutation，绝不使用旧复制 expression |
| 空 scopes | 422，不隐式扩为全量 |
| UI contract mismatch | 契约测试阻断构建，不以可选字段静默降级 |

所有 service 只 flush；commit/rollback 只在 router 或显式 transaction runner。任何 catch 都必须转化为 failure detail 或重新抛出，禁止吞错后返回 success。

## Testing Strategy

### Unit and property tests

- Hypothesis 使用全局 fast profile（`max_examples=5`, `deadline=None`）。
- P1–P16 每条有独立可定位测试；金额用 Decimal，禁止 float 比较掩盖误差。
- 查询计数测试证明 batch resolve/load 不发生逐引用 N+1。
- structural guard 扫描新增 evaluator、默认 skip、空 catch 和共享文件 ownership 漂移。

### PostgreSQL integration

使用真实 PostgreSQL 测试事务，至少覆盖：

1. 四领域各一条 auto_calc 真写入；
2. all-or-nothing 中间失败整批零写入；
3. partial-success 的成功/失败守恒；
4. before→after→rollback round-trip；
5. 并发相同 fingerprint 仅一 writer；
6. outbox 与业务写入同事务。

### Frontend and Playwright

- Vitest 验证共享 response contract、production host 挂载和失败态展示。
- Playwright 不默认 skip；测试项目与五角色 fixture 在前置脚本创建或读取显式环境变量，不得全部回退 admin。
- 核心路径禁止 `.catch(() => {})`、`if visible then click else pass`。
- 浏览器执行一次真实刷新，断言 response、UI counts、刷新后值；随后 rollback 并断言恢复；console error 为 0。

### Completion gate

只有以下全部成立才允许 Task 18 更新为完成：所有叶子 `[x]`、定向/PBT/PG integration 通过、Playwright 通过、single-kernel 与 no-skip guard 通过。旧 spec 的完成标记不能作为本 spec 的证据。
