# Design: D1 取数链路补齐与披露/附注口径修复

## Overview

本设计把 D1 的取数链路从「四表库 → 明细底稿」延伸到「审定表 → 披露表 → 附注」，
并把科目定位从硬编码前缀换成**报表规则映射驱动**。核心手法是三条：

1. **后端新增一个科目解析层**（`d1_account_resolver`），把 `report_config.formula` →
   标准码 → `account_mapping` → 项目原始码，全程 fail-open 回退到现有行为。
2. **前端抽一个共享纯函数模块 `d1AdjudicationModel.ts`**，作为「审定表锚点 → 分类合计」
   的**单一真源**，同时被审定表、披露表、D1-10、D1-11 消费 —— 从结构上消灭
   「读方与写方锚点漂移」这一类静默失效。
3. **披露/附注口径以源模板单元格公式为裁决者**逐条对齐（比率 ×100、合计行派生、
   变动表符号），并把 D1-4 的既有语义与披露变动表的语义**显式分开**，不共用一个函数。

零回归策略：后端全部改动在 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 分支内或纯 additive
输出键；前端共享模块以「读同一批既有锚点」为唯一行为改变点，取不到数时行为与现状一致
（回落手工录入）。

## Architecture

```
┌─ 后端 ────────────────────────────────────────────────────────────────────┐
│ report_config.formula (BS-005)                                            │
│        │ resolve_report_line_account_codes                               │
│        ▼                                                                  │
│ 标准码 ['1121','1231-01']                                                 │
│        │ d1_account_resolver.split_gross_provision(account_chart)         │
│        ▼                                                                  │
│ {gross:['1121'], provision:['1231-01']}                                   │
│        │ d1_account_resolver.to_original_codes(account_mapping)           │
│        ▼                                                                  │
│ {gross:['1121'], provision:['1231.01']}   ← tb_balance 用原始码            │
│        │ d1_detail_seed._fetch_leaves(叶子 only, get_active_filter)        │
│        ▼                                                                  │
│ responses_snapshot: D1-cat-rows / D1-bd-portfolio-rows  (transient seed)  │
│ html_data.tb_source_codes                                (取数溯源)       │
│ /d1/import-aux-balance  ← tb_aux_balance(aux_type='客户') → D1-cust-rows  │
└───────────────────────────────────────────────────────────────────────────┘
                                   │ checklist_responses
┌─ 前端 ────────────────────────────▼──────────────────────────────────────┐
│ d1AdjudicationModel.ts  (纯函数 · 单一真源)                              │
│   ANCHOR = (rowKey, field) => `D1-adj-${rowKey}-${field}`                │
│   readCategoryRows(allResponses)     → 动态票据种类行（含 slug）          │
│   readAdjudicationTotals(allResponses) → {gross,provision,net} × 双期    │
│        ├────────────► useD1Adjudication   (D1-1 三区块，写入方)          │
│        ├────────────► useD1Disclosure     (①分类表，读取方)              │
│        ├────────────► useD1InventoryCount (D1-10 账面余额)               │
│        └────────────► useD1RelatedPartyCheck (D1-11 期末余额)            │
│                                   │                                      │
│                  buildD1SyncPayload（口径修复：pct / 合计派生）           │
│                                   ▼                                      │
│               附注 五、4 / 八、4 (sub_table_data + columns)               │
└──────────────────────────────────────────────────────────────────────────┘
```

### 断点修复对照

| 断点 | 修复位置 | 手法 |
|------|----------|------|
| 硬编码 1121/1231 | `d1_account_resolver.py`（新） | 报表映射 + account_mapping，fail-open |
| D1-4 → D1-1 坏账 | `useD1BadDebt`（新增按票据种类小计块）+ `useD1Adjudication`（override） | 镜像源模板 R23/R24 |
| 动态票据种类无落点 | `d1AdjudicationModel.readCategoryRows` + anchor 正则扩展 | 银承/商承固定在前 + 动态追加 |
| D1-1 → 披露主表 | `useD1Disclosure` 改用共享模块 | 删除 `CROSS_SHEET_KEYS` 常量 |
| D1-10 / D1-11 | 同上 | 删除 `D1-adj-notes-receivable-current-audited` |
| D1-3 无 aux 取数 | 后端端点 + `useD1DetailCustomer` | 复用 F1/D2 归集范式 |

