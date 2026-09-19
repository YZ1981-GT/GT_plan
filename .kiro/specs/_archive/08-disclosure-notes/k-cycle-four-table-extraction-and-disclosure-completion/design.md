# Design Document

## Overview

本 spec 把 K1/K2 已验证的四表取数范式推广到 K3~K13，核心是**不新建机制**：
后端复用 `app/services/four_table/` 三件共享件（`report_line_accounts` 报表行解析、
`leaf_aggregation` 叶子聚合、`aux_aggregation` 辅助维度），前端复用
`shared/WpFourTableSourcePanel.vue` 溯源面板与 `composables/shared/dynamicAdjudicationRows.ts`
动态行共享件。新增的只有两类：per-cycle 的**声明**（`ReportLineAccountSpec` 与
`kXAccountScope.ts`）和一个共享的**损益口径取数件**。

设计上有三条硬约束贯穿全篇：

1. **科目码是声明不是实现** —— 每个循环只声明「我的报表行是哪个 row_code、兜底码是什么」，
   解析逻辑全在共享件里。禁止在取数路径出现科目码字面量。
2. **口径按科目性质分流** —— 资产负债类取余额（`opening`/`closing`），损益类取发生额
   （`trial_balance` 权威 + `tb_balance` 方向侧兜底），**永不用 `debit - credit`**。
3. **宁缺勿造优先于填满** —— K4/K6 三表零命中，返回空结果并留证，不臆造。

## Architecture

### 取数链路（三层映射，实证）

```
tb_balance.account_code          客户原始码（点号）      2241 / 2241.13.02 / 2801
        │  account_mapping(project_id, original → standard)
        ▼
trial_balance.standard_account_code  标准码（横杠）      2241 / 2801 / 6601
        │  report_config.formula（按 applicable_standard 挑）
        ▼
报表行  BS-075 其他应付款 soe_standalone: TB('2241','期末余额')
        BS-094 预计负债   soe_standalone: TB('2801','期末余额')
        IS-022 销售费用   soe_standalone: TB('6601','本期发生额')
```

### 后端调用图

```
render(ctx)                                   ← 各 _kX_*.py
  ├─ resolve_report_line_accounts(ctx, KX_ACCOUNT_SPEC)   [共享件，fail-open]
  │     ├─ fetch_applicable_standards         按准则挑公式
  │     ├─ resolve_report_line_account_codes  report_config → 标准码
  │     ├─ split_gross_provision              按 account_chart 方向拆原值/备抵
  │     └─ to_original_codes_with_flag        account_mapping 反解 → 原始码前缀
  │
  ├─ 资产负债类 ─ fetch_tb_balance_leaves(ctx)  [共享件]
  │     └─ select_leaves → aggregate_leaves(prefixes, absolute=?)
  │
  ├─ 损益类 ───── fetch_pl_occurrence(ctx, accounts, nature)  [本 spec 新增共享件]
  │     ├─ trial_balance 最长前缀归属（权威）
  │     └─ tb_balance 叶子的 debit（费用）/ credit（收益）兜底
  │
  ├─ build_adjudication_prefill(...)          纯函数，可独立单测
  └─ 输出 { tb_values, adjudication_prefill, tb_source_codes, parent_check }
```

### 前端消费链

```
render-config.sheets[].html_data
  ├─ tb_source_codes ──→ shared/WpFourTableSourcePanel.vue（溯源展示）
  │                        └─ composables/shared/tbSourceCodes.ts（视图模型）
  ├─ adjudication_prefill ─→ useKXAdjudication.seedFromPrefill / pullFromTB
  │                            └─ shared/dynamicAdjudicationRows.ts（动态行）
  └─ tb_values ──────────→ 审定表「与试算平衡表核对」只读行

kXAccountScope.ts（科目单一真源）
  ├─ KX_REPORT_ROW_CODE / KX_FALLBACK_STANDARD
  ├─ kXQueryCodes(src)   运行态优先 tb_source_codes.gross
  └─ kXAccountCode(src)  writebackTB / 序时账导入 / 抽凭 / EventBus / AI 共用
```

### 新增共享件：损益类发生额取数

`app/services/four_table/pl_occurrence.py`

