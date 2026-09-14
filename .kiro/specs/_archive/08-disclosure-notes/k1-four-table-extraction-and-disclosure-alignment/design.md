# Design Document

## Overview

本设计分两条互不耦合的主线，共用一套「不新造第二方言」的原则。

**主线 A — 四表库取数口径根治。** 不新写科目定位逻辑：把 D1 已实证跑通的
`d_cycle_extraction/d1_account_resolver.py` 中**与循环无关**的部分提升为共享模块
`app/services/four_table/report_line_accounts.py`，D1 侧改为薄壳委托（其 378 行既有守卫
即零回归证明），K1 侧用同一 API 传入自己的报表行 `BS-009` 与兜底码。`tb_balance` 聚合
从「只取最深层级」改为**叶子口径**（复用 `trial_balance_service.recalc_unadjusted` 的
leaf 判定语义，但不做方向翻转 —— 见 Property 2 的实证理由）。

**主线 B — 披露/附注结构对齐。** 以源 xlsx 为唯一裁决者，用既有幂等脚本
`backend/scripts/fix/fix_note_k_complex_structure.py`（`_aligned_by` 已是它）扩展 K1 的
plan，同步改 `k1DisclosureSyncPayload` / `k1NoteSectionMap` / `k1DisclosureModel`，
并把守卫从「模板↔载荷双向」升级为「模板↔载荷↔源 xlsx 三向」。

**主线 C — 账龄枚举贯通 K1-1**（小而独立）：把 `k1AdjudicationModel` 的固定 6 档与
`k1AdjudicationSync` 的固定段 key 改为参数化，调用方传 `useAgingConfig(projectId,'K1')`
的 `segments`。

## Architecture

```
四表入库
 ├── tb_balance.account_code          客户原始码（点号分级）  1221 / 1221.12 / 1231.03
 │        │ account_mapping(project_id, original → standard)   ← 科目映射模块
 │        ▼
 ├── trial_balance.standard_account_code  标准码（横杠分级）   1221 / 1231-03 / 1131
 │        │ report_config.formula（按 applicable_standard 精确匹配）
 │        ▼
 └── 报表行 BS-009 其他应收款
        soe_standalone : TB('1221') - TB('1231-03') + TB('1131')
        listed_*       : TB('1221')

                       ▼ 反向解析（本设计）
   app/services/four_table/report_line_accounts.py            ← 新建（共享）
     resolve_report_line_accounts(ctx, spec) -> ReportLineAccounts
       ① _fetch_applicable_standards(ctx)         projects.applicable_standard_v2
       ② resolve_report_line_account_codes(..., applicable_standards=...)
       ③ split_gross_provision(codes, account_chart)   direction/name/码族
       ④ _to_original_codes_with_flag(ctx, std_codes)  account_mapping 反解 → 极小前缀集
       ⑤ fail-open 兜底 + resolved_from 溯源
                       │
        ┌──────────────┴───────────────┐
        ▼                              ▼
 d1_account_resolver（薄壳委托，零回归）   _k1_other_receivables.py::render
                                          ├── _fetch_leaf_rows(ctx)      ← 叶子口径
                                          ├── tb_values（1221 / 1231.03 / 1131 / 1132）
                                          ├── adjudication_prefill
                                          │     nature / portfolio / provision
                                          │     + fs_reconciliation{interest,dividend,report_total}
                                          └── tb_source_codes（溯源，前端展示）
                                                    │
                        GtK1OtherReceivables（htmlData）
                          ├── tbData（只读 tb_values；兜底口径改用 provision_standard）
                          ├── K1TabAdjudication
                          │     ├── applyAdjudicationPrefill（手工优先）
                          │     ├── 「从四表库带入未审数」按钮（N1 范式）
                          │     ├── FS 三行 seed
                          │     └── 账龄行 ← useAgingConfig segments（主线 C）
                          └── K1TabDisclosureListed / Soe
                                └── useDisclosureAutoSync → sync-from-workpaper
                                      → disclosure_notes §五、8 / §八、9
```

## Components and Interfaces

### 后端

#### 新建 `backend/app/services/four_table/report_line_accounts.py`

