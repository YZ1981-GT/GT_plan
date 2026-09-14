# Design Document: K0 管理循环函证源模板对齐

## Overview

本设计把 K0 的五类缺口拆成**四类落点**，每类的改动半径与并发风险不同：

| 落点 | 文件 | 并发风险 | Wave |
|---|---|---|---|
| ① K0 专属新建件 | `confirmation/k0-confirmation/**` 新增 4 个模块 | 无（新文件，仅 K0 消费） | 2 |
| ② 后端数据与守卫 | `prefill_formula_mapping.json` 修订脚本 + `backend/tests/test_k0_*.py` | 低（K0 块隔离 + 新测试文件） | 1/2 |
| ③ 共享件按循环扩展 | `confirmationColumnSpec.ts` / `cycleConfirmationMeta.ts` / `ConfirmationSampling.vue` / `memoTemplates.ts` / `entityVerifyTypes.ts` | 中（G0 spec 同批） | 3 |
| ④ 共享件门控与渠道列 | `GtConfirmationSummary.vue`（加 `isK0`）/ `reliability/ReliabilityGrid.vue` | **高（F0 spec 正在跑、G0 spec 13:16 刚改过 ReliabilityGrid）** | 3（须等 F0 收口） |

核心设计判断三条（**2026-08-04 按平台现状修正**）：

**判断 1 — 矩阵沿用 H0 已确立的范式，不做统一内核重构。** 平台现有**三份**品种矩阵：`e0SummaryMatrix.ts`（6 品种 × 6 指标）/ `f0SummaryAggregation.ts`（4 品种 × 8 指标）/ `h0SummaryMatrix.ts`（动态品种 × 8 指标）。H0 落地时已明确写下范式与理由：**复用 `safeRatio` / `sumByCategory` 两个纯函数，指标与品种常量各自声明**，因为「一侧源模板改动不应波及另一侧」。K0-1 的 8 指标与公式与 F0/H0 逐条同构，故新建 `k0SummaryMatrix.ts` 沿用同法即可。

> 初稿曾设计成「泛化 `x0SummaryMatrix` 内核 + F0/E0 改薄壳」，已撤回：重构半径覆盖 E0（已收口）/ F0（正在跑）/ H0（刚归档）/ G0（13/23 在跑）四个 spec，且要吸收 E0 侧「分母为 0 返 `0`」与 F0/H0 侧「返 `null`」这一既有差异，风险显著高于「少三份常量声明」的收益。三份并存这件事登记为平台级观察项，不在本 spec 处置。



**判断 2 — `send_memo` 伪列撤回但字段保留。** 源模板 `C5:F5` 是合并单元格分组表头，不是数据列。撤回列即可消除源模板不存在的自由文本输入位，但既有项目可能已在该列填过值 → 字段保留 + 只读提示，符合「数据零丢失红线」。同族的分段归属修正（把 `sample_purpose`/`entity_name`/`account_type`/`amount` 移入 `send_memo` 段）**只改 `group`，不改 `key`**，故不影响任何持久化数据。

**判断 3 — 列标签与剔除列一律走既有 per-cycle 机制，不改 BASE。** `account_type` 的 key 已被 E0/F0/H0 的矩阵 `sumByCategory` 消费，改 key 会打断三个循环的矩阵聚合；而 label 必须按各自源模板（`confirmationColumnSpec.ts` 文件头铁律原文「各枢纽源模板用词不同不强行统一」）。`CYCLE_COLUMN_LABEL_OVERRIDES` 与 `CYCLE_EXCLUDED_COLUMNS` 两个机制**已由 H0/G0 建好并在用**（前者现含 `G0`/`H0` 两 key），K0 只需各增一个 key。K0 与 G0/H0 的列集差异实证为**同款**：三者源模板都没有联系人/联系电话/币种，都把「函证方式」当渠道（`send_channel` variant，DV `邮寄/跟函/电子函证/其他`），都保留 `confirmation_method` 作显式登记的源外保留列（准则 1312 的积极式/消极式）。故 K0 的处置逐条对齐 G0/H0，不另起一套。

**判断 4 — 分段归属与 G0/H0 对齐，不新建结论段。** `confirmationColumnSpec.ts` 现有注释已指明：G0/H0 的行级结论列用 `row_summary`（「行级审计结论」）组「而非 K0/L0 的 `send_memo`」—— 即 K0/L0 的现状已被认定为待修正项。故 K0 把 `row_conclusion` 移入 `row_summary`，与三个循环统一，不新建第三个结论段。

## Architecture