理由：K8~K13 六个循环需要同一段逻辑（`trial_balance` 权威 + 方向侧兜底 + 归一符号），
若各写一份必然再次分叉（`debit - credit` 就是分叉产物，六处同错）。
放进 `four_table/` 与既有两件并列，保持「四表取数唯一入口」的收敛性。

`AccountNature` 枚举只有两个值：`EXPENSE`（借方增加，取 `debit`）与 `INCOME`
（贷方增加，取 `credit`）。不设第三态 —— 资产负债类走 `leaf_aggregation`，
不经本模块。

## Components and Interfaces

### 后端

| 组件 | 类型 | 职责 |
|---|---|---|
| `four_table/pl_occurrence.py` | 新增共享件 | 损益类发生额取数（`fetch_pl_occurrence` + 纯函数 `pick_occurrence` / `sum_longest_prefix_only`） |
| `four_table/k_cycle_specs.py` | 新增声明件 | K3~K13 的 `ReportLineAccountSpec` 集中声明（单一真源，供 render 与守卫共读） |
| `_k3_other_payables.py` | 改造 | 走共享件；删自造 `_is_leaf`；叶子聚合；输出 `tb_source_codes` |
| `_k4_other_current_liabilities.py` | 改造 | 宁缺勿造（三表零命中留证）；移除 `2245` |
| `_k5_provisions.py` | 改造 | 🔴 `2701` → 报表行 `BS-068`/`BS-094` 解析（兜底 `2801`） |
| `_k6_held_for_sale.py` | 改造 | 宁缺勿造；移除 `1481`/`2605` |
| `_k7_deferred_income.py` | 改造 | 走共享件（兜底 `2401`） |
| `_k8`~`_k13` | 改造 | 损益口径；删 `debit - credit`；删父子双计 |
| `scripts/fix/fix_k_cycle_prefill_presets.py` | 新增幂等脚本 | 重写 9 个错位块 + 移除 5 个孤儿块 + 清病态区间 + 补 `WP()` |
| `scripts/fix/fix_note_k_cycle_residual_structure.py` | 新增幂等脚本 | 附注残余结构修订（columns/guidance/表名/`_note_texts` title） |

### 前端

| 组件 | 类型 | 职责 |
|---|---|---|
| `composables/k{3..13}AccountScope.ts` | 新增 | 科目单一真源（11 份薄声明，范式 = `k2AccountScope.ts`） |
| `components/workpaper/shared/WpFourTableSourcePanel.vue` | 复用 | 溯源面板（props 表达循环差异，无备抵不传 `provisionLabel`） |
| `composables/shared/dynamicAdjudicationRows.ts` | 复用 | 动态审定表行 |
| `composables/disclosureAgingLabels.ts` | 复用 | 账龄枚举 → 披露口径字面 |
| `K{3..13}TabAdjudication.vue` | 改造 | 接「从四表库带入未审数」按钮 + 溯源面板 |
| `k{3..13}NoteSectionMap.ts` | 复核/修订 | 列结构按源模板；动态插行；`_removed_table_keys` |

### 关键接口签名

```python
# four_table/pl_occurrence.py
class AccountNature(str, Enum):
    EXPENSE = "expense"   # 借方增加 → 取 debit
    INCOME = "income"     # 贷方增加 → 取 credit

@dataclass(frozen=True)
class PlOccurrence:
    unadjusted: float          # trial_balance.unadjusted_amount（权威）
    audited: float             # trial_balance.audited_amount
    fallback_amount: float     # tb_balance 叶子方向侧发生额（兜底）
    source: str                # 'trial_balance' | 'tb_balance' | 'none'
    raw_sign: int              # 原始符号（-1/0/1），不静默翻正
    leaf_total: float          # 叶子之和（供「明细 == 汇总」自检）

async def fetch_pl_occurrence(ctx, accounts: ReportLineAccounts,
                              nature: AccountNature) -> PlOccurrence: ...

def sum_longest_prefix_only(rows: list[tuple[str, float]],
                            wanted: list[str]) -> float: ...
def pick_occurrence(debit: float, credit: float,
                    nature: AccountNature) -> float: ...
```

```typescript
// composables/k5AccountScope.ts（范式，其余 10 份同构）
export const K5_REPORT_ROW_CODE_LISTED = 'BS-068'
export const K5_REPORT_ROW_CODE_SOE = 'BS-094'
export const K5_FALLBACK_STANDARD = '2801'      // 🔴 不是 2701（长期应付款）
export function k5QueryCodes(src?: TbSourceCodes | null): string[]
export function k5AccountCode(src?: TbSourceCodes | null): string
```