```python
@dataclass(frozen=True)
class ReportLineAccountSpec:
    row_code: str                      # 'BS-009'
    fallback_gross: list[str]          # ['1221']
    fallback_provision: list[str]      # ['1231-03']
    provision_name_filter: str | None  # '其他应收款'（仅宽前缀兜底时叠加）
    extra_gross: list[str] = ()        # ['1131','1132'] —— 报表行未必引用，但底稿需要

@dataclass(frozen=True)
class ReportLineAccounts:
    gross: list[str]                 # 原始码前缀集（tb_balance 用）
    provision: list[str]
    gross_standard: list[str]        # 标准码集（trial_balance 用）
    provision_standard: list[str]
    extra_standard: dict[str, list[str]]   # {'1131': ['1131'], ...} 原始码
    resolved_from: str               # 'report_config' | 'fallback'
    provision_resolved_from: str
    use_provision_name_filter: bool
    def as_dict(self) -> dict       # → render 的 tb_source_codes

async def resolve_report_line_accounts(ctx, spec) -> ReportLineAccounts
# 纯函数（可单测，无 DB）：
def split_gross_provision(codes, chart_rows) -> tuple[list[str], list[str]]
def normalize_standard_prefix(code: str) -> str
def minimal_prefix_set(codes: Iterable[str]) -> list[str]
```

`d1_account_resolver` 保留全部公开名（`D1AccountCodes` / `resolve_d1_account_codes` /
`split_gross_provision` / `normalize_standard_prefix` / `to_original_codes`），实现改为
委托共享模块，`D1AccountCodes` 由 `ReportLineAccounts` 投影而来 —— 字段名与语义不变。

#### 新建 `backend/app/services/four_table/leaf_aggregation.py`

```python
@dataclass(frozen=True)
class LeafRow:
    account_code: str
    account_name: str
    opening: float
    closing: float
    debit: float
    credit: float
    direction: str

def select_leaves(rows: list[LeafRow]) -> list[LeafRow]
    """叶子 = 不存在以 `code + '.'` 开头的兄弟行。纯函数。"""

def aggregate_leaves(leaves, prefixes, *, absolute=False) -> dict[str, float]
    """按前缀集过滤后求和 opening/closing/debit/credit；absolute=True 对结果取 abs。"""
```

`select_leaves` 是纯函数 → 可用 PBT 覆盖 Property 1/3。

#### 改 `backend/app/routers/wp_render_strategies/_k1_other_receivables.py`

- 删除 `_K1_ACCOUNT_PREFIXES` 与 `_aggregate_prefix_deepest`（死代码立即删，不留 DEPRECATED）。
- `_fetch_tb_data` / `_build_adjudication_prefill` 改用 `resolve_report_line_accounts`
  + `select_leaves` + `aggregate_leaves`。
- 新增 `_build_fs_reconciliation(ctx, accounts)`：`1132`→interest、`1131`→dividend、
  `BS-009` 报表口径合计→report_total（`gross − provision + extra`，与公式符号一致）。
- `render` 返回新增 `tb_source_codes`；`account_codes` 由解析结果派生（不再写死）。
- `K1_SHEETS` 的两个披露 sheet 名改为源 xlsx 逐字值
  （`附注披露信息(上市公司）` / `附注披露信息（国企）`），与 `K1_DISCLOSURE_SHEET_NAME` 同源。

#### 改 `backend/data/prefill_formula_mapping.json`

K1-1 块补 6 条：`坏账准备期初/期末`（`TB('1231-03',…)`）、`应收股利`（`TB('1131',…)`）、
`应收利息`（`TB('1132',…)`）、`明细表原值合计`（`WP('K1','明细表K1-2','其他应收款余额期末审定数')`）、
`坏账准备期末审定`（`WP('K1','坏账准备明细表K1-3','期末审定数额')`）。K1-2 块不动（防循环）。

#### 改 `backend/scripts/fix/fix_note_k_complex_structure.py`

- `K1_LISTED_PLAN`：「按账龄披露」行改 5 年段；「本期计提、收回或转回的坏账准备情况」
  列改两级（新增 `_listed_stage_movement_cols()`）；追加 3 张表
  （`rule(..., insert=True)`）+ `text_sections` 追加 ⑧⑨⑩ 段落。
- `K1_SOE_PLAN`：「按账龄披露其他应收款项」列改 3 列 `flat` + 行补小计/减坏账/合计；
  「账龄组合」行改 6 档。
- SOE 的 `_movement_cols` 保持 `flat`（源模板国企侧确为单级：`B63` 单格即
  「第一阶段未来12个月预期信用损失」）。

### 前端