```
                     ┌─────────────────────────────────────────┐
                     │ 源 xlsx（唯一裁决者）                    │
                     │ backend/wp_templates/K/K0 管理循环函证    │
                     └────────────────┬────────────────────────┘
                                      │ openpyxl 直读（守卫）
              ┌───────────────────────┴───────────────────────┐
              │                                               │
   ┌──────────▼──────────┐                        ┌───────────▼───────────┐
   │ 后端守卫             │                        │ 前端守卫               │
   │ test_k0_source_      │                        │ k0ColumnAlignment      │
   │   template_facts.py  │                        │ k0SummaryLowerZone     │
   │ test_k0_formula_     │◄──── 交叉锁死 ────────►│ k0MatrixConfig         │
   │   presets.py         │      （读对侧源码）     │ reliabilityChannelCols │
   └──────────┬───────────┘                        └───────────┬───────────┘
              │                                                │
   ┌──────────▼──────────────────┐        ┌────────────────────▼──────────────────┐
   │ 后端数据                     │        │ 前端实现                               │
   │ prefill_formula_mapping.json │        │ ① K0 专属：k0MatrixSpec / k0LowerZone  │
   │  （K0 块：sheet 名 + 科目 +   │        │ ② 共享扩展：列标签覆盖 / 分段 / 话术    │
   │    矩阵账面金额两格）         │        │ ③ 共享泛化：X0 矩阵内核（8 指标）      │
   └──────────────────────────────┘        └───────────────────────────────────────┘
                                                             │
                                            ┌────────────────▼────────────────┐
                                            │ 取数来源（不新建通路）           │
                                            │ BS-009 → K1 render-config       │
                                            │ BS-050 → K3 render-config       │
                                            │ （缺失返 undefined 而非 0）      │
                                            └─────────────────────────────────┘
```

数据流（K0-1 下区矩阵）：

```
上区 grid rows（ConfirmationRow[]）
   │  account_type = 「其他应收款」|「其他应付款」（源 E 列）
   │  amount / confirmed_amount / alt_confirmed（源 F / U / Y 列）
   ▼
buildX0SummaryMatrix({ rows, categories, bookAmounts, manualOverrides, zeroDenominator })
   │  8 指标 × N 品种 → X0MatrixCell[][]
   ▼
K0SummaryLowerZone.vue「一、函证情况」表格
   ▲
   │ bookAmounts（可手工覆盖，手工优先）
   └── loadK0MatrixSources()：K1(BS-009 净额) / K3(BS-050) render-config
```

## Components and Interfaces

### 新建（K0 专属）

**`confirmation/k0-confirmation/k0MatrixSpec.ts`** — K0 品种矩阵声明式配置（单一真源）

```ts
export interface K0CategorySpec {
  /** 品种名，必须与 grid 的 account_type 取值一致 */
  category: '其他应收款' | '其他应付款'
  /** 源模板单元格出处 */
  sourceRef: string           // '函证结果汇总表K0-1!E28' | '!F28'
  /** report_config 报表行（row_code 精确匹配，非 row_name） */
  reportRowCode: 'BS-009' | 'BS-050'
  /** 兜底与展示用科目码；运行态取数一律走 four_table 语义定位，不据此查询 */
  fallbackAccountCodes: readonly string[]
  /** 取数口径说明（溯源 tooltip） */
  amountHint: string
  /** 提供账面金额的相邻循环 wp_code */
  bookAmountFrom: 'K1' | 'K3'
}

export const K0_MATRIX_CATEGORIES: readonly K0CategorySpec[]
/** 8 指标标签（逐字取自源 C29:C36），与共享内核的 metric 顺序一一对应 */
export const K0_MATRIX_METRIC_LABELS: readonly string[]
```

**`confirmation/k0-confirmation/k0LowerZoneSpec.ts`** — 下区四块声明（标签/placeholder/持久化键/源出处）

```ts
export interface K0SampleSelectionItem {
  key: string          // 复用替代程序抽样字段族名，不新造
  label: string        // '测试范围' 等，逐字源 I28..I34
  placeholder: string  // 逐字源 J28..J34 示例文字
  sourceRef: string
}
export interface K0AuditNoteItem {
  key: string
  label: string        // 逐字源 S28/X28/S32/X32/S36
  sourceRef: string
  /** 非空时表示只读引用既有共享字段（如 note_alternative），不重复录入 */
  aliasOf?: string
  /** 源模板把一句话拆两格时的合并结果（X29+X30） */
  inlineHint?: string
}
export const K0_SAMPLE_SELECTION: readonly K0SampleSelectionItem[]   // 6 项
export const K0_AUDIT_NOTES: readonly K0AuditNoteItem[]              // 5 项
export const K0_REFERENCE_CONCLUSIONS: readonly { key: 'A'|'B'|'C'; text: string }[]
export const K0_GUIDANCE_BLOCKS: readonly { title: string; items: readonly string[]; sourceRef: string }[]
export const K0_INDEX_TYPO_MAP: readonly { sourceRef: string; literal: string; intended: string; note: string }[]
```