## Components and Interfaces

### 后端

#### `backend/app/services/d_cycle_extraction/d1_account_resolver.py`（新）

```python
D1_REPORT_ROW_CODE = "BS-005"          # 实证：report_config 四准则均为 BS-005
D1_FALLBACK_CODES = ["1121", "1231-01"]

@dataclass(frozen=True)
class D1AccountCodes:
    gross: list[str]        # tb_balance 可用的**原始码**前缀集
    provision: list[str]
    gross_standard: list[str]
    provision_standard: list[str]
    resolved_from: str      # 'report_config' | 'fallback'

def split_gross_provision(codes, chart_rows) -> tuple[list[str], list[str]]:
    """按备抵科目判定拆分（direction=='credit' 或名含 坏账准备/减值准备）。纯函数。"""

async def resolve_d1_account_codes(ctx) -> D1AccountCodes:
    """报表映射 → 拆分 → account_mapping 反解原始码。全程 fail-open。"""

def normalize_standard_prefix(code: str) -> str:
    """'1231-01' → '1231'（无 account_mapping 时的兜底前缀）。"""
```

`resolve_d1_account_codes` 内部顺序：
1. `resolve_report_line_account_codes(db, project_id, 'BS-005', fallback=D1_FALLBACK_CODES)`
2. 查 `account_chart`（`project_id` + `source='standard'`）取 `direction` / `account_name` → `split_gross_provision`
3. 查 `account_mapping`（`project_id`，`standard_account_code IN (...)`, `is_deleted=false`）
   → 原始码集；空则 `normalize_standard_prefix`
4. 任一步异常 → 用 `D1_FALLBACK_CODES` 走同一拆分/兜底路径，`resolved_from='fallback'`

#### `d1_detail_seed.py`（改）

- `_fetch_leaves(ctx, prefixes: list[str], *, name_contains=None)`：入参由单前缀改为**前缀集**
  （`or_(*[startswith(p)...])`），叶子判定不变。
- `seed_d1_detail_rows(ctx, snapshot, codes: D1AccountCodes | None = None)`：`codes` 为 None 时
  自行解析；坏账侧仅当 `resolved_from == 'fallback'` 才继续用 `name_contains='应收票据'`
  （报表映射已精确到 `1231-01`，再叠名称过滤会误杀）。

#### `_d1_notes_receivable.py`（改）

- 灰度分支内先 `codes = await resolve_d1_account_codes(ctx)`，传给 seed。
- `html_data['tb_source_codes'] = asdict(codes)`（additive）。
- `project_context['tb_amount_*']` 的 `1121%` 查询改用 `codes.gross_standard`
  （`trial_balance` 存标准码）；新增 `tb_provision_amount`（`codes.provision_standard`）。

#### `_d1_import_export.py` / D1 路由（改）

新增 `POST /api/workpapers/{wp_id}/d1/import-aux-balance`：
按 `codes.gross`（原始码）+ `aux_type='客户'` + `get_active_filter` 归集
→ 返回 `{imported_count, rows:[{customerName, noteTypes, priorUnadjusted, increase, decrease, endUnadjusted}], tb_total}`。
**不落库**，由前端合并进 `D1-cust-rows` 后走既有保存路径（与 F1 的落库式不同：D1-3 下游
不做级联，transient 返回即可；若实测发现 D1-1 需要 D1-3 级联再改落库）。

### 前端

#### `composables/d1AdjudicationModel.ts`（新，零依赖 leaf）