| 文件 | 改动 |
|------|------|
| `GtK1OtherReceivables.vue` | `tbSourceCodes` computed；`_loadTbData` 兜底改用 `provision_standard` 且叶子去重；`fsPrefill` 透传 |
| `k1\core\K1TabAdjudication.vue` | 「从四表库带入未审数」按钮 + FS 三行 seed + 账龄段透传 |
| `k1\core\K1FourTableSourcePanel.vue`（新建） | 展示 `tb_source_codes`（报表行 / 标准码 / 原始码 / 来源），消费 R1.7 |
| `composables/useK1Adjudication.ts` | `applyAdjudicationPrefill` 支持 `fs_reconciliation`；`agingRowDefs` 由入参 segments 派生 |
| `composables/k1AdjudicationModel.ts` | `buildK1AgingRowDefs(segments)`；`K1_AGING_ROW_DEFS` 保留为 FIVE_YEAR 默认导出（兼容） |
| `composables/k1AdjudicationSync.ts` | `aggregateK12ForK11(rows, segmentKeys)`；旧签名默认 FIVE_YEAR keys |
| `composables/k1DisclosureSyncPayload.ts` | listed 变动表两级列；listed 新增 3 表列头与行映射；soe 账龄表 3 列 + 忠实推 subtotal/provision/total |
| `composables/k1NoteSectionMap.ts` | `K1_LISTED_SUBTABLE` 追加 `govGrant` / `transfer` / `continuedInvolvement`；`K1_NOTE_TOTAL_LABEL` 单一真源 |
| `composables/k1DisclosureModel.ts` | listed payload 补 `govGrantRows` / `transferRows`（`continuedInvolvementRows` 已有） |

### 守卫

| 文件 | 作用 |
|------|------|
| `backend/tests/four_table/test_report_line_accounts.py` | 共享解析器纯函数 + 拆分 + 极小前缀集 + fail-open |
| `backend/tests/four_table/test_leaf_aggregation.py` | 叶子选取 PBT（Property 1/3） |
| `backend/tests/test_k1_adjudication_prefill.py` | 扩展：1231.03 口径、叶子完整性、FS 三行、手工优先 |
| `backend/tests/services/test_note_k1_structure.py` | openpyxl 直读源 xlsx ↔ 模板三向比对（含反向自检） |
| `composables/__tests__/k1NoteSubtableContract.spec.ts` | 追加 3 表；`columnsPending` 保持空 |
| `composables/__tests__/k1AdjudicationSync.spec.ts` | 3 年段 / 自定义段不丢桶 |
| `.github/workflows/governance-checks.yml` | job `note-k1-structure` |

## Data Models

### `tb_source_codes`（render 输出 → 前端溯源面板）

```json
{
  "row_code": "BS-009",
  "gross": ["1221"],
  "provision": ["1231.03"],
  "gross_standard": ["1221"],
  "provision_standard": ["1231-03"],
  "extra_standard": { "1131": ["1131"], "1132": ["1132"] },
  "resolved_from": "report_config",
  "provision_resolved_from": "report_config",
  "use_provision_name_filter": false
}
```

### `adjudication_prefill`（扩展）

```json
{
  "receivable_total": { "opening": 150302795.09, "closing": 269885933.03,
                        "debit": 1601611866.71, "credit": 1482028728.77 },
  "bad_debt_total":   { "opening": 639230.01, "closing": 900217.36 },
  "nature":     { "margin": {...}, "deposit": {...}, "petty": {...},
                  "intercompany": {...}, "other-nature": {...} },
  "portfolio":            { "aging": {...} },
  "portfolio_provision":  { "aging": {...} },
  "fs_reconciliation": { "interest": 0.0, "dividend": 21000000.0,
                         "report_total": 289985715.67 }
}
```

`fs_reconciliation.report_total = Σgross − Σprovision + Σextra`，符号取自 `BS-009`
公式中各 `TB()` 前的运算符，保证与报表引擎同口径。

### 国企「按账龄披露其他应收款项」子表行（对齐源模板 3 列）

```json
[
  { "label": "1年以内（含1年）", "期末数": 0, "期初数": 0, "row_kind": "data", "segment_key": "within1" },
  { "label": "小  计",        "期末数": 0, "期初数": 0, "is_total": true, "row_kind": "subtotal" },
  { "label": "减：坏账准备",   "期末数": 0, "期初数": 0, "row_kind": "provision" },
  { "label": "合  计",        "期末数": 0, "期初数": 0, "is_total": true, "row_kind": "total" }
]
```

