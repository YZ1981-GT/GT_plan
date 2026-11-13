# 账套导入单位归一开发指南

> **spec**: `platform-global-display-settings-closure` 任务 12B（阶段 B 账套导入单位文档）。
> 屏幕显示偏好见 [`docs/frontend/display-preferences.md`](../frontend/display-preferences.md)（任务 12A）。
> 正式导出单位策略见 [`docs/reference/formal-export-unit-policy.md`](formal-export-unit-policy.md)（任务 12C）。

---

## 1. 账套导入入口闭集

平台所有账套导入相关端点被划分为五类，以可执行注册表 `LEDGER_IMPORT_ENTRYPOINTS` 维护闭集。注册表从真实 `app.routes` 反查 ImportJob 创建、四表/科目表 writer、active 切换与恢复入口，双向校验——未登记的旁路使守卫失败。

### 1.1 preview / detect（只读预览）

| 端点 | 方法 | 路由 | 鉴权 | 说明 |
|------|------|------|------|------|
| 科目表预览 | POST | `/api/projects/{project_id}/account-chart/preview` | `require_project_access('edit')` | 预览上传文件的表头与前 N 行 |
| 账套预览 | POST | `/api/projects/{project_id}/ledger/smart-preview` | `require_project_access('edit')` | 智能预览账套文件（表头检测、行数估算） |
| 导入检测 | POST | `/api/projects/{project_id}/ledger-import/detect` | `require_project_access('edit')` | 上传文件后首次检测，返回 `UnitDetectionSummary` |
| 导入预览 | POST | `/api/projects/{project_id}/import/preview` | `require_project_access('edit')` | 兼容导入预览 |
| 增量检测 | POST | `/api/projects/{project_id}/ledger-data/incremental/detect` | `require_project_access('edit')` | 返回当前 active 的 `base_dataset_id` + `base_unit_contract_digest` + 检测到的 `file_periods` |

所有 preview/detect 端点都需要当前路径项目的 `edit` 权限，仅登录态不可读取或创建其他项目的导入证据。

### 1.2 已退役的同步 POST（固定返回 410）

以下两个同步导入端点没有生产前端调用方，已在项目 `edit` 鉴权后固定退役：

| 端点 | 方法 | 路由 | 返回 |
|------|------|------|------|
| 科目表同步导入 | POST | `/api/projects/{project_id}/account-chart/import` | `410 LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB` |
| 全量同步导入 | POST | `/api/projects/{project_id}/import` | `410 LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB` |
| 增量覆盖 | POST | `/api/projects/{project_id}/ledger-data/incremental/apply` | `410 INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB` |

退役路由**不再导入或调用**旧的 `run_account_chart_import`、`import_service.start_import/start_import_streaming`、四表 writer 或 ImportJob 创建函数。410 响应 detail 固定为：

```json
{
  "code": "LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB",
  "message": "账套导入已迁移到单位确认作业，请重新预览并提交"
}
```

增量覆盖退役响应：

```json
{
  "code": "INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB",
  "message": "增量覆盖已并入导入作业，请重新上传并提交"
}
```

### 1.3 三条正式 submit（单位确认作业）

| 端点 | 方法 | 路由 | 鉴权 | 说明 |
|------|------|------|------|------|
| v2 JSON 提交 | POST | `/api/projects/{project_id}/ledger-import/submit` | `require_project_access('edit')` | v2 结构化提交 |
| 科目表异步 | POST | `/api/projects/{project_id}/account-chart/import-async` | `require_project_access('edit')` | 兼容异步导入，显式传 `incremental_plan=None` |
| 账套智能导入 | POST | `/api/projects/{project_id}/ledger/smart-import` | `require_project_access('edit')` | 从 Form JSON 解析增量计划 |

三条 submit 共用同一个无默认值的 `UnitConfirmationInput` 和服务端合同构造 helper（`build_confirmed_unit_contract`），在建锁/job 前重算 bundle hash、检测摘要和 digest。

**兼容入口行为**：当 `account-chart/import-async` 或 `ledger/smart-import` 收到直接上传的文件但没有 `upload_token + evidence_digest` 时：

1. 只落不可变 bundle（`create_bundle`，含逐文件 SHA-256）。
2. 返回 `428 SOURCE_UNIT_CONFIRMATION_REQUIRED`：