```ts
export const D1_ADJ_PREFIX = 'D1-adj-'
export type D1AdjSection = 'gross' | 'bd' | 'net'
export type D1AdjField = 'prior-unadj' | 'prior-aje' | 'prior-rje'
                       | 'current-unadj' | 'current-aje' | 'current-rje' | 'reason'

/** 唯一锚点构造器；与 d_cycle_anchor_registry.json 的 D1 模式锚点同构。 */
export function d1AdjAnchor(section: D1AdjSection, slug: string, field: D1AdjField): string

/** 票据种类 → 锚点 slug（bank / commercial / 其余取稳定 hash-free slug）。 */
export function d1CategorySlug(category: string): string

/** 从 D1-cat-rows 读实际票据种类（银承/商承固定在前，其余按 D1-2 顺序）。 */
export function readD1Categories(allResponses: ReadonlyMap<string, Resp>): D1Category[]

/** 从 D1-4 读按票据种类小计（新区块 D1-bd-notetype-rows）。 */
export function readD1BadDebtByNoteType(allResponses): Record<string, D1PeriodAmounts>

/** 审定表三区块合计（审定数现算 = 未审+账项+重分类）。披露/监盘/关联方共用。 */
export function readD1AdjudicationTotals(allResponses): {
  categories: D1Category[]
  gross: Record<string, D1PeriodAmounts>
  provision: Record<string, D1PeriodAmounts>
  net: Record<string, D1PeriodAmounts>
  grossTotal: D1PeriodAmounts
  provisionTotal: D1PeriodAmounts
  netTotal: D1PeriodAmounts
  hasData: boolean
}
```

`D1PeriodAmounts = { priorUnadj, priorAje, priorRje, priorAudited, currentUnadj, currentAje, currentRje, currentAudited }`。

#### `useD1Adjudication.ts`（改）

- `GROSS_ROWS` / `BAD_DEBT_ROWS` / `NET_VALUE_ROWS` 由常量改为 `readD1Categories` 派生。
- 坏账区块新增 override：`readD1BadDebtByNoteType` 命中则写值 + `isFromCrossSheet=true`；
  未命中则可编辑且 `isFromCrossSheet=false`。
- 新增 `crossCheckRows`：`D1-2 合计 vs 原值小计`、`D1-4 合计 vs 坏账小计` 两条提示行。

#### `useD1BadDebt.ts`（改）

新增「按票据种类小计」区块（持久化键 `D1-bd-notetype-rows`），行名逐字
「银行承兑汇票小计」「商业承兑汇票小计」+ 动态票据种类；提供与 D1-4 合计的勾稽提示。
**不做按原值比例分摊**（坏账按单项/组合计量，比例分摊无审计依据）。

#### `useD1Disclosure.ts`（改）

删除 `CROSS_SHEET_KEYS`，`crossSheetData` / `categorySummaryRows` 改由
`readD1AdjudicationTotals` 驱动；`canEditCategorySummary = !hasData` 语义不变。

#### `d1NoteSectionMap.ts`（改）

- 国企组合表 `loss_rate: pct(r.lossRate)`。
- `mergePortfolio` / `individualTable` 合计行损失率改派生（`ratioOfPct(provisionSum, balanceSum)`）。

#### `useD1FormulaEngine.ts`（改，additive）

新增 `calcDisclosureBadDebtEnd(prior, provision, reversal, writeOff, transfer, other)`
= `prior + provision − reversal − writeOff − transfer − other`（源模板 `B100`/`G48`）。
**`calcBadDebtEndBalance` 保持不变**（D1-4 语义：`其他增加` 为加项）。

### 数据/配置文件改动

| 文件 | 改动 |
|------|------|
| `backend/data/d_cycle_extraction/d_cycle_anchor_registry.json` | D1 模式锚点正则扩展为接纳动态 slug + 新增 `D1-bd-notetype-rows` |
| `backend/data/prefill_formula_mapping.json` | D1 sheet 名纠正、`TB_AUX` 维度纠正、补 D1-2 / D1-4 / D1-1 条目 |
| `backend/data/report_note_linkage.json` | 补 BS-005 → 五、4 / 八、4 |

## Data Models

### `tb_source_codes`（render 新增输出）