**`confirmation/k0-confirmation/K0SummaryLowerZone.vue`** — 下区四块渲染（K0 专属展示组件）

- props：`rows`（上区 grid）/ `readonly` / `wpId` / `projectId` / `wpCode`
- 四个 `el-collapse-item`：函证情况矩阵（表格）/ 样本选择（6 个 textarea + placeholder）/ 审计说明（5 个 textarea + AI + 复核）/ 审计结论（结论选择 + textarea）
- 编制说明以 `details` 折叠置底；矩阵账面金额行可手工录入（`el-input`，手工优先）
- 金额一律走 `displayPrefs.fmtAmount()`（setup 顶层 inject，不在函数体内取 store）

**`confirmation/k0-confirmation/k0SummaryMatrix.ts`** — K0 矩阵纯函数（沿用 H0 范式）

```ts
import { safeRatio, sumByCategory } from '../composables/f0SummaryAggregation'

/** 8 指标标签（源 C29:C36 逐字，去尾冒号）+ 锚点（守卫交叉比对） */
export const K0_MATRIX_METRIC_LABELS: readonly string[]      // 8 项
export const K0_MATRIX_METRIC_ANCHORS: readonly string[]     // ['C29'..'C36']
/** 唯一可手填的指标下标（源 R29 手填行） */
export const K0_MATRIX_EDITABLE_METRIC_INDEX = 0

export function buildK0SummaryMatrix(input: {
  rows: readonly ConfirmationRow[]
  bookAmounts?: Partial<Record<string, number>>
  manualOverrides?: Record<string, number>   // key = `${category}::${metric}`
}): X0MatrixCell[][]
```

与 H0 的差异仅两处：品种为**固定 2 个**（源 `E28`/`F28`，非动态可扩位）；账面金额来源为 K1(`BS-009` 净额) / K3(`BS-050`)。`safeRatio`/`sumByCategory` **只引用不修改** ⇒ E0/F0/H0 三份矩阵渲染结果逐字节不变。

### 共享件按循环扩展

**`confirmationColumnSpec.ts`**（三个机制中两个已存在，只增 K0 声明）
- `VARIANT_COLUMN_DEFS.send_memo` 删除（伪列）；`row_conclusion` 的 `group` 由 `send_memo` 改 `row_summary`（对齐 G0/H0）
- `CYCLE_VARIANT_COLUMNS.K0/L0`：`['send_memo','row_conclusion']` → `['send_channel','row_conclusion']`（`send_channel` 已由 G0/H0 建好）
- `CYCLE_EXCLUDED_COLUMNS.K0`（现为 `[]`）：增 `contact_person`/`contact_phone`/`currency`，与 G0/H0 同款
- `CYCLE_COLUMN_LABEL_OVERRIDES`（**已存在**，现含 `G0`/`H0`）：增 `K0` 键，13 处 label + `confirmation_method` → 「函证类型（积极式/消极式）」
- **新增** `CYCLE_COLUMN_GROUP_OVERRIDES: Partial<Record<ConfirmCycle, Record<string, ColumnGroup>>>`（现不存在），K0 声明 6 处（4 列入 `send_memo` 段 + 2 列入 `reply_amount` 段）；默认缺省 ⇒ 未声明循环逐字节不变
- `resolveConfirmationColumns(cycle)` 在合并 group 后套用 group override（label override 逻辑已在）

**`cycleConfirmationMeta.ts`** — 新增可选 `indexTypoMap`（源模板笔误登记），K0 声明三条；其余循环缺省 `undefined` ⇒ 行为不变

**`memoTemplates.ts`** — 通用两段话术补「工号为〔staff_no〕（如有）」占位与「确认其确实于〔visit_date〕接待跟函人员」核实要点；E0 五段逐字不变

**`entityVerifyTypes.ts`** — additive 六字段：`second_send_address` / `second_send_zipcode` / `second_send_contact` / `second_send_phone` / `second_send_fax` / `second_info_match`