## Data Models

### `tb_source_codes`（render 输出，前端消费）

沿用 `ReportLineAccounts.as_dict()`，K 循环新增两个可选字段：

```json
{
  "gross": ["2801"],
  "gross_standard": ["2801"],
  "provision": [], "provision_standard": [],
  "signed_codes": [["2801", 1]],
  "formula": "TB('2801','期末余额')",
  "row_code": "BS-094",
  "resolved_from": "report_config",
  "provision_resolved_from": "fallback",
  "provision_exact": false,
  "nature": "balance",
  "empty_reason": null
}
```

- `nature`: `"balance"` | `"expense"` | `"income"`，供前端选列头文案（余额 vs 发生额）
- `empty_reason`: K4/K6 专用。三表零命中时填
  `"三表零命中：account_chart/tb_balance/trial_balance 均无该科目"`，
  前端溯源面板据此显示说明而非空白（避免用户误以为坏了）

### `parent_check`（自检不变量，render 输出）

```json
{ "prefix": "2801", "leaf_sum": 0.0, "parent": 0.0, "diff": 0.0 }
```

### `adjudication_prefill`

资产负债类：`[{name, code, opening_balance, closing_balance}]`
损益类：`[{name, code, unadjusted, audited}]`（**不再有** `unadjustedDebit`/`unadjustedCredit`
双列，因为 `debit == credit` 恒成立，两列并列只会误导）

### 公式预设块（`prefill_formula_mapping.json` 的 `mappings[]`）

```json
{
  "wp_code": "K5",
  "wp_name": "预计负债审定表",
  "account_codes": ["2801"],
  "cells": [
    {"cell_ref": "期初余额", "formula": "=TB('2801','期初余额')",
     "description": "🔴 科目由报表行 BS-068/BS-094 映射解析；历史预设整块写的是税金及附加 6403，明细块写的是 2701（长期应付款）"},
    {"cell_ref": "明细表期末合计", "formula": "=WP('K5','明细表K5-2','期末余额合计')",
     "description": "🔴 反向不可：K5-2 明细表禁引 WP() 防 K5-1↔K5-2 循环"}
  ]
}
```

## Correctness Properties

### Property 1: 叶子和等于父额

对任一 K 循环、任一项目，`tb_balance` 中该循环科目的叶子行金额之和等于父科目行金额
（容差 0.01 元）。

**Validates: Requirements 2.1, 2.4**

### Property 2: 科目码来自报表行

对 K3~K13 每个循环，`tb_source_codes.gross_standard` 的每个码，要么出现在该循环
`report_config` 报表行公式解析结果中（`resolved_from == 'report_config'`），
要么等于 spec 声明的 `fallback_gross`（`resolved_from == 'fallback'`）；
不存在第三种来源。

**Validates: Requirements 1.1, 1.2, 1.5**

### Property 3: K5 不取长期应付款

K5 的 `tb_source_codes.gross_standard` 不包含 `2701`，且在报表行可解析时等于 `['2801']`。

**Validates: Requirements 1.3**

### Property 4: 宁缺勿造

K4 / K6 的 render 在任何项目上返回的 `adjudication_prefill` 为 `[]`、
`tb_values` 全 0，且 `tb_source_codes.empty_reason` 非空；
源码中不出现 `2245` / `1481` / `2605` 作科目码。

**Validates: Requirements 1.4**

### Property 5: 损益类禁净额

K8~K13 的取数源码中不存在 `debit - credit` / `debit_amount - credit_amount`
形态的表达式（`stripComments` 后断言）。

**Validates: Requirements 3.1**

### Property 6: 发生额非零可达

对至少一个真实项目，K8/K9 的 `PlOccurrence.unadjusted` 非零
（实证 6601 = 505,080,400.27、6602 = 72,957,201.11）。

**Validates: Requirements 3.2, 10.1**

### Property 7: 明细之和等于汇总

对任一 K 循环，`adjudication_prefill` 各行金额之和等于对应的汇总标量（容差 0.01 元）。

**Validates: Requirements 2.4, 3.4**

### Property 8: 无父子双计

