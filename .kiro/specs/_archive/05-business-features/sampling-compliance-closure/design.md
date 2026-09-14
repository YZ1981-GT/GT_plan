# Design Document

## Overview

本设计的核心判断：**canonical 抽凭链路不重构**。抽样算法、全量框、覆盖率、批次状态机、
历史/撤销/对比都保持逐字节不变，本 spec 只做三类**加法**：

1. **给抽样留痕补上「在哪一版数据上抽的」与「抽完评价成什么样」两个维度**（R1/R2）——
   落点是既有 `workpaper_extraction_log.extraction_criteria` JSONB 的新 key，不改
   request/response 的既有字段，不改表结构。
2. **把抽样评价的输出接到错报汇总**（R3）—— 落点是既有 `a13:push-misstatement` 事件桥
   增一个可选字段，缺省值等于现状。
3. **清掉与 canonical 口径不同的第二套实现**（R4）与**把留痕呈现到底稿正文**（R6），
   并把两张已存在但空置的准则记录表接成真数据（R5）。

风险控制的两个支点：
- **所有新增字段都有缺省语义** → 既有 ~35 个 A13 推送点、既有历史记录、既有宿主在不改
  动的情况下行为不变（R7.2）。
- **每条守卫都配反向自检** → 避免出现「守卫写了但恒绿」这一平台已多次踩中的假绿模式。

三波边界与用户给定顺序一致：Wave 1 = R1→R2→R3（三者合起来才让「样本错报 → 总体错报 →
与重要性比较」闭环，缺任一环都不成立）；Wave 2 = R4 + R5；Wave 3 = R6。

## Architecture

### 现状链路（本 spec 不改）

```
前端 useVoucherSampling.triggerSampling
  → POST /sampling/voucher-extract
      → _authorize_and_validate_extract（编辑权 + 底稿归属 + 年度）
      → LedgerSamplingService.build_ledger_query（get_active_filter → active dataset）
      → execute_with_stats（全量聚合 stats，内存框上限 10000）
      → [总体 > 10000] locate_sampling_units → execute_sampling → fetch_by_unit_ids
        [总体 ≤ 10000] execute_sampling(items)
      → build_methodology_snapshot（CAS1314 泊松，algo_version）
      → _resolve_independent_book_amount（trial_balance 独立账面）
  → 预览弹窗（选样 / 录 actualMisstatement / inferMisstatement / 确认结论）
  → confirmFill → POST /sampling/cutoff-fill
      → LedgerSamplingService.record_extraction_log（批次状态机 + 幂等键 + batch_id）
  → emit('filled', {samples, methodology, ...}) → 宿主回填底稿
```

### 本 spec 的加法（标 ✚）

```
voucher-extract
  ✚ get_active_dataset_id_or_none → stats.dataset_id                        [R1]

cutoff-fill（extraction_criteria）
  ✚ dataset_id                                                             [R1]
  ✚ evaluation{...}（若回填时已有推断结果）                                  [R2]
  ✚ 回填成功后：写 sampling_records 1 条 + sampled_vouchers N 条            [R5]

✚ POST /sampling/voucher-evaluation                                        [R2]
      → 同一授权 helper → upsert extraction_criteria.evaluation
      → 同步 sampling_records 的 deviations/projected/UML/conclusion        [R5]

voucher-history
  ✚ 每行 dataset_id / dataset_stale / evaluation                           [R1/R2]

✚ GET /sampling/voucher-coverage（项目级抽样登记概览 + 跨底稿重复凭证）      [R5]

前端
  ✚ 引擎挂载时回读最近批次 evaluation → 还原推断区                          [R2]
  ✚ 「推送推断错报至 A13」→ a13:push-misstatement{misstatementType:'projected'} [R3]
  ✚ useA13MisstatementBridge 透传 misstatementType（缺省 factual）           [R3]
  ✚ shared/samplingFillTarget.ts + WpSamplingMethodologyBar.vue → 81 宿主   [R6]

删除
  ✘ /sampling/execute ×2 端点 + wp_sampling_engine.py + 其 3 个测试文件      [R4]
```