**`reliability/ReliabilityGrid.vue`** — 12 个渠道字段按 `reply_method` 分组展开录入位置；`G:M` 七列加父表头「期末未收回原件函证可靠性验证」

### 后端

**`backend/scripts/fix/fix_k0_prefill_presets.py`**（幂等，`--dry-run`/`--check`/`--apply` + round-trip 自检）
- K0 块 `sheet`：`审定表K0-1` → `函证结果汇总表K0-1`
- `account_codes`：`['1221']` → 其他应收款与其他应付款两侧
- `cells`：审定表口径两格 → 矩阵账面金额两格（`E29`/`F29`），公式按 `BS-009` 净额口径与 `BS-050` 口径
- 校验器只扫语义字段（`formula`/`formula_type`/`account_codes`/`applies_when`），不扫 `description`/`notes`

## Data Models

### 持久化载荷（K0-1 下区，新增键）

存于 `working_paper.parsed_data.html_data['函证结果汇总表K0-1']`，与上区 `rows` 同一 payload（`_format: 'confirmation-v1'`），新增顶层键：

```ts
interface K0LowerZonePayload {
  /** 矩阵账面金额手工值：key = `${category}::${metric}` */
  k0_matrix_overrides?: Record<string, number>
  /** 二、样本选择 6 项（key 取自替代程序抽样字段族） */
  k0_sample_selection?: Record<string, string>
  /** 三、审计说明 5 项（aliasOf 项不落此处，读写既有 notes 字段） */
  k0_audit_notes?: Record<string, string>
  /** 四、审计结论 */
  k0_conclusion?: { ref_option?: 'A' | 'B' | 'C'; text?: string }
}
```

零回归：全部可选键；旧 payload 读回为 `undefined`；写回时空值不产生键（不制造 `undefined` 噪声）。既有 `sampling`/`notes`/`conclusion` 键**不动**（Requirement 3.8 的 aliasOf 项直接读写它们）。

### 矩阵单元格

```ts
interface X0MatrixCell {
  category: string
  metric: string
  /** null = 无法计算（分母缺失）→ 渲染「-」 */
  value: number | null
  kind: 'amount' | 'ratio'
  /** 仅「本期（期末）账面金额」行为 true */
  editable: boolean
  sourceHint?: string
}
```

### 报表行映射（`report_config` 实证，2026-08-04 只读查询）

| 品种 | row_code | `soe_standalone` 公式 | 备注 |
|---|---|---|---|
| 其他应收款 | `BS-009` | `TB('1221') − TB('1231-03') + TB('1131')` | **净额口径**；`listed_*`/`soe_consolidated` 为 `TB('1221')` |
| 其他应付款 | `BS-050` | `TB('2241') + TB('2231')` | `*_consolidated` 为 `TB('2241')`；**`BS-075` 同名行 formula 为 NULL，必须按 row_code 匹配** |

### 源模板笔误登记（不改源 xlsx）

| 源出处 | 源模板字面 | 实际所指 | 处置 |
|---|---|---|---|
| `K0-1!V6` | `调节索引（K1-12）` | `K0-4` 函证差异调节表 | 跳转指 K0-4，tooltip 标原值 |
| `K0-1!S32` | `…可靠性的考虑（K0-6）` | `K0-7` 邮件传真回函可靠性验证（`K0-6` 实为其他应付款替代程序） | 同上 |
| `K0-2!AA6` | `跟函函证控制过程（K1-11）` | `K0-3` 跟函函证过程控制 | 同上 |
| `底稿目录!D5:D13` | 序号 `[1,2,3,4,5,7,8,9,10]` | 9 张底稿（序号 6 缺失） | 以索引号为真源，不依赖序号 |
| `K0-5!M46` | `SUM(M40:M45)` 对索引号文本列求和 | 无业务含义 | 不实现，守卫登记 |

## Correctness Properties

### Property 1: 源模板 sheet 结构不变式

守卫以 openpyxl 直读 `K0 管理循环函证.xlsx`，断言 11 张 sheet、`GT_Custom` 为 hidden、其余 10 张 visible 且名称逐字一致；底稿目录 9 行、索引号集合为 `{K0A, K0-1..K0-8}`、序号序列为 `[1,2,3,4,5,7,8,9,10]`。含反向自检：把任一断言基准改一字必须打红。

**Validates: Requirements 1.1, 1.2, 6.3**

### Property 2: K0-1 上区 28 列与 6 段一一映射