对含父子两级的科目（如 `2241` 与 `2241.13`），汇总标量不等于「父额 + 子额之和」，
而等于父额（亦等于叶子和）。

**Validates: Requirements 2.3, 8.1**

### Property 9: 前端无错误科目码字面量

K3~K13 的前端源码（`stripComments` 后）不出现该循环的**错误**科目码
（K5 不得出现 `2701`，K4 不得出现 `2245`，K6 不得出现 `1481`/`2605`）
作科目码、请求参数或事件载荷。

**Validates: Requirements 5.2**

### Property 10: 溯源有消费方

每个 K3~K13 循环，`tb_source_codes` 至少有一个前端消费点
（`WpFourTableSourcePanel` 或等价组件）。

**Validates: Requirements 4.2, 4.4**

### Property 11: 带入不覆盖手工值

「从四表库带入未审数」对已有手工录入行不改写其金额；对四表新增的叶子科目按名建行。

**Validates: Requirements 6.1, 6.2, 6.4**

### Property 12: 预设科目属本循环

`prefill_formula_mapping.json` 中每个 K 循环块引用的科目码，均存在于标准科目表
**且**属于该循环报表行引用的科目集合（K4/K6 除外，其块不含 `TB()`）。

**Validates: Requirements 7.2, 7.6**

### Property 13: 无孤儿预设块

`prefill_formula_mapping.json` 不含 wp_code 在 `RENDERER_DISPATCH` /
`backend/wp_templates/` 中无对应循环的块（K14~K18 已移除）。

**Validates: Requirements 7.3**

### Property 14: 无病态区间

K 循环预设中不存在跨科目大类的 `TB_SUM('a~b')`（判据：区间端点一级科目码不同大类）。

**Validates: Requirements 7.4**

### Property 15: 预设不成环

K 循环审定表块可引用明细表（`WP()`），明细表块不得反引审定表。

**Validates: Requirements 7.5**

### Property 16: 披露列结构三向一致

对 K3~K13 每个循环两个变体，源 xlsx 表头（openpyxl 直读）↔ 附注模板 `headers`/`columns`
↔ 同步载荷 `columns` 三者的叶子列名逐字一致，层级结构一致。

**Validates: Requirements 8.1, 8.2, 8.3, 9.5, 10.4**

### Property 17: 单级表必须标 flat

同步载荷与附注模板 `columns` 中，源模板为单行表头的表，其列 SHALL 至少一列带 `flat`，
且不得声明 `group`（否则被 `_infer_groups_from_headers` 推出凭空父表头）。

**Validates: Requirements 8.2, 9.5**

### Property 18: 动态插行区不 seed 占位

源模板标注动态插行的表，附注模板 `rows` 不含「可无限量添加行」「项目N」「……」类占位行。

**Validates: Requirements 8.4**

### Property 19: 账龄字面走单一真源

含账龄维度的 K 循环披露表，其档位字面来自 `disclosureAgingLabels.ts`，
源码中不出现 `'1年以内（含1年）'` 等字面量。

**Validates: Requirements 8.5**

### Property 20: 附注无孤儿子表

同步后附注 `sub_table_data` 的键集 ⊆ 附注模板 `tables[].name` 集合；
被改名的旧键出现在 `_removed_table_keys` 中。

**Validates: Requirements 9.2, 9.5**

### Property 21: guidance 纯文本

K 循环附注模板所有表的 `guidance` 不含 markdown 粗体标记（`**`）。

**Validates: Requirements 9.3**

### Property 22: `_note_texts` 位置与标题

`_note_texts` 位于 `sub_table_data` 内、每条带非空中文 `title`、空文本条目被过滤。

**Validates: Requirements 9.4**

### Property 23: 守卫反向自检

每个读源码的守卫，其 `stripComments()` 均有反向自检（断言原始源码确实含被禁字样，
或对内联 fixture 断言正则有效），防断言空转。

**Validates: Requirements 10.3**

### Property 24: builder 零入参可调

K3~K13 新增/修改的 `build*Columns` 在零入参调用下返回完整列集（每列 `flat` 或 `group`
已表态），以通过平台 `disclosureColumnsCoverage` sweep。

**Validates: Requirements 10.2**

## Error Handling

**fail-open 是取数链路的铁律** —— 任何一环失败都不得阻断 render，否则整张底稿打不开。