```json
{
  "code": "SOURCE_UNIT_CONFIRMATION_REQUIRED",
  "message": "请确认账套金额单位后重新提交",
  "upload_token": "<token>",
  "unit_detection": { ... }
}
```

该分支**不取队列锁、不创建 ImportJob、不触碰四表**。

### 1.4 status（只读查询）

status 端点只允许纯读，按 task/batch 反查项目后以 `readonly` 门放行。

### 1.5 recovery（受控恢复）

recovery 端点只允许 cancel/retry/rollback 已有作业，**不得接收新文件或新金额值**，必须验证对象属于路径项目并走 `edit` 门。

### 1.6 入口闭集注册表

`LEDGER_IMPORT_ENTRYPOINTS` 以 `app.routes` 中注册的 endpoint 身份为输入，为每条 route 标记分类：

| 分类 | 允许操作 |
|------|---------|
| `preview` | 只读预览/检测 |
| `retired` | 固定 410 |
| `submit` | 创建确认作业（须经单位确认合同） |
| `status` | 纯读状态查询 |
| `recovery` | 取消/重试/回滚已有作业 |

AST 守卫从 `ImportJobService.create_job`、`DatasetService.activate`、`bulk_write_staged/copy_insert` 和旧 import service 反向追踪——任何未登记可达入口或登记 endpoint 未挂载都失败。守卫代码见 `check-format-single-source.mjs`（`ledger_read_surface_results` 键）。

---

## 2. 单位检测与确认合同

### 2.1 UnitDetectionSummary

三条正式 detect/preview 返回逐字段相同的摘要：

```python
class UnitDetectionSummary(BaseModel):
    status: Literal['detected', 'missing', 'conflict', 'unsupported']
    candidates: list[Literal['yuan', 'qian', 'wan']]
    unsupported_labels: list[str]     # 百元、亿元、外币单位等
    suggested_unit: Literal['yuan', 'qian', 'wan'] | None
    detector_version: str
    evidence_digest: str              # 64 位小写 SHA-256
```

- `元 / 千元 / 万元` 映射为 `yuan / qian / wan`。
- `百元 / 亿元 / 外币单位` 等进入 `unsupported`。
- `evidence_digest` 是 bundle 文件 hash/size、`detector_version` 以及按原始 file name、sheet name、raw label、normalized verdict 排序后的规范 JSON SHA-256。

### 2.2 UnitConfirmationInput

```python
class UnitConfirmationInput(BaseModel, extra='forbid'):
    source_amount_unit: Literal['yuan', 'qian', 'wan']
    source_unit_confirmed: Literal[True]
    unit_evidence_digest: str          # 64 位小写十六进制
    unit_confirmation_reason: str | None = None  # 条件必填，1~200 字
```

- digest 必须是 64 位小写十六进制。
- 检测为 `missing / conflict`，或用户选择与 `suggested_unit` 不同时，`unit_confirmation_reason` 去首尾空白后必须为 1–200 字。
- `unsupported` 状态下不可构造合同。

### 2.3 UnitNormalizationContract

```python
class UnitNormalizationContract(BaseModel):
    source_unit: Literal['yuan', 'qian', 'wan']
    storage_unit: Literal['yuan'] = 'yuan'
    factor: Decimal             # yuan=1, qian=1000, wan=10000
    normalization_version: Literal['normalized_v1']
    fields_version: Literal['amount_fields_v1']
    detection: UnitDetectionSummary
    confirmation_reason: str | None
    confirmed_by: UUID
    confirmed_at: datetime
    contract_digest: str        # 规范合同的 64 位小写 SHA-256
```

**铁律**：

- `storage_unit` 固定为 `'yuan'`，不可改。
- `factor` 由 `source_unit` 单向派生：`yuan → Decimal('1')`、`qian → Decimal('1000')`、`wan → Decimal('10000')`。客户端不可决定因子。
- `confirmed_by` 只取服务端 `current_user.id`，不接受客户端 user id。
- `canonical_unit_contract` 对除 `contract_digest` 外全部字段做枚举 value、UTC ISO 时间、Decimal 规范字符串和 sorted-key 紧凑 JSON 后取 SHA-256。
- `parse_persisted_unit_contract(raw, job_created_by=...)` 在每次 claim/retry/resume 重新计算并要求 `confirmed_by == job.created_by`、`detection.evidence_digest == options.unit_confirmation.unit_evidence_digest`。