### 上市「本期计提、收回或转回的坏账准备情况」列（两级混合分组）

```json
[
  { "key": "label",   "label": "坏账准备", "is_label": true },
  { "key": "第一阶段", "label": "未来12个月预期信用损失",              "group": "第一阶段", "format": "amount" },
  { "key": "第二阶段", "label": "整个存续期预期信用损失(未发生信用减值)", "group": "第二阶段", "format": "amount" },
  { "key": "第三阶段", "label": "整个存续期预期信用损失(已发生信用减值)", "group": "第三阶段", "format": "amount" },
  { "key": "合计",     "label": "合计",                              "format": "amount" }
]
```

标签列不打 `flat`（否则 `_extract_column_groups` 返回 `[]` 判为显式单级），
`合计` 不带 `group`（rowspan=2）—— 与 `methodColumns()` 同款混合分组范式。

## Correctness Properties

### Property 1: 叶子集合互不为前缀且金额之和等于父科目

对任意 `tb_balance` 行集与前缀 `p`，`select_leaves` 返回的叶子中不存在 `a != b` 且
`b.startswith(a + '.')`；且当行集包含 `p` 自身时，叶子在 `p` 下的金额之和等于 `p` 行的金额。

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: 备抵科目集不含其他应收款以外的备抵子科目

`resolve_report_line_accounts(BS-009)` 返回的 `provision` 原始码集，与
`{1231.01, 1231.02, 1231.05}`（应收票据/应收账款/长期应收款坏账）的交集为空；
当反解退化为宽前缀时 `use_provision_name_filter` 为真。

**Validates: Requirements 1.3, 1.4, 1.5**

### Property 3: fail-open 恒不抛且原值码集恒非空

对任意依赖缺失组合（无 report_config 行 / account_chart 空 / account_mapping 空 /
DB 抛异常），`resolve_report_line_accounts` 均返回结果、`gross` 非空、
`resolved_from == 'fallback'`；`render` 不抛异常。

**Validates: Requirements 1.6, 3.5**

### Property 4: 手工优先幂等

若 `responses_snapshot` 含任一非零 `K1-1-*-unadj`，则 `adjudication_prefill` 为空字典；
`applyAdjudicationPrefill` 在该前提下返回 `false` 且不写任何 item。FS 三行同理按项判定。

**Validates: Requirements 3.2, 3.3, 3.4**

### Property 5: 账龄聚合对任意段集合无丢失

对任意段 key 列表 `S`（3 年段 / 5 年段 / 自定义 2~10 段），
`aggregateK12ForK11(rows, S).agingGross` 长度等于 `|S|`，且各元素等于明细行
`agingAudited[S[i]]` 之和；`Σ agingGross ≤ Σ endBalance`（细分不超过总额）。

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

### Property 6: 两级表头三态自洽

对本 spec 定义的每张表，`derive_column_groups(columns)` 满足：声明了 `group` 的表返回
非空分组且分组区间连续；打了 `flat` 的表返回 `[]`；无一张表返回 `None`。

**Validates: Requirements 7.1, 8.1, 9.2**

### Property 7: 载荷子表名 ⊆ 模板表名（无孤儿子表）

`K1_LISTED_SUBTABLE` / `K1_SOE_SUBTABLE` 的每个值都逐字存在于对应 `note_template`
章节的 `tables[].name`；反之模板中属于 K1 语义的表都被某个常量引用。

**Validates: Requirements 7.3, 9.4**

### Property 8: 载荷列 key 与行对象中文键逐字一致

对每张表，`columns[].key`（除 `label`）的集合等于该表行对象（剔除 `row_kind` /
`segment_key` / `row_key` / `is_total` 等元字段）键集合的超集，且不存在行有值而
列缺失的键。

**Validates: Requirements 7.1, 8.2, 9.2**

### Property 9: 源 xlsx 三向一致

对「按账龄披露」「按账龄披露其他应收款项」「账龄组合」「本期计提、收回或转回的
坏账准备情况」四张关键表，模板 `headers` / 同步 `columns` 的叶子列名与源 xlsx
对应单元格文本逐字相等；两级表头的父列名等于源 xlsx 合并单元格首格文本。

**Validates: Requirements 7.1, 7.2, 8.1, 8.3, 9.3**

### Property 10: 报表口径合计与公式符号一致