`resolveConfirmationColumns('K0')` 的列标签集合（套用 label + group override 后）覆盖源模板 R6 的 **28** 个叶子列且一一映射；除 `confirmation_method`（显式登记的源外保留列，label「函证类型（积极式/消极式）」）外无剩余列；`contact_person`/`contact_phone`/`currency` 已被剔除；`send_channel` 已启用并承载源 `G6 函证方式`；每列的 `group` 与源模板段（`C5:F5`/`G5:K5`/`L5:R5`/`S5:W5`/`X5:AA5`/`AB5`）对应，`row_conclusion` 在 `row_summary` 段。守卫读源 xlsx（或后端导出的 fixture）与 `confirmationColumnSpec.ts` 双源比对。

**Validates: Requirements 1.3, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9**

### Property 3: 伪列撤回且字段保留

`resolveConfirmationColumns('K0')` 与 `('L0')` 均不含 `key === 'send_memo'` 的列，且 `VARIANT_COLUMN_DEFS` 不再声明该列；同时 `ConfirmationRow` 仍声明 `send_memo` 字段，且读回既有非空 `send_memo` 值时 UI 有只读呈现路径。反向自检：把 `send_memo` 加回列集必须打红。

**Validates: Requirements 2.1, 2.2**

### Property 4: 其余循环列集逐字节不变

对 `D0`/`E0`/`F0`/`G0`/`H0` 五个循环，`resolveConfirmationColumns(cycle)` 的 `JSON.stringify` 结果与改造前的黄金快照逐字节相等（快照作为常量冻结在守卫内）。`CYCLE_COLUMN_GROUP_OVERRIDES` 对未声明循环缺省 ⇒ 该断言即为机制正确性的证明。

**Validates: Requirements 2.8, 11.4**

### Property 5: 矩阵 8 指标与源模板公式同构

对给定 grid rows，`buildK0SummaryMatrix` 产出 `2 × 8` 矩阵，且：发函金额 == `Σ rows[account_type==品种].amount`；回函确认 == `Σ …confirmed_amount`；替代确认 == `Σ …alt_confirmed`；三个比例 == 对应商；末行 == `(替代+回函)/账面`。指标标签逐字等于源 `C29:C36`（去尾冒号），锚点常量与源单元格一致。

**Validates: Requirements 1.5, 3.2, 3.3**

### Property 6: 分母缺失不产出 NaN/Infinity 且不用 0 冒充

对任意输入（PBT：金额取金额域含 0/负数，`bookAmounts` 可缺项），`buildK0SummaryMatrix` 的比例单元格 `value` 要么是有限数、要么是 `null`，绝不为 `NaN`/`±Infinity`；`bookAmounts` 缺该品种时比例为 `null` 而非 `0`。

**Validates: Requirements 3.4**

### Property 7: 新建 K0 矩阵对 E0/F0/H0 零回归

`k0SummaryMatrix.ts` **只 import 不修改** `safeRatio`/`sumByCategory`；守卫断言 `f0SummaryAggregation.ts` 与 `e0SummaryMatrix.ts` 与 `h0SummaryMatrix.ts` 三文件的内容哈希在本 spec 改动前后不变，且 `buildF0SummaryMatrix`/`buildE0SummaryMatrix`/`buildH0SummaryMatrix` 对同一批输入的返回值与黄金快照逐字节相等；三侧既有 spec 断言不做任何修改必须全绿。

**Validates: Requirements 11.2, 11.3**

### Property 8: 账面金额取数按 row_code 精确匹配且区分「无科目」与「为 0」

`K0_MATRIX_CATEGORIES` 声明的 `reportRowCode` 为 `BS-009`/`BS-050`；取数缺失时 `bookAmounts` 对应键为 `undefined`（不是 `0`），矩阵账面金额单元格渲染为 `null`；守卫断言配置中不含按 row_name 匹配的路径，且断言 `BS-050`（非 `BS-075`）。

**Validates: Requirements 4.2, 4.3, 4.4, 4.6**

### Property 9: 下区新增键不与既有键冲突且旧 payload 兼容

`k0_matrix_overrides`/`k0_sample_selection`/`k0_audit_notes`/`k0_conclusion` 四键与既有 `rows`/`sampling`/`notes`/`conclusion`/`summary_config` 键集**无交集**；读回不含这四键的旧 payload 时组件正常渲染（全空）；写回空值不产生键。

**Validates: Requirements 3.12, 3.8**

### Property 10: 审计说明 5 项与源模板逐字一致且两格句子合并

`K0_AUDIT_NOTES` 的 5 个 label 逐字等于源 `S28`/`X28`/`S32`/`X32`/`S36`；第 2 项的 `inlineHint` 等于 `X29 + X30` 拼接结果且不以「（）万元」半句结尾；声明 `aliasOf` 的项其目标字段存在于 `NotesData`。