### 为什么 evaluation 落 `extraction_criteria` 而不是先建新表

三个理由：
1. **半径**。`extraction_criteria` 是既有 JSONB，加 key 不需要迁移、不需要改 ORM、不需要
   动批次状态机的幂等派生逻辑（幂等键只从 `filled_voucher_nos` 派生，不受 evaluation 影响）。
2. **时序**。评价发生在回填之后且可能反复更新（审计师逐天核查），JSONB upsert 天然支持；
   而新表会引入「哪条评价对应哪个批次」的第二套关联。
3. **与 R5 的接缝**。R5 把 `sampling_records` 接成 canonical 评价记录表时，
   `extraction_criteria.evaluation` 仍是**写入侧的载荷形状**，`sampling_records` 是
   **可查询侧的投影**。两者由同一次写入同时更新，`extraction_criteria` 为准（批次维度
   唯一），`sampling_records` 供项目级/QC 级查询。这是「JSON 承载 + 列投影」的既有平台
   范式（同 `report_config` 与 `note_template` 的关系），不是双真源。

## Components and Interfaces

### 后端

#### `voucher_sampling.py`（改）

```python
# R1：extract 返回抽样框版本
active_dataset_id = await get_active_dataset_id_or_none(db, pid, req.year)
# → stats["dataset_id"] = str(active_dataset_id) if active_dataset_id else None
```

```python
# R2：新端点
class VoucherEvaluationRequest(BaseModel):
    workpaper_id: UUID
    log_id: UUID | None = None
    evaluation: dict          # 形状见 Data Models
@router.post("/voucher-evaluation")
async def voucher_evaluation(pid, req, db, current_user) -> dict:
    await _authorize_and_validate_evaluation(db, current_user, pid, req.workpaper_id)
    log = await _resolve_target_log(db, req.workpaper_id, req.log_id)   # 404 if none
    criteria = dict(log.extraction_criteria or {})
    criteria["evaluation"] = _normalize_evaluation(req.evaluation, actor=current_user.id)
    log.extraction_criteria = criteria      # 整 key 重写，JSONB 需显式赋新 dict
    await _upsert_sampling_record_evaluation(db, log)                    # R5
    await db.commit()
    return {"success": True, "log_id": str(log.id), "batch_id": str(log.batch_id)}
```

关键实现约束：
- `log.extraction_criteria` 是 JSONB，**必须赋一个新 dict**（原地 mutate 不触发 SQLAlchemy
  脏检测 → 静默不落库，平台已有同类坑）。
- 写 JSONB 时若走裸 SQL，**用 `CAST(:val AS jsonb)` + `json.dumps`**，禁
  `sa.type_coerce(..., sa.JSON)`（asyncpg 下 100% 失败，memory 已记）。本设计走 ORM 赋值，
  不涉及裸 SQL。

```python
# R1：history 增字段
current_ds = await get_active_dataset_id_or_none(db, pid, <year>)
# 逐行：ds = criteria.get("dataset_id")
#       dataset_stale = bool(ds) and str(ds) != str(current_ds)
#       dataset_id = ds, evaluation = criteria.get("evaluation")
```

`voucher-history` 现签名只有 `wp_id` 无 `year`。**不改签名**：year 从底稿所属项目的
`audit_year` 解析（`_authorize_and_validate_extract` 已有同类查询），解析不到则
`dataset_stale` 一律 `false`（未知不当已变更，R1.6）。

```python
# R5：新端点
@router.get("/voucher-coverage")
async def voucher_coverage(pid, year, db, current_user) -> dict:
    # by_workpaper: [{wp_id, wp_code, batch_count, sample_count}]
    # duplicated:   [{voucher_no, wp_codes: [...], count}]  count >= 2
```

#### `sampling_registry_service.py`（新）

承接 R5 的两表写入，纯服务层，被 `cutoff_fill`（voucher_sampling 类型）与
`voucher_evaluation` 调用：