```json
{
  "gross": ["1121"],
  "provision": ["1231.01"],
  "gross_standard": ["1121"],
  "provision_standard": ["1231-01"],
  "resolved_from": "report_config"
}
```

### `D1-bd-notetype-rows`（D1-4 新区块，`checklist_responses.remark` JSON）

```json
[
  {"rowId":"bdnt-bank","noteType":"银行承兑汇票小计","isFixed":true,
   "priorUnadjusted":0,"priorAje":0,"priorRje":0,
   "currentUnadjusted":0,"currentAje":0,"currentRje":0}
]
```

### `D1-cust-rows` 取数列（D1-3，既有结构增补字段）

`noteTypes: string`（票据种类，多种以「/」连接）—— 由 aux 归集写入，手工可改。

## Correctness Properties

### Property 1: 报表映射解析恒不阻断且可回退
对任意 `report_config` 状态（缺行、公式为空、抛异常），`resolve_d1_account_codes` 恒返回
非空 `gross`，且 `resolved_from` 正确标注来源。

**Validates: Requirements 1.1, 1.5, 1.7**

### Property 2: 备抵科目拆分正确
对任意标准码 + `account_chart` 组合，`split_gross_provision` 把 `direction='credit'` 或
名含「坏账准备」/「减值准备」的码归入 `provision`，其余归入 `gross`，且两集合无交集、并集 = 入参。

**Validates: Requirements 1.2**

### Property 3: 原始码反解不丢科目
`to_original_codes` 对任意 `account_mapping` 子集，返回的原始码集经前缀匹配 `tb_balance`
所覆盖的叶子集合 ⊇ 直接用标准码前缀匹配所覆盖的叶子集合（即反解只会更准，不会更少）。

**Validates: Requirements 1.3, 1.4**

### Property 4: 锚点单一真源
`d1AdjudicationModel` 导出的全部锚点字符串均匹配 `d_cycle_anchor_registry.json` 的 D1
锚点（精确或模式），且 D1 各 composable 中不存在该模块以外构造的 `D1-adj-*` 字面量。

**Validates: Requirements 3.1, 3.5, 8.1**

### Property 5: 审定数派生一致
对任意锚点取值，`readD1AdjudicationTotals` 算出的 `currentAudited` 恒等于
`useD1Adjudication` 渲染的对应行 `currentAudited`（同一纯函数，不存在两套算法）。

**Validates: Requirements 3.1, 3.2**

### Property 6: 净值恒等
对任意票据种类，`net.currentAudited == gross.currentAudited − provision.currentAudited`
（源模板 `D1-1!F16=F8-F12`），期初同理。

**Validates: Requirements 2.1, 2.6**

### Property 7: 动态票据种类不丢金额
D1-2 任意类别集合下，审定表原值小计恒等于 D1-2 各类别期末未审之和（不再因类别名不含
「银行」/「商业」而丢失）。

**Validates: Requirements 2.4, 2.5**

### Property 8: 比率列口径统一为百分数
`buildD1SyncPayload` 输出的所有 `ratio` / `loss_rate` / `end_loss_rate` / `prior_loss_rate`
字段，对任意快照输入均满足「等于对应分数 × 100」，包含合计行（合计行按合计金额现算）。

**Validates: Requirements 6.1, 6.2**

### Property 9: 变动表符号与源模板一致
`calcDisclosureBadDebtEnd` 对任意输入满足 `期末 = 期初 + 计提 − 收回或转回 − 核销 − 转销 − 其他`，
且与 `d1DisclosureConsistency` 的 F4-7 判定值逐分相等；`calcBadDebtEndBalance` 行为不变。

**Validates: Requirements 6.3, 6.4**

### Property 10: 灰度关时零回归
`D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED=False` 时，D1 render 的 `html_data` 与本 spec
改动前逐字节等价（不含 `tb_source_codes` 等新键）。

**Validates: Requirements 1.7**

### Property 11: aux 归集宁缺勿造
`tb_aux_balance` 无「客户」维度或无匹配科目时，导入端点返回 `imported_count=0` 且
`rows=[]`，不抛错、不写入。