### 2.4 增量提交额外参数

```python
class IncrementalSubmitInput(BaseModel, extra='forbid'):
    overlap_strategy: Literal['skip', 'overwrite']
    file_periods: list[int]               # 1~12
    base_dataset_id: UUID
    base_unit_contract_digest: str        # 64 位小写十六进制
    confirmed_overwrite: Literal[True] | None = None
```

`incremental/detect` 返回的 `base_dataset_id` 与 `base_unit_contract_digest` 必须原样提交。submit、seal、activation 三次在项目+年度锁内要求当前 active ID 与 unit contract digest 逐值相同。不新增或伪造 `base_dataset_version`。

---

## 3. 四表与 AccountChart 可见性

### 3.1 四表 staged 可见性规则

导入采用 staged 原子可见协议（非长事务）。核心规则由 `dataset_query.py` 的唯一异步 predicate 拥有：

| 场景 | 可见行 |
|------|--------|
| 有 active dataset | 只读 `dataset_id = <active>` 且 `is_deleted = false` |
| 无 active（legacy 数据） | 只读 `dataset_id IS NULL` 且 `is_deleted = false` |
| active 查询失败 | **上抛异常**，不扩大结果、不 rollback 后退化 |
| 绑定历史版本 | 显式 `force_dataset_id`（已绑定快照专用） |

四张 Tb staged 行统一写 `dataset_id = <stage>`、`is_deleted = false`。由于 stage 不是 active，**所有生产读者看不到 staged 行**——每次批次提交后登记生产读者仍只返回旧 active 结果。

**禁止**：裸 `project_id / year / is_deleted = false` 组合、`dataset_id.in_(active_subquery)` 无 legacy 规则、同步裸过滤、"无 active 即读所有未删行"。

### 3.2 AccountChart 独立可见性

AccountChart 保留 `(project_id, account_code, source) WHERE is_deleted = false` 部分唯一索引：

- 标准科目行：始终可见，不参与切换。
- staged 客户科目：写 `is_deleted = true`，不可见。
- 短激活事务顺序：先隐藏旧 active/legacy NULL-dataset 客户科目 → 再放开新 dataset 客户科目。
- dataset rollback：严格逆操作。
- seal / cleanup：按 `dataset_id` 统计和删除，不依赖 `is_deleted`。

### 3.3 四表读取面注册表

`LEDGER_TABLE_READ_SURFACES` 由 Python AST 从 `TbBalance / TbLedger / TbAuxBalance / TbAuxLedger` 的 `select / update-derived-read / aggregate` 符号反向产生，覆盖 `note_trace.py`、`disclosure_trace.py`、`note_source_resolvers.py` 等现有裸读。

每个生产读取必须调用 async predicate 或显式 `force_dataset_id`。以下用法使守卫失败：

- 裸 `project_id / year / is_deleted = false` 组合
- 未登记 reader
- 异常后 base filter
- 只用 `dataset_id.in_(active_subquery)` 但无 legacy 规则

---

## 4. attempt 恢复协议

### 4.1 ledger_import_attempts 表

每次导入执行尝试记录一条 attempt：

| 列 | 类型 | 说明 |
|---|------|------|
| `id` | UUID | 主键 |
| `job_id` | UUID FK | 所属 ImportJob |
| `attempt_no` | INTEGER | 尝试序号，`UNIQUE(job_id, attempt_no)` |
| `staged_dataset_id` | UUID | 本次尝试创建的 staged dataset（每 staged dataset 唯一） |
| `base_dataset_id` | UUID / NULL | 增量导入的基准 active dataset |
| `base_unit_contract_digest` | CHAR(64) / NULL | 基准 active 的 canonical unit contract digest |
| `state` | VARCHAR | 状态机值 |
| `unit_contract_digest` | CHAR(64) | 本次合同的 canonical digest |
| `bundle_digest` | CHAR(64) | bundle 文件 manifest digest |
| `active_before_hashes` | JSONB | 执行前旧 active 的逐表物理 hash |
| `row_counts` / `pre_hashes` / `post_hashes` | JSONB | 逐表行数与 hash |
| `failure_code` | VARCHAR / NULL | 失败原因码 |
| `created_at` / `sealed_at` / `finished_at` | TIMESTAMP | 时间戳 |