```python
async def register_sampling_batch(db, *, log, methodology, stats, dataset_id) -> UUID
    """回填成功后写 sampling_records 1 条（绑 batch_id），返回 record id。"""
async def register_sampled_vouchers(db, *, log, vouchers) -> int
    """批量登记 sampled_vouchers（ON CONFLICT DO NOTHING 走 V139 唯一索引）。"""
async def update_sampling_record_evaluation(db, *, batch_id, evaluation) -> bool
    """把 evaluation 投影进 sampling_records 的 deviations/projected/UML/conclusion。"""
async def project_level_extracted_voucher_nos(db, project_id, year) -> list[str]
    """R5.5：跨底稿排除集合来源。"""
```

写入失败一律 **fail-open + WARNING 日志**：登记表是查询投影，不得因它写失败而让审计师的
回填整体失败（但 warning 会被 R7 的守卫捕获，见 Property 12）。

#### 删除清单（R4）

| 路径 | 处置 |
|------|------|
| `backend/app/services/wp_sampling_engine.py` | 删 |
| `sampling_enhanced.py` 的 `SamplingExecuteRequest` + `/sampling/execute` | 删 |
| `wp_functional_actions.py` 的 `elif endpoint == "sampling/execute"` 分支 | 删 |
| `backend/tests/test_wp_sampling_engine_seed.py` | 删（整文件锁 legacy 行为） |
| `test_voucher_sampling_characterization.py::TestWpSamplingEngineCharacterization` | 删该类，canonical 段保留 |
| `test_wp_functional_actions.py` 的 4 个 `test_sampling_engine_*` | 删 |

### 前端

#### `useVoucherSampling.ts`（改）

```ts
// R1
const datasetId = ref<string | null>(null)            // 来自 extract stats.dataset_id
// R2
const loadedFromBatch = ref<{logId: string; batchId: string; evaluatedAt: string} | null>(null)
async function loadLatestEvaluation(): Promise<void>  // 仅当未执行新抽样时调用
async function persistEvaluation(): Promise<boolean>  // POST /voucher-evaluation
// R3
async function pushProjectedToA13(): Promise<boolean>
```

`confirmFill` 的 `extraction_criteria` 增 `dataset_id` + `evaluation`（若有）。
`triggerSampling` 已有的「重置上一批次推断状态」分支同时清 `loadedFromBatch`（R2.8）。

#### `useA13MisstatementBridge.ts`（改）

```ts
export type MisstatementTypeValue = 'factual' | 'judgmental' | 'projected'
const VALID_TYPES: readonly MisstatementTypeValue[] = ['factual', 'judgmental', 'projected']
function normalizeType(v: unknown): MisstatementTypeValue {
  const s = String(v ?? '')
  return (VALID_TYPES as readonly string[]).includes(s) ? (s as MisstatementTypeValue) : 'factual'
}
// MisstatementDraft 增 misstatementType: MisstatementTypeValue（归一后必有值）
// 行级 r.misstatementType/r.misstatement_type > 顶层 payload.* > 'factual'
```

去重 hash 增 `misstatementType` 维度（同金额同描述的 factual 与 projected 不应互相吞掉）。

#### `composables/shared/samplingFillTarget.ts`（新，R6）

```ts
export interface SamplingMethodologySnapshot {
  samplingMethod: string
  samplingInterval: string | null
  sampleSize: number
  suggestedSampleSize: number | null
  tolerableMisstatement: number | string | null
  expectedMisstatement: number | string | null
  confidenceLevel: number | null
  accountCodes: string[]
  randomSeed: string | null
  batchId?: string | null
  datasetId?: string | null
}
/** 方法学持久化键：`{wpCode}-sampling-methodology`（一底稿一条，最后一次抽样为准） */
export function samplingMethodologyItemKey(wpCode: string): string
/** 方法学 → 一行中文摘要（供 bar 折叠态与导出复用） */
export function buildMethodologySummary(m: SamplingMethodologySnapshot | null): string
/** SampledVoucher → 通用最小行（6 字段），供宿主映射时兜底不丢字段 */
export function mapSampledToGenericRow(v: unknown): GenericSampledRow
```