**Validates: Requirements 4.3, 4.4**

### Property 12: 预设指向真实 sheet 与维度
`prefill_formula_mapping.json` 中 D1 全部条目的 `sheet` ∈ 源模板 sheet 名集合，
`TB_AUX` 第二参数 ∈ 平台已知 `aux_type` 集合，且明细表侧无 `WP()`。

**Validates: Requirements 5.1, 5.2, 5.4, 5.5**

## Error Handling

| 环节 | 失败模式 | 处置 |
|------|----------|------|
| `resolve_report_line_account_codes` | `report_config` 无 BS-005 / 公式为空 / DB 异常 | 回退 `D1_FALLBACK_CODES`，`resolved_from='fallback'`，`logger.debug` |
| `account_chart` 查询 | 表空 / 项目无 standard 行 | 按码族启发（`1231*`/`15xx` 计提类前缀）拆分；再失败则全部归 `gross` 并把 fallback 的 `1231-01` 归 `provision` |
| `account_mapping` 反解 | 无记录 / 全 `is_deleted` | `normalize_standard_prefix` 兜底（等价于改动前行为） |
| `_fetch_leaves` | SQL 异常 | 该侧跳过 seed，`logger.warning`，不阻断 render（既有 fail-open 语义不变） |
| `/d1/import-aux-balance` | 无「客户」维度 / 无匹配科目 | `200 {imported_count: 0, rows: []}`，前端提示「辅助余额表无客户维度数据」 |
| `readD1AdjudicationTotals` | 锚点缺失 / JSON 损坏 | 返回全 0 + `hasData=false` → 披露主表回落手工录入（现状行为） |
| `buildD1SyncPayload` | 快照字段缺失 | `num()`/`str()` 归零/空串（既有语义），不抛错 |
| 披露同步 POST | 409 `STANDARD_MISMATCH` | 前端静默不写（既有平台语义：宁可不写也不写错章节） |

原则：**取数类失败一律 fail-open 降级为手工录入**，绝不阻断 render 或让用户看到崩溃页；
**写入类失败必须提示用户**（保存失败静默会让数据丢了没人发现）。

## Testing Strategy

| 层 | 文件 | 覆盖 |
|----|------|------|
| 后端纯函数 | `backend/tests/d_cycle_extraction/test_d1_account_resolver.py` | Property 1/2/3 + 反向自检（credit 科目必判 provision；构造「无 account_mapping」必回退前缀） |
| 后端集成 | `test_d1_render_prefill_integration.py`（扩展） | Property 10 灰度关逐字节等价；`tb_source_codes` 结构；真实叶子 seed 值 |
| 后端端点 | `test_d1_aux_import.py` | Property 11 + 客户合并语义 + `get_active_filter` 去重（实证 aux 数据 2× 冗余） |
| 后端配置 | `test_d1_prefill_presets.py` | Property 12（sheet 名 ∈ 源模板 sheet 集、`TB_AUX` 维度 ∈ 已知集、明细表无 `WP()`） |
| 前端纯函数 | `d1AdjudicationModel.spec.ts` | Property 4/5/6/7；与 `d_cycle_anchor_registry.json` 正则交叉校验 |
| 前端源码守卫 | `d1AnchorSingleSource.spec.ts` | Property 4：扫源码禁止模块外 `D1-adj-*` 字面量（先 `stripComments`，带反向自检） |
| 前端口径 | `d1DisclosureRateUnit.spec.ts` / `d1MovementSign.spec.ts` | Property 8/9（含 PBT，金额域有界生成器，禁 `±Infinity`） |
| 契约 | `d1NoteSubtableContract.spec.ts`（既有） | 子表名/列头/两级表头与模板逐字 |
| 活体 | Wave 6.3 | chrome-devtools 驱动 + postgres 只读比对落库 |

关键反回归点：**修 fixture 时必须改成引用共享常量**（Requirement 8.2）—— 现有
`useD1Disclosure.pbt.spec.ts` 正是因为镜像了同款错误锚点字面量，才让断点 4 恒绿而生产恒死。