**Validates: Requirements 1.7, 3.7, 3.8, 3.9**

### Property 11: 公式预设 sheet 名存在于源 xlsx

对全部 7 个函证循环，`prefill_formula_mapping.json` 中该循环块的 `sheet` 值必须存在于对应源 xlsx 的**可见** sheet 名集合；K0 块断言为 `函证结果汇总表K0-1`；E0 块的 `审定表E0-1` 为已知预存在缺陷，登记白名单并写明归属 spec（白名单只许变短）。

**Validates: Requirements 5.1, 5.5**

### Property 12: 预设修订脚本幂等且 round-trip 安全

`fix_k0_prefill_presets.py --apply` 执行两次后第二次报告 0 项变更；`--check` 在已修订状态返回 exit 0；脚本在 `json.dumps` 无法逐字复现原文时 exit 非 0（防全文件重排）。校验器不对 `description`/`notes` 做禁词断言（反向自检：把被纠正的反例写入 notes 不应导致 `--apply` 被拒）。

**Validates: Requirements 5.3, 5.4**

### Property 13: 索引号笔误三条显式登记且跳转指向意图目标

`K0_INDEX_TYPO_MAP` 恰含三条，`literal` 逐字等于源模板原值（含 `K1-12`/`K0-6`/`K1-11`），`intended` 分别为 `K0-4`/`K0-7`/`K0-3`；UI 上每条都有 tooltip 呈现原值。反向自检：把 `intended` 改成 `literal` 必须打红。

**Validates: Requirements 6.1, 6.2, 6.4**

### Property 14: K0-5/K0-6 段①对方当事人 label 必须不同

`BLOCK_COLUMN_CONFIGS_K05.block1` 中银行回单组的对方当事人 label 为「付款方」，`K06` 对应为「收款方」，二者**不相等**；守卫以源 xlsx `K0-5!G16`/`K0-6!I16` 交叉比对。反向自检：统一为同一词即打红。

**Validates: Requirements 7.1, 7.6**

### Property 15: K0-5 段①支持性文件三列齐备且笔误未实现

`BLOCK_COLUMN_CONFIGS_K05.block1` 含 `支持性文件1` 组下三列（识别特征/信息1/信息2）；`getSumFieldsK05('block1')` 中不含索引号列（源模板 `M46` 对文本列求和为笔误，不实现）。

**Validates: Requirements 7.2, 7.5**

### Property 16: 源外增强区块登记不变

`SOURCE_EXTRA_MANIFEST` 中 K05/K06 的 `block4` 条目仍在且 `reason` 非空；`splitByDirection` 仅标于 K05/K06 的 `block3`（源模板段③借贷两表），且两个组件确有借方/贷方两个渲染点。

**Validates: Requirements 7.6, 1.13**

### Property 17: K0-2 二次发函六列 additive 且与源模板叶子列一一映射

`EntityVerifyRow` 新增六字段与源 `AF6:AK6` 六个叶子列一一映射；字段变化仅为 additive（对改造前字段名集合取差集，删除项与重命名项均为空）；`is_second_send` 为假时该区域折叠。

**Validates: Requirements 8.1, 8.2, 8.3, 8.5**

### Property 18: K0-7 渠道字段全部有 UI 消费方

`reliabilityTypes.ts` 声明的 12 个按渠道核对字段在 `reliability/**/*.vue` 中**每个都有至少一处引用**；`G:M` 七列有中文父表头「期末未收回原件函证可靠性验证」。反向自检：删除任一字段的渲染点必须打红。

**Validates: Requirements 9.1, 9.2, 9.6**

### Property 19: 跟函通用话术含工号与接待事实核实占位，E0 五段逐字不变

`IMMEDIATE_CONFIRM_TPL` 与 `LATER_FOLLOW_TPL` 均含工号占位；`LATER_FOLLOW_TPL` 含接待事实核实占位；五个 `BANK_*_TPL` 与源 `E0-7` 对应单元格逐字相等（黄金快照冻结）；`getTemplate` 两种旧签名的返回值与改造前一致（除新增占位）。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

### Property 20: 本 spec 新建模块零消费方即打红

对本 spec 新建的每个模块（`k0MatrixSpec.ts` / `k0LowerZoneSpec.ts` / `K0SummaryLowerZone.vue` / `x0SummaryMatrix.ts`），守卫扫描全前端源码断言至少有一个非自身、非 `__tests__`、非 `components.d.ts` 的消费方。