零 Vue 依赖纯函数，便于 PBT 与守卫交叉读取。

#### `WpSamplingMethodologyBar.vue`（新，R6）

只读紧凑单行 bar（对齐平台「状态面板禁空洞 el-card 改紧凑单行」铁律）：
`方法 · 间隔 · 样本量(建议 N) · 可容忍错报 · 种子 · 批次 · 账套版本`，
`methodology` 为空时整条隐藏。金额一律走 `displayPrefs.fmtAmount()`
（**`fmtAmount` 是 store 成员不是模块导出**，setup 顶层 inject/useStore 取得，禁写进函数体）。

## Data Models

### `extraction_criteria.evaluation`（R2，JSONB 内新 key）

```jsonc
{
  "projected": "12345.67",              // 推断错报（Decimal 字符串，不含高值层已知错报）
  "known_high_value": "5000.00",        // 高值层已知错报
  "basic_precision": "8000.00",
  "incremental_allowance": "1200.00",
  "upper_limit": "21545.67",            // UML = projected + basic + incremental
  "checked_sample_count": 23,
  "unchecked_sample_count": 2,
  "deviation_count": 3,                 // actualMisstatement > 0 的样本数
  "tolerable_misstatement": "500000.00",
  "conclusion_code": "acceptable",      // acceptable | not_acceptable | undetermined
  "conclusion_message": "错报上限低于可容忍错报，总体可接受",
  "conclusion_confirmed": true,
  "algo_version": "cas1314-poisson-v1",
  "evaluated_at": "2026-08-04T14:20:00Z",
  "evaluated_by": "<uuid>",
  "a13_pushed_at": null,                // R3.8；非空表示已推送过推断错报
  "a13_misstatement_id": null
}
```

`_normalize_evaluation` 只接受上述 key（未知 key 丢弃），金额一律转字符串，
`evaluated_at`/`evaluated_by` 由服务端覆盖（客户端传值不可信）。

### `extraction_criteria.dataset_id`（R1）

`str(uuid) | null`。**不复用** `bound_dataset_id` 这个名字，因为它在平台语义里表示
「下游对象锁定版本后强制查该版本」（`force_dataset_id` 路径），而抽样这里只是**记录当时的
版本**、不锁定后续查询 —— 混用会误导后来者以为抽凭查询走了 force 路径。

### 迁移 V139（R5）

```sql
-- sampling_records：批次关联 + 方法学快照列
ALTER TABLE sampling_records ADD COLUMN IF NOT EXISTS batch_id uuid;
ALTER TABLE sampling_records ADD COLUMN IF NOT EXISTS sampling_method varchar(32);
ALTER TABLE sampling_records ADD COLUMN IF NOT EXISTS random_seed bigint;
ALTER TABLE sampling_records ADD COLUMN IF NOT EXISTS dataset_id uuid;
CREATE INDEX IF NOT EXISTS ix_sampling_records_batch ON sampling_records(batch_id);

-- sampled_vouchers：批次关联 + 防重唯一索引
ALTER TABLE sampled_vouchers ADD COLUMN IF NOT EXISTS batch_id uuid;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_vouchers_batch
  ON sampled_vouchers(project_id, year, voucher_no, working_paper_id, batch_id)
  WHERE is_deleted = false;
```

取号依据：磁盘最高 `V138__fix_report_config_equity_and_asset_codes.sql` 且 `schema_version`
已记录 138 → 下一可用号 **V139**。迁移须幂等（`MigrationRunner` 只在后端启动时跑，
应用后需重启后端）。

### `sampling_records` 字段映射（R5.1）

| 列 | 来源 |
|----|------|
| `working_paper_id` | log.workpaper_id |
| `batch_id` | log.batch_id |
| `sampling_purpose` | `criteria.filters.account_codes` + 方法拼成的中文描述 |
| `population_description` | 过滤条件中文摘要（科目/期间/金额区间/方向/凭证类型/关键字） |
| `population_total_amount` / `population_total_count` | extract 的 `stats.population_amount` / `population_count` |
| `sample_size` | log.filled_count |
| `sampling_method` / `random_seed` / `dataset_id` | criteria 同名字段 |
| `sampling_method_description` | `buildMethodologySummary` 的后端等价文本 |
| `deviations_found` / `misstatements_found` / `projected_misstatement` / `upper_misstatement_limit` / `conclusion` | evaluation 投影（R5 更新路径） |