### 4.2 attempt 状态机

```
building → sealed → activating → activated
    │         │          │
    └─────────┴──────────┘
              │
    cleanup_pending → cleanup_done
```

正常流程：`building`（parse/convert/normalize/批量 staged 写入）→ `sealed`（封存证据）→ `activating`（短事务切换）→ `activated`。

失败分支：`building | sealed | activating` → `cleanup_pending`（写失败码）→ `cleanup_done`（清空五表 staged 行）。

### 4.3 三次基准复验

submit、seal、activation 三处在项目+年度 advisory lock 下都要求：

1. 当前 active 的 UUID = `base_dataset_id`（增量）或无 active（首次）。
2. 当前 active 的 canonical unit contract digest = `base_unit_contract_digest`（增量）。
3. 合同 digest、bundle digest 一致。

任一条件不满足：增量导入返回 `409 BASE_DATASET_CHANGED`；合同篡改返回对应错误码。

### 4.4 恢复判定

| 条件 | 恢复方式 |
|------|---------|
| `state = sealed` 且合同/bundle/base token/row counts/post-hash 全部复验一致 | `activation_only`：不重新 convert/normalize，直接进入 activating |
| 其他 retry/resume | 先清旧 stage → 创建新 attempt → 完整重建 |

**铁律**：禁止对已写 staged 行再次归一。`current_phase` 仅供状态显示。

---

## 5. 金额归一内核

### 5.1 归一字段

两条执行引擎共用 `_AMOUNT_FIELDS_BY_TABLE`：

| 表 | 换算字段 |
|---|---------|
| TbBalance / TbAuxBalance | `opening_balance, opening_debit, opening_credit, debit_amount, credit_amount, closing_balance, closing_debit, closing_credit` |
| TbLedger / TbAuxLedger | `debit_amount, credit_amount` |

**不换算**：数量字段（`qty` 等）、全部 `*_fc` 原币字段。

### 5.2 Decimal 归一规则

1. converter 输出合同：金额字段只能是 `Decimal | None`。
2. 空值/空白字符串 → `None`，hash 使用稳定 null token。
3. 非空不可解析值 → fatal `LEDGER_AMOUNT_INVALID`（含 file/sheet/row/field）。
4. 非空值写入前 `is_finite()` 校验：`NaN / +Infinity / -Infinity` → `LEDGER_AMOUNT_NOT_FINITE`。
5. `value * factor` → `ROUND_HALF_UP` 到 `0.01` → `Numeric(20,2)` 边界检查（18 位整数上限）。

正负 0.005 分别得到 0.01 / -0.01。边界可写、越界 fail closed。

### 5.3 错误码速查

| 错误码 | HTTP 状态 | 含义 |
|--------|----------|------|
| `LEDGER_AMOUNT_INVALID` | — | 非空不可解析值（含定位信息） |
| `LEDGER_AMOUNT_NOT_FINITE` | — | NaN / ±Infinity |
| `SOURCE_UNIT_CONFIRMATION_REQUIRED` | 428 | 直接文件上传未确认单位 |
| `UNIT_DETECTION_CHANGED` | 409 | 确认后检测摘要变化 |
| `BASE_DATASET_CHANGED` | 409 | 增量基准 active ID 或 digest 变化 |
| `BASE_DATASET_UNIT_UNVERIFIED` | 409 | 基准 active 为 legacy 或证据不完整 |
| `INCREMENTAL_PERIODS_CHANGED` | 409 | 服务端检出月份与提交不一致 |
| `LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB` | 410 | 旧同步 POST 已退役 |
| `INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB` | 410 | 旧增量覆盖已退役 |
| `UPLOAD_BUNDLE_INTEGRITY_FAILED` | — | bundle hash 不符或缺失 |
| `DISPLAY_MEASURE_CONTRACT_INVALID` | — | 度量合同无效 |

---

## 6. 共享 PG READ ONLY inspector

### 6.1 设计原则

既有共享 PG 的 baseline 与 dry-run 必须使用数据库级只读入口。inspector 的调用纪律如下：