| 失败点 | 处理 | 可观测性 |
|---|---|---|
| `report_config` 无该行 / 公式为 `None` | 用 `spec.fallback_gross` | `resolved_from='fallback'` |
| `account_chart` 查询失败 | 备抵判定降级为码族启发 | `logger.debug` |
| `account_mapping` 反解为空 | 用 `normalize_standard_prefix` 宽前缀 | `provision_exact=False` |
| `trial_balance` 无该科目 | 损益类回退 `tb_balance` 方向侧发生额 | `PlOccurrence.source='tb_balance'` |
| 三表均无该科目（K4/K6） | 返回空结果 | `empty_reason` 非空，溯源面板显示说明 |
| DB 异常 | `except Exception` + `logger.warning` + 返回空 | 日志 |

**两个反模式必须避免**（均为平台已踩过的坑）：

1. **不要把异常吞成静默零** —— `get_active_filter(ctx.project_id)` 单参调用会抛
   `TypeError` 被 `except Exception` 吞掉，取数恒空且无线索（N2/N5 各踩一次）。
   守卫必须以**真实签名**调用被测函数并断言返回非零。
2. **不要让 fail-open 掩盖契约错误** —— 前端 `Array.isArray(pf) ? pf : null` 对
   后端返回的 `dict` 恒得 `null`（N2 踩过）。契约测试断言返回类型与字段名镜像。

**破坏性操作门槛**：`fix_*` 脚本默认 `--dry-run`；`--apply` 需显式传入；
附注模板改动前先 `--check` 输出欠账清单。

## Testing Strategy

### 后端

| 层级 | 文件 | 覆盖 |
|---|---|---|
| 纯函数单测 | `four_table/test_pl_occurrence.py` | `pick_occurrence` / `sum_longest_prefix_only` + PBT |
| 科目声明守卫 | `four_table/test_k_cycle_account_scope.py` | Property 2/3/4/5/8，含**反向自检**（断言旧口径 `2701` 确实命中长期应付款） |
| 取数集成 | `test_k_cycle_extraction.py` | 以真实签名 await 调用 `_fetch_*`，断言非零（Property 6） |
| 预设守卫 | `test_k_cycle_formula_presets.py` | Property 12/13/14/15 |
| 附注结构守卫 | `test_note_k_cycle_residual_structure.py` | Property 16/17/18/20/21/22，openpyxl 直读源 xlsx 三向比对 |

### 前端

| 层级 | 文件 | 覆盖 |
|---|---|---|
| 科目真源守卫 | `__tests__/kCycleAccountScope.spec.ts` | Property 9（参数化 11 循环，`stripComments` + 反向自检） |
| 溯源消费守卫 | `__tests__/kCycleFourTableWiring.spec.ts` | Property 10/24 |
| 动态行 | `__tests__/kCycleAdjudicationRows.spec.ts` | Property 11 + PBT |
| 披露契约 | `__tests__/kCycleNoteSubtableContract.spec.ts` | 复用 `runDisclosureSubtableContract` helper（P1~P6）+ Property 19 |

### 实测（不可省略）

1. **真实 DB 直跑 render**：对至少 3 个项目（含 soe 与 listed 模板）逐循环跑 render，
   核对 `tb_source_codes.resolved_from`、`parent_check.diff == 0`、
   `adjudication_prefill` 各行之和 == 汇总标量。
2. **postgres 只读复核**：SQL 逐行验证叶子和 == 父额、损益发生额来源。
3. **浏览器实测**：审定表「从四表库带入未审数」→ 动态行增删 → 披露表录入 →
   「推送到附注」→ postgres 验 `sub_table_data` 键集 / `_column_groups` /
   `last_sync_at` 前移。
4. **数据复原**：实测写入的 `checklist_responses` 与 `disclosure_notes` 必须按
   实测前快照逐字复原。

### 已知测试陷阱

- 替身 session 必须按 SQL/params 区分「同一张表的多次查询」，否则备抵与原值返回同一行。
- `mock` 的 `get_active_filter` 返回值必须是真实 `sa.true()`，`MagicMock()` 会被
  `sa.and_` 拒绝后被 fail-open 吞成空结果 = 假绿。
- `npx vitest run -t ""` 会把全部用例判 skipped；用位置参数子串过滤。
- 读源码守卫用花括号配对截函数体，不要用固定字符窗口。