## Error Handling

分三档，判据是「该失败是否影响审计师已经做出的判断」：

| 场景 | 处置 | 理由 |
|------|------|------|
| `get_active_dataset_id_or_none` 抛错 / 无 active 数据集 | `dataset_id = null` + 前端提示，不阻断抽样 | 「先建底稿后导账套」是合法工作流；把未知如实表达为 null，绝不用「当前时间」「随便一个 dataset」兜底 |
| `voucher-evaluation` 授权失败 | 403/404，目标记录零变化 | 授权在 try 之外（沿用 `voucher-extract` 已有范式，防 403 被 except 吞成 500） |
| `voucher-evaluation` 载荷含未知 key / 非法金额 | 丢弃未知 key、非法金额转 `"0.00"`，其余正常落库 | 评价是审计师的工作成果，不能因一个字段格式问题整条丢弃 |
| `register_sampling_batch` / `register_sampled_vouchers` 抛错 | fail-open + `logger.warning`，回填仍返回成功 | 登记表是查询投影，不是权威留痕；权威在 `extraction_criteria`。但必须留 WARNING，否则 fail-open 变静默黑洞（Property 12 用 caplog 钉死） |
| A13 推送失败 | `ElMessage.error` 明示 + 不写 `a13_pushed_at` | 不得静默吞（平台已有「catch {} 吞掉 422」的踩坑记录）；不写标记以便重试 |
| 前端 `persistEvaluation` 失败 | 提示「评价未保存」+ 保留内存态 | 内存态还在，用户可重试；静默失败会让用户以为已存 |
| `loadLatestEvaluation` 失败 | 静默降级为空评价 | 回读是增强，失败不应阻塞打开引擎；但不得把失败当「无评价」写回库 |

**fail-open 的边界**：只允许在「投影/增强」路径 fail-open（登记表、回读），
**绝不允许**在「权威留痕」路径 fail-open（`extraction_criteria` 写入失败必须让
`cutoff-fill` 返回失败，现状即如此，不改）。

## Testing Strategy

四层，各自职责不重叠：

1. **后端纯函数/契约测试**（不连库，可进 CI）
   - `_normalize_evaluation` 的 key 白名单、金额字符串化、服务端覆盖 `evaluated_at`/`evaluated_by`
   - `dataset_stale` 三态判定（Property 2）
   - `sampling_records` 字段映射纯函数
   - 源码级守卫：legacy 零引用（Property 10）、`SamplingConfig(` 计数（Property 13）、
     登记表构造点存在（Property 14）—— **全部配反向自检**，读源码前先 `_strip_comments()`
     （否则守卫自己注释里写的反例会被数成真实引用）
2. **后端连库测试**（`backend/tests/four_table/` 同款单 `asyncio.run` 快照范式）
   - Property 1（dataset_id 取值等于真实 active 记录）、Property 11（唯一索引防重）、
     Property 12（caplog 断言 WARNING）
   - **一个测试模块内只允许一次 `asyncio.run`**：连接池绑定首个事件循环，第二次必炸成
     `AttributeError: 'NoneType' object has no attribute 'send'`，若 fixture 里
     `except → skip` 会变成静默假绿
3. **前端 vitest**
   - `normalizeMisstatementPushPayload` 的缺省等价性（Property 6）用 PBT + 既有四形态
     fixture 回归；去重不跨类型（Property 9）
   - `samplingFillTarget.ts` 纯函数（Property 17 的字段集）
   - 平台守卫 `samplingHostMethodologyCoverage.spec.ts`（Property 15/16），
     **`REPO_ROOT` 用哨兵文件向上查找，禁写死回退级数**，且哨兵必须是具体文件不能是目录