**Validates: Requirements 11.6**

### Property 21: 共享件受影响循环的同步生效声明完整

对每个共享件改动点（列标签覆盖 / 分段覆盖 / 通用话术 / 渠道列 / 二次发函列），守卫要求一份显式声明表列出「同步生效的循环」与「声明不变的循环」，并对后者断言逐字节不变；声明表缺项即打红。

**Validates: Requirements 11.4**

### Property 22: 金额显示走平台单一真源

`K0SummaryLowerZone.vue` 中只读金额一律经 `displayPrefs.fmtAmount()`；守卫断言该组件源码不含 `toLocaleString`，不含 `import { fmtAmount } from '@/stores/displayPrefs'`（该命名导出不存在，会让整页崩），且 `useDisplayPrefsStore()` 调用位于 setup 顶层而非函数体内。

**Validates: Requirements 3.1**

### Property 23: 可编辑金额控件选型正确

矩阵账面金额行的手工录入控件为 `el-input` 或 `WpAmountInput`，**不得**为 `el-input-number :formatter`（EP 2.13.6 无该 prop，千分符不生效）；守卫断言 `K0SummaryLowerZone.vue` 中 `el-input-number` 计数为 0。

**Validates: Requirements 3.5**

### Property 24: 源外保留列显式登记且已在 UI 标注

K0-7 可靠性表里源模板**没有**的列（落地实证四条：`reply_date` / `identity_method` / `phone_source` / `reliability_note`）必须在 `SOURCE_EXTRA_RELIABILITY_COLUMNS` 显式登记且 `reason` 有实质内容（禁「历史遗留」这类无信息量理由）；守卫另断言每条登记的 `field` 真实存在于 `ReliabilityRow`、且四条都在 `ReliabilityGrid.vue` 有 tooltip 标注（登记不能只躺在常量里）。

**落地时对 Requirement 9.3 的修正**：立项写「按循环控制 `reply_date` 可见性（K0 源模板无该列）」，而 openpyxl 实测**六个枢纽（D0-7/F0-7/G0-7/H0-6/K0-7/L0-6）的可靠性表列集逐字同构、全部没有「回函日期」列** ⇒ 按循环分叉只会产出自相矛盾的结果（哪个循环该显示都说不出依据），正确形态是**平台级源外保留列 + 显式登记 + UI 标注**。后端 `test_k0_source_template_facts.py::test_no_reply_date_column` 是该判据的来源，前端交叉锁死到它。

**Validates: Requirements 9.3, 9.5**

### Property 25: 模板引用的标识符均已定义或导入

`ReliabilityGrid.vue` 等被改造的共享组件，其 `<template>` 求值上下文引用的每个标识符都必须能在 `<script setup>` 中解析到（import / const / function / props 解构）。

**为什么单列一条**：`<script setup>` 里**未声明的标识符不阻断编译** —— `get_diagnostics`(Volar) 零诊断 / vitest 全绿 / Vite transform 返回 200，只在浏览器打开该页时抛 `Property "xxx" was accessed during render but is not defined` 并让整页崩成「页面渲染出错」。本 spec 把常量（`RELIABILITY_PARENT_HEADER` / `RELIABILITY_COLUMN_LABELS`）接进模板，正是这类缺陷的高发形态。守卫配反向自检（注入一个未定义常量必须被抓到）。

**Validates: Requirements 9.6, 11.6**

## Error Handling

| 场景 | 策略 | 依据 |
|---|---|---|
| K1/K3 render-config 取不到账面金额 | `bookAmounts` 该键为 `undefined`（**不是 0**），矩阵渲染「-」并在 tooltip 说明「未取到，请手工填写」 | 宁缺勿造；「本项目无此科目」与「余额为 0」必须可区分 |
| 账面金额请求失败（网络/权限） | 静默降级为手填态，把错误记入 `diagnostics.errors` 供排查；SHALL NOT 打断录入 | F0 spec 实测教训：被 `_silent` 吞掉的错误必须有可读落点 |
| `report_config` 查不到 `BS-009`/`BS-050` | 返回 `undefined` 并在溯源面板打告警条；SHALL NOT 回退到硬编码科目码查询 | Requirement 4.5 |
| grid 的 `account_type` 取值不在 `K0_MATRIX_CATEGORIES` 内 | 该行不计入任何品种，并在矩阵下方提示「有 N 行『账户/交易』未归类，不计入函证情况」 | 与 F0 的「待归类」提示同款；不猜归属 |
| 既有 `send_memo` 字段有非空值 | 只读呈现 + 提示改填对应分段列；SHALL NOT 删除数据 | 数据零丢失红线 |
| 旧 payload 无下区四键 | 全部按空渲染，写回时空值不产生键 | Property 9 |
| 预设修订脚本遇到并发改动（round-trip 失败） | exit 非 0 并不写盘，提示重新拉取 | Property 12；防全文件重排覆盖并发会话成果 |
| 共享件改动导致某循环列集变化 | 守卫直接打红（黄金快照比对），不允许「顺手统一用词」 | Property 4/7；零回归支点 |