`fs_reconciliation.report_total` 等于按 `BS-009` 公式中每个 `TB()` 前运算符加权求和的
结果（`+` → 加、`-` → 减），与 `report_engine` 对同一公式的求值在容差 0.01 内一致。

**Validates: Requirements 3.3, 1.1**

## Error Handling

| 失败点 | 处理 | 可观测性 |
|--------|------|----------|
| `report_config` 无 `BS-009` 行 / 公式为空 | 用 `spec.fallback_gross` + `fallback_provision`，`resolved_from='fallback'` | `logger.debug` + `tb_source_codes.resolved_from` 在溯源面板显示为「兜底」tag |
| `projects.applicable_standard_v2` 缺失或非法 | `derive_applicable_standards(None)` 补默认，退回「任取一条非项目级配置」 | 同上 |
| `account_chart` 查询失败 / 为空 | `split_gross_provision` 降级为码族启发（`1231` 前缀视为备抵） | `logger.debug` |
| `account_mapping` 无该项目记录 | `normalize_standard_prefix` 宽前缀兜底，并置 `use_provision_name_filter=True`（叠加「其他应收款」名称过滤） | `tb_source_codes.use_provision_name_filter` |
| `tb_balance` 查询异常 | 返回空行集 → `tb_values` 为空、`adjudication_prefill` 为 `{}` | `logger.warning` |
| 全部金额为 0 | 返回空预填（不写 0 占位） | 前端显示「四表库暂无 K1 数据」 |
| 前端兜底请求 401/失败 | `_silent` 静默，保留 render 下发值 | 控制台 warn |
| 披露同步 409 `STANDARD_MISMATCH` | 前端静默不写（宁可不写也不写错章节，平台既有约定） | 后端 warning |

原则：**render 绝不因取数失败而抛错**（Property 3）。所有新增 DB 访问都包 `try/except`
并在 except 分支 `await ctx.db.rollback()`（避免 MissingGreenlet / 事务污染后续查询）。

## Testing Strategy

**分层**

1. **纯函数单测（最重）** — `select_leaves` / `aggregate_leaves` /
   `split_gross_provision` / `minimal_prefix_set` / `buildK1AgingRowDefs` /
   `aggregateK12ForK11`。含 hypothesis PBT（`max_examples=5`，遵守平台约定），
   生成器收敛到金额域（禁无界 float，`Number.isFinite` 守卫）。
2. **fixture 用实测值** — 以项目 `0ec33ac9`/2025 的真实叶子数据作 fixture
   （1221 叶子和 = 269,885,933.03、1221.11 = 3,597,359.45、1221.12 = 55,035,942.52、
   1231.03 期末 = 900,217.36、1231.02 期末 = 26,401,719.77 作**反向断言**：
   K1 结果不得等于含 1231.02 的 28,464,225.16）。
3. **characterization** — Wave 1 的委托重构以 `test_d1_account_resolver.py` 既有 378 行
   为零回归证明；K1 render 在依赖缺失路径下与改动前逐字等价。
4. **结构守卫（三向）** — `test_note_k1_structure.py` 用 openpyxl 直读源 xlsx，
   与模板 `headers`、前端同步 `columns`（读 `.ts` 源码正则抽取）逐字比对；
   **必含反向自检**（先断言源 xlsx 里确实存在该文本，防正则失效导致断言空转）。
5. **契约守卫** — 复用共享 helper `_disclosureSubtableContract.helper.ts` 跑 P1~P6；
   `columnsPending` 逃逸阀必须保持为空。
6. **端到端实测** — chrome-devtools MCP 驱动浏览器（登录 `admin`/`admin123`，
   底稿 URL `/projects/{pid}/workpapers/{wpId}/edit`）+ postgres MCP 只读比对落库；
   实测数据必须复原。

**命令**

```
python -m pytest backend/tests/four_table backend/tests/test_k1_adjudication_prefill.py backend/tests/services/test_note_k1_structure.py -v --tb=short
python -m pytest backend/tests/d_cycle_extraction/test_d1_account_resolver.py -v
python backend/scripts/fix/fix_note_k_complex_structure.py --check
npx vitest run src/components/workpaper/composables/__tests__/k1NoteSubtableContract.spec.ts src/components/workpaper/composables/__tests__/k1AdjudicationSync.spec.ts
```

**不做的事**：不引入新的 mock 后端；不为本 spec 新建第二套四表读取路径；
不在 K1-2 明细表引入 `WP()`（防 K1-1↔K1-2 循环，`test_h1_two_level_chain` 同款约束）。