4. **浏览器实测**（chrome-devtools + postgres 只读）
   - 抽样 → 录实际错报 → 推断 → 确认结论 → 推送 A13 → `postgres` 查到
     `misstatement_type='projected'`（Property 18）
   - 关闭弹窗重开 → 推断区还原且标注来源批次（R2.7）
   - 序时账切换 dataset 后打开历史 → 「抽样框已变更」告警出现（R1.5）
   - 实测三件套缺一不算实测：**录真实数据 + 看目标区域真出数 + postgres 查落库**；
     测完必须逐字段复原（含 `unadjusted_misstatements` 的 projected 行）

**已知实测障碍**：抽凭引擎所在的宿主 dialog 是 `destroy-on-close`，且部分底稿（如 K 系）
的抽凭入口在多层 Tab 内；实测前先用 `render-config` 确认 sheet 分发命中，避免把「Tab 没
挂上」误判为「功能没生效」。

## Correctness Properties

### Property 1: extract 响应必带 dataset_id 且取值等于当前 active 数据集

对任意成功的 `voucher-extract` 调用，`stats.dataset_id` 要么为 `null`（该 project/year 无
active 数据集），要么等于 `ledger_datasets` 中该 project/year 状态为 active 的记录 id。
不得出现「有 active 数据集但返回 null」。

**Validates: Requirements 1.1, 7.3**

### Property 2: dataset_stale 三态判定

对任意历史记录：`dataset_id` 为空 ⇒ `dataset_stale == false`；`dataset_id` 非空且等于当前
active ⇒ `false`；`dataset_id` 非空且不等于当前 active ⇒ `true`。改造前的既有记录
（无 `dataset_id`）永不产生告警。

**Validates: Requirements 1.4, 1.6**

### Property 3: evaluation upsert 幂等且只影响目标 key

对同一 log 连续两次提交相同 `evaluation`，`extraction_criteria` 除
`evaluation.evaluated_at` 外逐字节相同；`extraction_criteria` 的其余 key
（`filled_voucher_nos` / `filled_unit_ids` / `filters` / `random_seed` / `dataset_id` …）
在两次提交后均保持原值不变。

**Validates: Requirements 2.1, 2.3, 7.2**

### Property 4: evaluation 端点授权先于任何写入

对无编辑权用户或跨项目 `workpaper_id`，端点返回 403/404 且目标 log 的
`extraction_criteria` 与 `updated_at` 均无变化（授权在 try 之外、先于 ORM 赋值）。

**Validates: Requirements 2.4**

### Property 5: 新抽样清空回读评价

执行 `triggerSampling` 成功后，`misstatementResult` / `samplingConclusion` /
`conclusionConfirmed` / `loadedFromBatch` 全部为初始态；不得出现「界面显示的结论来自上一
批次而样本已换」的组合。

**Validates: Requirements 2.7, 2.8**

### Property 6: misstatementType 归一化的缺省等价性

对任意不含 `misstatementType` / `misstatement_type` 的历史载荷（覆盖既有四种形态 A/B/C/D），
`normalizeMisstatementPushPayload` 的输出除新增字段恒为 `'factual'` 外，与改造前逐字段相同。
非法取值（空串/未知字符串/数字/对象）一律归一为 `'factual'`。

**Validates: Requirements 3.2, 3.4, 7.2**

### Property 7: 推断错报推送的金额与类型

「推送推断错报至 A13」产生的错报草稿恰为 1 条，`misstatementType === 'projected'`，
`amount === Number(evaluation.projected)`，且 `amount > 0`；描述中同时含抽样方法、
样本量、随机种子与批次号四项标识。`known_high_value > 0` 时描述含提示语。

**Validates: Requirements 3.5, 3.6**

### Property 8: 结论未确认不得推送

`conclusionConfirmed === false` 或 `projected <= 0` 时，推送操作不可用且不产生任何
`a13:push-misstatement` 事件。

**Validates: Requirements 3.5**

### Property 9: 去重不跨类型互吞