## Testing Strategy

**判据原则**：本 spec 的守卫一律以 **openpyxl 直读源 xlsx** 或**读对侧源码**为裁决者，不接受「拿脚本常量比自己写的 fixture」这种自证；每个守卫文件必须含**反向自检**（改一字必红），防正则失效导致断言空转。

| 层 | 文件 | 覆盖 |
|---|---|---|
| 后端·源模板事实 | `backend/tests/test_k0_source_template_facts.py` | Property 1（sheet/目录）+ 1.3~1.16 全部结构断言（openpyxl 直读，不连库，可进 CI） |
| 后端·公式预设 | `backend/tests/test_k0_formula_presets.py` | Property 11、12（含 7 循环 sheet 名存在性 + E0 白名单） |
| 前端·列对齐 | `confirmation/__tests__/k0ColumnAlignment.spec.ts` | Property 2、3、4（读源 xlsx 的 JSON 化结构 + 黄金快照） |
| 前端·矩阵 | `confirmation/k0-confirmation/__tests__/k0SummaryMatrix.spec.ts` | Property 5、6（含 PBT）、7（F0/E0/H0 零回归快照）、8 |
| 前端·下区声明 | `confirmation/k0-confirmation/__tests__/k0LowerZoneSpec.spec.ts` | Property 9、10、13 |
| 前端·下区实现 | `confirmation/k0-confirmation/__tests__/k0LowerZone.spec.ts` | Property 22、23 |
| 前端·替代程序 | `confirmation/k0-confirmation/__tests__/k0AlternativeBlocks.spec.ts` | Property 14、15、16、17、18 |
| 前端·共享件 | `confirmation/__tests__/k0SharedComponentBoundary.spec.ts` | Property 17、18、19、20、21、24、25 |
| 前端·渠道字段撤回 | `confirmation/reliability/__tests__/reliabilityChannelFieldsWithdrawal.spec.ts` | Property 18（「不得复活」方向） |

> **落地时的路径修正**：初稿把矩阵守卫写成 `confirmation/__tests__/x0SummaryMatrix.spec.ts`（泛化内核撤回后该文件名不再成立），替代程序守卫写成 `confirmation/__tests__/`；实际两者都在 `confirmation/k0-confirmation/__tests__/` 下（per-cycle 件与其守卫同目录，与 L0 一致）。**下区拆两个文件**：`k0LowerZoneSpec.spec.ts` 守声明真源（四块文字/键名/笔误映射），`k0LowerZone.spec.ts` 守组件实现形态（金额怎么读、怎么录）—— 混在一个文件里会让「改声明」与「改渲染」的红信号混淆。

**PBT 边界**（Property 6）：金额生成器必须收敛到金额域并显式排除 `±Infinity` —— `fc.float({noNaN:true})` 仍会生成无穷值（平台已踩过一次，seed 1139061718）。

**实测（不可省）**：按平台铁律，「挂载无报错」不算实测。K0 实测三件套 =
1. 在真实项目的 K0-1 上录 ≥2 行数据（含两个品种各一行、一行未回函走替代），确认矩阵 8 指标出数、比例正确、未归类提示按预期出现/消失；
2. `postgres` 只读查 `working_paper.parsed_data.html_data['函证结果汇总表K0-1']` 确认下区四键落库且键名符合 Property 9；
3. 测完按实测前快照**逐字复原**测试数据。

另需在浏览器逐个打开 K0 的 9 个 sheet 页签，确认无「页面渲染出错」（`get_diagnostics`/vitest/Vite 200 对 SFC 运行期错误全查不出，平台已有多次先例）。

**回归范围**：`npx vitest run confirmation` 全绿；`backend/tests/test_k0_*.py` 与既有 `test_fraud_risk_presets_source_fidelity.py` / `test_confirmation_meta_override_alignment.py` / `test_render_config_smoke.py` 全绿；F0/E0/G0/D0/H0/L0 的 confirmation 相关 spec **不改任何断言**必须全绿。