1. 单一连接，**第一条业务 SQL** 必须为 `SET TRANSACTION READ ONLY`。
2. 断言 `SHOW transaction_read_only` = `on`。
3. 全调用图禁止另开连接（所有 helper 复用同一连接）。
4. `finally` 统一 `ROLLBACK`（即使只读也显式回滚）。
5. 输出只放 `tmp_global_display_settings/`。

### 6.2 产出内容

inspector 按 `normalized_v1 / legacy_declared / legacy_unknown` 三类输出：

- 动态数据集数量
- 四表逐字段 row count / sum / max / 溢出风险
- canonical hashes

**不按金额大小猜单位**。

### 6.3 故障注入

隔离 PG 自动测试在该入口故障注入 `UPDATE`，必须得到 `ReadOnlySqlTransaction`（SQLSTATE `25006`），随后 scoped row count、金额 hash 与 `source_summary` hash 前后相同。

### 6.4 未来 apply / rollback 双闸门

真实写脚本使用与共享 dry-run **物理分离**的显式写入口：

| 操作 | 前置条件 |
|------|---------|
| `apply` | 环境变量 + `--apply` + dataset 双录 + source unit |
| `rollback` | 以上 + 最后未回滚 normalization version |

- apply history 保存变更前单位元数据的 presence-aware canonical snapshot + digest。
- rollback 闭合当前 after-hash → 反向 before-hash 后精确恢复原 `legacy_declared / legacy_unknown` 状态。
- 四表、unit metadata、history 和 hash 在单数据集事务内。

> ⚠️ **本 spec 在共享 PG 只运行 inspector，绝不运行真实 apply/rollback**。真实批量改值须另行获得用户放行。

---

## 7. 数据集单位三态分类

后端 `dataset_unit_contract.classify_dataset_unit()` 把 `source_summary` 归为三类：

| 状态 | 含义 | 判定依据 |
|------|------|---------|
| `normalized_v1` | 已确认归一，存储单位为元 | `source_summary.unit_normalization.contract.contract_digest` 存在且为 64 位小写十六进制 |
| `legacy_declared` | 旧 `source_summary` 有顶层 `amount_unit` 声明 | 有 `amount_unit` 字符串，无 `unit_normalization` |
| `legacy_unknown` | 无单位证据或合同无效 | 其余情况（含 `unit_normalization` 存在但合同无效的 fail-closed） |

唯一前端 presenter `datasetUnitPresentation.ts` 供 LedgerPenetration 与 TrialBalance 使用，见 [`display-preferences.md` §12](../frontend/display-preferences.md#12-数据集单位三态)。

---

## 8. 文档守卫核对项

本文档的守卫应核对以下内容与代码一致：

1. **导入 API 端点路径与方法**：§1.1–§1.3 的端点路径/方法与 `account_chart.py`、`ledger_import_v2.py`、`ledger_penetration.py`、`ledger_data.py` router 一致。
2. **错误码**：§5.3 错误码在对应 router/service 中存在。
3. **入口注册表名称**：`LEDGER_IMPORT_ENTRYPOINTS` 名称与代码中的注册表变量名一致。
4. **读取面注册表名称**：`LEDGER_TABLE_READ_SURFACES` 名称与代码中的注册表变量名一致。
5. **分类器函数**：`classify_dataset_unit` 的三个返回值与 `dataset_unit_contract.py` 一致。
6. **attempt 状态机值**：§4.2 的六个状态值（`building / sealed / activating / activated / cleanup_pending / cleanup_done`）与 `ledger_import_attempts` 表/ORM CHECK 一致。
7. **归一字段**：§5.1 `_AMOUNT_FIELDS_BY_TABLE` 的字段名与代码中的常量一致。
8. **真实 PG 禁写**：本文档未声称在共享 PG 执行过真实 apply/rollback。

---

## 9. 后续批次

| 任务 | 范围 | 状态 |
|------|------|------|
| B-V | 阶段 B 运行时冒烟/验证（preview→确认→submit→激活、旧 POST 410、只读 inspector dry-run） | 待实施 |
| B-BK | 阶段 B 备份 commit 对象 | 待实施 |
| 12C | 正式导出单位开发文档 | 待实施 |
| 11C | 正式导出出口闭集接入唯一守卫 | 待实施 |
| 13 | 终验（Playwright、候选树验证、独立评审） | 待实施 |

> 未来真实 apply/rollback 的执行仍需用户另行放行，不在当前轮次授权范围内。