同一去重窗口内推送「相同 wpCode/描述/金额」的 factual 与 projected 两条草稿时，两条
均应落库（去重 hash 含类型维度）。

**Validates: Requirements 3.1, 3.3**

### Property 10: legacy 引擎全仓零引用

`backend/app/**` 下不存在任何对 `WpSamplingEngine` / `wp_sampling_engine` 的引用，
也不存在对 `parsed_data.action_data` 的写入。守卫含反向自检：给定一段含该引用的替身源码
时判定必须为「违规」。

**Validates: Requirements 4.3, 4.4, 4.5**

### Property 11: sampled_vouchers 同批次防重

同一 `(project_id, year, voucher_no, working_paper_id, batch_id)` 重复登记时总行数不增加
（唯一索引 + ON CONFLICT DO NOTHING）；不同 batch_id 的同一凭证可以共存（体现「该凭证被
抽过两次」这一事实）。

**Validates: Requirements 5.2, 5.4**

### Property 12: 登记表写失败不影响回填主流程且必留 WARNING

当 `register_sampling_batch` / `register_sampled_vouchers` 抛异常时，`cutoff-fill` 仍返回
成功且 `workpaper_extraction_log` 已落库；同时 logging 必须产生 WARNING 及以上记录
（守卫用 caplog 断言，避免 fail-open 变成静默黑洞）。

**Validates: Requirements 5.1, 5.2, 7.1**

### Property 13: sampling_config 写入点不增加

`backend/app/**` 中构造 `SamplingConfig(` 的位置数量不超过改造前基线（当前为 1，位于
`sampling_service.create_config`），且 `sampling_service.py` 模块 docstring 含
`.. deprecated::` 标注。

**Validates: Requirements 5.7, 5.8**

### Property 14: 登记表接入点确实存在

`backend/app/**` 中存在对 `SamplingRecord(` 与 `SampledVoucher(` 的构造点且位于
`sampling_registry_service.py`；守卫反向自检：删除该服务的构造调用时断言必红
（防「建了表和迁移但没人写」再次退化为孤儿）。

**Validates: Requirements 5.1, 5.2, 5.8**

### Property 15: 宿主 methodology 覆盖率单调收敛

全部含 `GtVoucherSamplingEngine` 的 `.vue` 中，未消费 `methodology` 的文件集合必须是
allowlist 的子集；allowlist 每条须带理由字符串（≥10 字），条目数不得超过上一次基线。
薄壳（`v-bind="$props"` 委托）视为已满足。

**Validates: Requirements 6.3, 6.6, 6.7**

### Property 16: 宿主样本映射最小字段集

宿主的 `filled` 处理函数中，对样本对象的字段读取必须覆盖凭证号、日期、金额（借或贷）、
科目编码四类中的全部；只读 `summary`/`voucherNo` 二者之一即判违规。守卫反向自检：
构造一个只读 `summary` 的替身宿主源码时断言必红。

**Validates: Requirements 6.5, 6.8**

### Property 17: 方法学 bar 渲染门控

`WpSamplingMethodologyBar` 在 `methodology` 为 `null`/空对象时不渲染任何 DOM；非空时
渲染的字段集恰为 `buildMethodologySummary` 声明的字段，且金额项经 `fmtAmount` 格式化
（含千分符与两位小数）。

**Validates: Requirements 6.2, 6.4**

### Property 19: 跨底稿重复检测的范围正确性

`cross_workpaper_duplicates` 只包含「被**其它** `working_paper_id` 且 `batch_id IS NOT NULL`
的登记行覆盖」的凭证号：当前底稿自身的登记不计入；`ledger_penetration` 的手工标记
（`batch_id IS NULL`）不计入；本次样本之外的凭证不计入。

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 20: 重复确认三出口与留痕

确认框的三个出口互斥且各自后果确定：`keep_all` → 样本集合不变；`removed` → 样本集合恰好
移除全部重复凭证且其余顺序不变；`none`（取消）→ 样本集合清空且不打开预览。三种情况下
回填留痕的 `duplicate_decision` 分别为 `keep_all` / `removed` / 不产生回填。

**Validates: Requirements 8.5, 8.6, 8.7**

### Property 21: 项目级排除下不重复提示

当 `exclude_scope === 'project'` 时重复项已在抽样阶段被排除，`cross_workpaper_duplicates`
恒为空数组，前端不弹确认框（避免「已按你的配置剔除了，还要再问你一遍」）。

**Validates: Requirements 8.8**

### Property 18: projected 端到端可落库

真实库上存在一条 `unadjusted_misstatements.misstatement_type = 'projected'` 的记录
（由 R3 通路写入），证明该 enum 值真正可用；实测后须复原测试数据。

**Validates: Requirements 7.4, 3.3**

### Property 22: 抽样方法学与错报留痕的可追溯字段真能取到值

Task 24 浏览器实测挖出四处「声明了但取不到值」（dead output）—— 判据一律是**源码形态**
而非「字段名出现过」，因为「出现过」挡不住把它写成恒 null 的表达式：

1. **`filled` 载荷的 methodology 必须携带 `batchId` / `datasetId`**。改造前引擎只填 9 个
   字段，而共享类型 `SamplingMethodologySnapshot`、`buildMethodologySummary` 与
   `WpSamplingMethodologyBar` 三处都声明并渲染这两列 ⇒ 归档件上最要紧的两个可追溯字段
   **结构上恒为空**（实测：一个 `dataset_id` 已绑定的批次仍显示「未绑定账套版本」）。
   `batchId` 的真源是 `cutoff-fill` 响应，故 `confirmFill` 不得丢弃该响应；
   备忘导出侧亦不得读 `methodologySnapshot.batch_id`（后端 `build_methodology_snapshot`
   是纯方法学函数，抽样时批次还不存在，其快照里压根没有该键）。
2. **`wpCode` 必须回落 `WorkpaperRuntimeContext.wpCode`**。实测 78 个抽凭宿主一个都没传
   该 prop ⇒ 只靠 prop 会让 A13 的 `source_wp_code` 恒 null（错报汇总看不出这笔推断错报
   出自哪张底稿）。`inject` 必须在 setup 顶层，且传给 composable 的必须是 getter
   （runtime 在引擎 setup 那一刻未必已就位，静态快照会把它固化成空串）。
   复核 `section_id` 前缀与 `source_wp_code` 共用同一真源，不得两处分叉。
3. **R2.7 回读态卡片不得被样本数门控藏起来**。回读既有批次评价时会话内没有样本，
   只按 `sampledVouchers.length > 0` 渲染会把回读结果整块藏起来 —— 状态还原了但用户
   看不见。同时「重新推断」与「记入 A13」在该态下必须禁用并给出根因（0 笔样本重算会
   抹掉回读结果；描述里的样本量/种子取自会话内值，会写出 `样本量:0 随机种子:-`）。
4. **A13 描述里的批次号必须与同一条描述的样本量/种子同属一个事件**。「已抽样但未回填」
   时 `loadedFromBatch` 仍指向**上一个批次**，直接取它会写出「样本量:2 随机种子:20260811
   批次:43da7592」而那个批次是另一套样本 —— 错的批次号比没有批次号更坏（复核人按它去翻
   批次会对不上样本），此时如实写「未回填」。

配套后端不变量：R2.5 的回填路径（`cutoff-fill`）随带的 `evaluation` 必须复用
`/voucher-evaluation` 的**同一归一器**，否则该路径写出的评价缺 `evaluated_at` /
`evaluated_by`（服务端权威字段，客户端不传）⇒ 前端 `evaluationSourceHint` 因
`evaluatedAt` 为空而不渲染「读自批次 X（… 评价）」标注，R2.7 的「标注来源批次与评价
时间」落不了地。`record_extraction_log` 的**幂等重放分支**同样要回报 `batch_id`
（改造前只有首次插入路径返回该键 ⇒ 幂等重放时调用方拿不到批次号）。

**Validates: Requirements 2.3, 2.5, 2.7, 3.6, 6.2, 6.3**
