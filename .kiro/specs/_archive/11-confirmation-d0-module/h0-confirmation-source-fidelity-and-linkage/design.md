# Design Document: H0 函证源模板保真度与联动补齐

## Overview

本设计把 H0 的修复拆成**四条互不耦合的改造线**，每条都以「零回归支点 + 单一真源 + 守卫反向自检」三件套落地：

1. **枚举线**（R1/R7）：后端 `system_dicts` additive 追加 → 前端 `CONFIRMATION_DICTS` 单一真源 → 三处硬编码字面量（`GtConfirmationSummary.dictData` / `GtConfirmationDiffReconcile.subjectOptions` / 内置回退）改为引用。零回归支点 = 追加不改既有取值。
2. **下区线**（R2/R3）：新增 `h0SummaryLowerZone.ts`（固定文字单一真源，对齐 `e0SummaryLowerZone.ts`）+ `h0SummaryMatrix.ts`（动态品种列矩阵，复用 `f0SummaryAggregation` 的 `safeRatio`/`sumByCategory` 纯函数）+ `H0SummaryLowerZone.vue` + 后端加法式注入 `_inject_h0_book_amounts`。零回归支点 = `GtConfirmationSummary.vue` 里 `v-if="isH0"` 门控，其余六枢纽模板不变。
3. **列集线**（R5/R6）：`confirmationColumnSpec` 新增 `CYCLE_COLUMN_LABEL_OVERRIDES` + 填充 `CYCLE_EXCLUDED_COLUMNS.H0` + `CYCLE_VARIANT_COLUMNS.H0` 加 `row_conclusion`；新增 `h0SummaryFromEntityVerify.ts` 带入映射。零回归支点 = override 表只有 `H0` 一个 key，其余循环 `resolveConfirmationColumns` 输出逐字节不变。
4. **补列/话术/stub 线**（R4/R8/R9/R10）：`entityVerifyTypes` additive 补 8 字段；`memoTemplates` 通用话术补陪同/工号/回访段；四个 stub 用既有 `navigateToCycleSheet` 实装。

**明确不做**（写进 Notes 防下个会话重启）：
- 其余六枢纽的枚举绑定改造（R7.8 —— 六枢纽 DV 虽同构，但改绑定会波及各自既有断言，另立 spec）
- 删除 H0-5 既有四区块（R4.7 —— 只标注 + 补源模板缺段，不销毁存量数据）
- 把 `confirmation-summary` 注册进 `RENDERER_DISPATCH`（R3.5 —— 会劫持七枢纽）
- H0A 程序表编号补 4（源模板事实，`函证程序表H0A` 的 A7~A17 就是 1,2,3,5…12）

## Architecture

```
┌─ 后端 ──────────────────────────────────────────────────────────────┐
│ system_dicts.py                                                     │
│   confirmation_account_type   +9 项 H 类科目           (R1.2)        │
│   confirmation_send_channel   新增 4 项（邮寄/跟函/电子函证/其他）  │
│   confirmation_sample_purpose 新增 5 项（A. 大额/…/E.随机）         │
│   confirmation_addr_verify    新增 6 项（发票合同/电话/官网/…）     │
│   confirmation_reply_method   +3 项（纸质原件/电子函证/其他介质）    │
│   confirmation_subject        +9 项 H 类科目           (R1.4)        │
│                                                                      │
│ services/four_table/h0_book_amounts.py            【新建】          │
│   H0_MATRIX_CATEGORY_SPECS: dict[品种, H{n}SemanticSpec]             │
│   resolve_h0_book_amounts(ctx) -> {品种: amount|None} + source_codes │
│      └─ 复用 semantic_account_resolver + h{n}_account_scope          │
│         + leaf_aggregation.select_leaves/aggregate_leaves            │
│                                                                      │
│ wp_render_config_helpers.py                                          │
│   _inject_h0_book_amounts(db, pid, year, wp_code, html_data)【新建】 │
│      └─ 仅 wp_code 前缀 H0 生效；写 project_context.h0_book_amounts │
│         + project_context.h0_book_source_codes                       │
│ wp_render_config.py L883 附近：confirmation-summary 注入点追加调用   │
│                                                                      │
│ scripts/fix/fix_h0_prefill_presets.py             【新建】(R11)      │
└──────────────────────────────────────────────────────────────────────┘
                              │ render-config
                              ▼
┌─ 前端 ──────────────────────────────────────────────────────────────┐
│ confirmation/                                                        │
│   coordination/confirmationDicts.ts                                  │
│     CONFIRMATION_DICTS +4 key；H0_DICT_KEYS 新增        (R1.3)       │
│     CONFIRMATION_DICT_FALLBACK 新增（组件内置回退单一真源）          │
│                                                                      │
│   h0SummaryLowerZone.ts        【新建】固定文字真源      (R2.6~2.10) │
│   h0SummaryMatrix.ts           【新建】动态品种矩阵      (R2.2~2.5)  │
│     ├─ H0_MATRIX_METRIC_LABELS  (8 条，逐字 R30~R37)                │
│     ├─ H0_MATRIX_DEFAULT_CATEGORIES (3 条，逐字 E29/F29/G29)        │
│     ├─ buildH0SummaryMatrix({rows, categories, bookAmounts, ...})   │
│     └─ 复用 f0SummaryAggregation.{safeRatio, sumByCategory}         │
│   H0SummaryLowerZone.vue       【新建】四块渲染                      │
│   h0SummaryFromEntityVerify.ts 【新建】7 列带入映射       (R5)       │
│                                                                      │
│   confirmationColumnSpec.ts                                          │
│     CYCLE_COLUMN_LABEL_OVERRIDES 新增（只有 H0 一个 key）(R6.4~6.5) │
│     CYCLE_EXCLUDED_COLUMNS.H0 填 3 项                    (R6.2)     │
│     CYCLE_VARIANT_COLUMNS.H0 加 row_conclusion           (R6.1)     │
│                                                                      │
│   GtConfirmationSummary.vue                                          │
│     isH0 分支 + <H0SummaryLowerZone> + 「从 H0-2 带入」按钮          │
│     dictData 改引用 CONFIRMATION_DICT_FALLBACK                       │
│                                                                      │
│   entityVerify/entityVerifyTypes.ts  +8 optional 字段     (R8)      │
│   entityVerify/EntityVerifyDashboard.vue 第二次发函列组渲染          │
│   followup/memoTemplates.ts  通用话术补陪同/工号/回访段   (R9)      │
│   alternativeH05/  样本选取6字段 + 检查过程记录 + 增强标注 (R4)     │
│   reliability/GtConfirmationReliability.vue  handleJumpD01 实装      │
│   diffReconcile/GtConfirmationDiffReconcile.vue jump+delete 实装     │
│   fraudRisk/GtConfirmationFraudRisk.vue      handleJumpRef 实装      │
└──────────────────────────────────────────────────────────────────────┘
```

### 三个关键架构判断

**判断 1：账面金额走加法式注入，不走 RENDERER_DISPATCH。**
`confirmation-summary` 是七枢纽共享 componentType，注册进 `RENDERER_DISPATCH` 会让 D0/E0/F0/G0/K0/L0 的载荷全部改道。平台已有现成通道：`wp_render_config.py` L883 对 `confirmation-summary` 调 `_inject_confirmation_population` 追加 `project_context.population_amount`。H0 账面金额沿用同一通道，判定条件加 `wp_code` 前缀门控。

**判断 2：账面金额取数复用 H 循环语义定位，不新造。**
实测 `_h1_fixed_assets.py ~ _h10_*.py` 十个策略 **`tb_amount` 零命中**，H 循环下发的是 `tb_values`（按 prefix 键，如 `..._unadjusted`/`..._audited`）+ `tb_source_codes`。若照抄 F0 的 `F0_BOOK_AMOUNT_SOURCES` 读 `project_context.tb_amount` → 恒 `undefined`。故 H0 自己在后端按品种解析：品种 → `H{n}_ACCOUNT_SPEC`（`four_table/h{n}_account_scope.py`，h-cycle spec 已建）→ `semantic_account_resolver` → `select_leaves`/`aggregate_leaves`。这也顺带满足 R3.3（H8 客户用 `1651/1652`、H9 用 `2651`）。

**判断 3：矩阵品种列做动态列，key 用 `{slot}_{seq}` 不用 label。**
源模板 `H29='……'` 是可扩位；且 H0A/H0-1/H0-4/H0-5 标题都写「固定资产/工程物资/使用权资产/租赁负债/……」而矩阵只有 3 列（**源模板自身的遗漏，登记不修**）。按平台铁律「横向展开的表禁写死列数」+「key 不能用 label 会撞键」，默认 seed 3 列（逐字 E29/F29/G29），其余品种由用户从 R1.1 枚举增列。

## Components and Interfaces

### 后端：`services/four_table/h0_book_amounts.py`（新建）

```python
@dataclass(frozen=True)
class H0CategorySpec:
    """H0-1 矩阵一个品种 → H 循环语义规格的映射。"""
    category: str                 # 品种名（= confirmation_account_type 标签，逐字）
    source_wp_code: str           # 'H1'..'H9'
    spec: SemanticAccountSpec     # 复用 h{n}_account_scope 的已有 spec
    gross_slot: str               # 取哪个槽作账面金额（原值/净值口径）
    net_of_slots: tuple[str, ...] # 需扣减的槽（累计折旧/减值等），空 tuple = 不扣
    source_ref: str               # 源模板锚点或 report_config 行号，供溯源

H0_MATRIX_CATEGORY_SPECS: tuple[H0CategorySpec, ...]

async def resolve_h0_book_amounts(
    ctx: ResolverContext,
    categories: Sequence[str] | None = None,
) -> H0BookAmountResult:
    """按品种解析账面金额。

    - 品种不在 H0_MATRIX_CATEGORY_SPECS → 不产出该键（调用方渲染「-」）
    - 槽 found=False（本项目无此科目）→ 该品种 amount=None（**不返 0**，R3.8）
    - 任一步异常 → 该品种 amount=None + warning，不影响其他品种
    """

@dataclass(frozen=True)
class H0BookAmountResult:
    amounts: dict[str, float | None]
    source_codes: dict[str, dict]   # 品种 → {row_code, gross, resolved_from, ...}
    conflicts: list[str]            # report_config 与科目表不一致的告警
```

### 后端：`_inject_h0_book_amounts`（wp_render_config_helpers）

```python
async def _inject_h0_book_amounts(
    db: AsyncSession, project_id, year, wp_code: str | None, sheet_html_data: dict,
) -> None:
    """向 H0-1 的 confirmation-summary htmlData 加法式注入账面金额。

    - wp_code 前缀非 H0 → 直接 return（其余六枢纽载荷逐字节不变，R3.6）
    - 写 project_context.h0_book_amounts / h0_book_source_codes
    - 不改 rows/_format/其它字段
    """
```

### 前端：`h0SummaryMatrix.ts`（新建）

```ts
/** 8 指标标签（逐字源模板 R30~R37；与 F0_MATRIX_LABELS 内容相同但各自声明，防一侧改动波及另一侧） */
export const H0_MATRIX_METRIC_LABELS: readonly string[]

/** 默认品种列（逐字源模板 E29/F29/G29；H29='……' 是可扩位不 seed） */
export const H0_MATRIX_DEFAULT_CATEGORIES: readonly string[]

export interface H0MatrixCategory {
  /** 稳定 key，形态 `cat_{seq}`，改名不变（R2.5） */
  key: string
  /** 品种名，须 ∈ confirmation_account_type 枚举（R1.5） */
  label: string
}

export interface H0MatrixCell {
  categoryKey: string
  metric: string
  value: number | null      // null → 渲染「-」（R2.4）
  kind: 'amount' | 'ratio'
  editable: boolean         // 仅「本期（期末）账面金额」行为 true
  /** 'auto' = 后端取数 / 'manual' = 手工覆盖 / 'derived' = 公式派生 / 'absent' = 本项目无此科目 */
  origin: 'auto' | 'manual' | 'derived' | 'absent'
  sourceHint?: string
}

export function buildH0SummaryMatrix(input: {
  rows: readonly ConfirmationRow[]
  categories: readonly H0MatrixCategory[]
  bookAmounts?: Record<string, number | null>
  manualOverrides?: Record<string, number>
}): H0MatrixCell[][]

/** 手工覆盖持久化 itemId，形态 `H0-1-matrix-{categoryKey}-{metricIdx}` */
export function h0MatrixOverrideItemId(categoryKey: string, metricIdx: number): string

/** 品种列持久化 itemId（列定义本身要落库，否则改名/增列刷新即丢） */
export const H0_MATRIX_CATEGORIES_KEY = 'H0-1-matrix-categories'
```

### 前端：`h0SummaryLowerZone.ts`（新建）

对齐 `e0SummaryLowerZone.ts` 结构：

```ts
export interface H0LowerZoneText {
  block: 'sample_selection' | 'audit_note' | 'conclusion' | 'guidance'
  key: string
  text: string          // 逐字源模板；跨格拆句的已合并（R2.7）
  anchor: string        // 源模板锚点，多格合并用 '+' 连接
  readonly: boolean     // true = 只读方法论上下文
}

export const H0_LOWER_ZONE_TEXTS: readonly H0LowerZoneText[]

/**
 * 四块锚点与标题。
 * 🔴 源模板 S28 的编号是「二、审计说明」（笔误，应为「三」）——
 *    title 用修正后的「三、审计说明」，sourceText 保留原文供守卫按原文断言（R2.8）
 */
export const H0_LOWER_ZONE_BLOCKS = {
  matrix:           { anchor: 'C28', title: '一、函证情况' },
  sample_selection: { anchor: 'J28', title: '二、样本选择' },
  audit_note:       { anchor: 'S28', title: '三、审计说明', sourceText: '二、审计说明' },
  conclusion:       { anchor: 'C39', title: '四、审计结论' },
} as const

/** 6 个样本选择字段（标签逐字 J29/J30/J31/J32/J34/J35） */
export const H0_SAMPLE_SELECTION_FIELDS: readonly { key: string; label: string; anchor: string; placeholder: string }[]

/** 5 个审计说明小节（标题逐字 S29/W29/S33/S34/S37） */
export const H0_AUDIT_NOTE_SECTIONS: readonly { key: string; title: string; anchor: string }[]

/** 参考结论 A/B/C（逐字 A66:B68），只读方法论上下文（R2.9） */
export const H0_REFERENCE_CONCLUSIONS: readonly { code: string; text: string }[]

export const H0_SAMPLE_KEY_PREFIX = 'H0-1-lower-sample-'
export const H0_AUDIT_NOTE_KEY_PREFIX = 'H0-1-lower-audit-note-'
export const H0_CONCLUSION_KEY = 'H0-1-lower-conclusion'
```

### 前端：`h0SummaryFromEntityVerify.ts`（新建，R5）

```ts
/**
 * H0-1 ← H0-2 带入映射（声明式）。
 * 每条的 sourceColumnIndex 是源模板 VLOOKUP 的第三参（col_index_num），
 * 由守卫与 xlsx 公式交叉锁死（R5.6）。
 */
export interface H0PullFieldSpec {
  targetKey: keyof ConfirmationRow   // H0-1 列 key
  targetColumn: string               // 源模板列字母，如 'D'
  sourceField: keyof EntityVerifyRow // H0-2 字段
  sourceColumnIndex: number          // VLOOKUP col_index_num：2/3/4/10/16/19/22
}

export const H0_PULL_FROM_ENTITY_VERIFY: readonly H0PullFieldSpec[]

export interface H0PullResult {
  matched: number
  skippedNoIndex: number
  unmatchedIndexes: string[]
  updatedRowIds: string[]
}

/** 纯函数：手工优先 / 幂等 / mode 二选一（R5.3~5.5） */
export function pullH0SummaryFromEntityVerify(input: {
  summaryRows: ConfirmationRow[]
  entityRows: readonly EntityVerifyRow[]
  mode: 'fill_blank' | 'overwrite'
}): H0PullResult
```

### 前端：`confirmationColumnSpec.ts` 扩展（R6）

```ts
/**
 * per-cycle label 覆盖（各枢纽源模板用词不同不强行统一，Requirement 8.3）。
 * 🔴 SHALL NOT 改 BASE_CONFIRMATION_COLUMNS 的 label —— 那会波及其余六枢纽。
 * 只有 H0 一个 key ⇒ 其余循环 resolveConfirmationColumns 输出逐字节不变（R6.7）。
 */
export const CYCLE_COLUMN_LABEL_OVERRIDES: Partial<Record<ConfirmCycle, Record<string, string>>> = {
  H0: { /* 12 处，见 requirements R6.4 表 */ },
}
```

`resolveConfirmationColumns` 末尾对命中 override 的列做 `{...col, label: override}` 浅拷贝（**不 mutate BASE 常量对象**，否则第一次调用即污染全局）。

## Data Models

### `project_context.h0_book_amounts`（render-config 注入）

```jsonc
{
  "project_context": {
    "h0_book_amounts": {
      "固定资产": 12345678.90,
      "工程物资": null,            // 本项目无此科目（R3.8）
      "租赁负债": 987654.32
    },
    "h0_book_source_codes": {
      "固定资产": {
        "row_code": "BS-028",
        "gross": ["1601"], "gross_standard": ["1601"],
        "net_of": ["1602", "1603"],
        "resolved_from": "account_chart_client",
        "found": true
      },
      "工程物资": { "row_code": null, "gross": [], "resolved_from": "none", "found": false }
    }
  }
}
```

### `checklist_responses` 新增键

| itemId | 内容 |
|---|---|
| `H0-1-matrix-categories` | 品种列定义 JSON（`H0MatrixCategory[]`，改名/增删列持久化） |
| `H0-1-matrix-{categoryKey}-0` | 账面金额手工覆盖（仅指标 0 可覆盖） |
| `H0-1-lower-sample-{fieldKey}` | 二、样本选择 6 字段 |
| `H0-1-lower-audit-note-{sectionKey}` | 三、审计说明 5 小节 |
| `H0-1-lower-conclusion` | 四、审计结论 |
| `H0-5-check-record-free` | H0-5「二、检查过程记录」自由记录（R4.5） |
| `H0-5-sample-{fieldKey}` | H0-5 样本选取标准与规模 6 字段（R4.2） |

### `EntityVerifyRow` additive 补 8 字段（R8）

| 字段 | 源模板 | 说明 |
|---|---|---|
| `provided_zipcode` | `E6` 邮编 | 被审计单位提供侧 |
| `provided_email_fax` | `H6` 邮箱/传真 | 被审计单位提供侧 |
| `second_entity_address` | `AF6` 地址 | 第二次发函 |
| `second_entity_zipcode` | `AG6` 邮编 | 第二次发函 |
| `second_contact_person` | `AH6` 联系人 | 第二次发函 |
| `second_contact_phone` | `AI6` 联系电话 | 第二次发函 |
| `second_fax` | `AJ6` 传真 | 第二次发函 |
| `second_info_verified` | `AK6` 信息是否核查一致 | 第二次发函 |

全部 optional；写回时空值不落 `undefined` 键（R8.4）。

## Correctness Properties

### Property 1: H 类品种枚举齐备且三处同源
`confirmation_account_type` 与 `confirmation_subject` 均含 9 项 H 类科目；`GtConfirmationSummary.dictData` 与 `GtConfirmationDiffReconcile.subjectOptions` 源码中不得出现品种字面量数组（须引用 `CONFIRMATION_DICTS` 派生的回退常量）。反向自检：把回退常量改回 7 项字面量，守卫必须打红。
**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 2: 矩阵品种 ⊆ 品种枚举
`H0_MATRIX_DEFAULT_CATEGORIES` 每项与用户新增的品种 label 均须存在于 `confirmation_account_type` 标签集合；否则矩阵 SUMIF 恒空。守卫同时断言 9 项 H 类标签与 `wp_system_map.json` 的 H 循环科目名逐字一致。
**Validates: Requirements 1.5, 1.6, 2.5**

### Property 3: 矩阵 8 指标标签与源模板逐字一致
守卫用 openpyxl 直读 `函证结果汇总表H0-1!C30:C37`，与 `H0_MATRIX_METRIC_LABELS` 逐字比对（去尾冒号后）。反向自检：改任一标签必打红。
**Validates: Requirements 2.2**

### Property 4: 矩阵三个聚合行按源模板 SUMIF 口径
`buildH0SummaryMatrix` 的 R31/R33/R36 分别等于 `Σ rows[品种].amount` / `Σ rows[品种].confirmed_amount` / `Σ rows[品种].alt_confirmed`。守卫用固定 fixture 逐值断言，并断言实现引用的字段名与源模板列（F/U/Y）的对应关系。
**Validates: Requirements 2.3**

### Property 5: 比例行分母缺失返 null 不返 0/NaN
对 `bookAmounts` 缺该品种、为 0、为 null 三种输入，5 个比例行均返回 `null`；任何输入下均不产出 `NaN`/`Infinity`。PBT：随机金额组合下断言 `Number.isFinite(value) || value === null`。
**Validates: Requirements 2.4, 3.8**

### Property 6: 品种列 key 稳定且不用 label
`H0MatrixCategory.key` 匹配 `^cat_\d+$`；对两个同名品种（用户误建重名）建列后 key 不相等。反向自检：把 key 改为取 label，重名场景必撞键打红。
**Validates: Requirements 2.5**

### Property 7: 下区固定文字与源模板逐字一致（含跨格合并与笔误保留）
守卫用 openpyxl 读 H0-1 下区各锚点，与 `H0_LOWER_ZONE_TEXTS` 逐字比对；`W30+W31` 与其它跨格条目须为合并后整句；`H0_LOWER_ZONE_BLOCKS.audit_note.sourceText` 须逐字等于源模板 `S28` 原文「二、审计说明」而 `title` 为「三、审计说明」。
**Validates: Requirements 2.6, 2.7, 2.8, 2.9, 2.10**

### Property 8: 账面金额取数走语义定位且非标准码项目可取到
`resolve_h0_book_amounts` 源码中不得出现 H 类标准科目码字面量作为查询前缀（`1601`/`1641`/`2601` 等只允许出现在 `H0CategorySpec.source_ref` 与注释里）。真实 DB 测试：对客户用 `1651/1652`（使用权资产）与 `2651`（租赁负债）的项目，两品种 `found=True` 且金额非空。
**Validates: Requirements 3.2, 3.3**

### Property 9: 未照抄 F0 的 tb_amount 口径
守卫断言 H0 账面金额实现不读 `project_context.tb_amount`（实测 H1~H10 render 该字段零命中，读它恒 undefined）。反向自检：注入一个读 `tb_amount` 的实现，守卫必打红。
**Validates: Requirements 3.4**

### Property 10: 注入仅对 H0 生效且其余六枢纽逐字节不变
对 D0/E0/F0/G0/K0/L0 的 `confirmation-summary` sheet 调注入前后，`html_data` 深比较逐字节相同；对 H0-1 则新增两个键且 `rows`/`_format` 不变。
**Validates: Requirements 3.5, 3.6**

### Property 11: 注入字段有真实消费方
守卫扫前端源码，断言 `h0_book_amounts` 与 `h0_book_source_codes` 各有 ≥1 处非测试消费点，且消费点在 `buildH0SummaryMatrix` 的入参链上（不是赋值即弃）。反向自检：把消费点入参改为 `undefined`，守卫必打红（对齐语义解析器全量迁移复盘的「死代码判据」）。
**Validates: Requirements 3.7**

### Property 12: H0-5 源模板缺段齐备且源外增强显式标注
守卫断言 H0-5 组件含源模板四段（样本选取 6 字段 / 检查过程记录自由区 / 审计说明 / 审计结论）与 3 条编制说明逐字；四区块渲染处含「平台增强」标注文案；`BLOCK_COLUMN_CONFIGS_H05` 的四个 title 与 `ALTERNATIVE_BLOCK_MANIFEST.H05` 逐字一致。
**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

### Property 13: H0-5 存量数据不丢
对含 `alternative-h05-v1` + 非空 `companies[]` 的历史载荷，改造后读回 `companies` 深比较逐字节相同。
**Validates: Requirements 4.7**

### Property 14: 带入映射与源模板 VLOOKUP 列序交叉锁死
守卫用 openpyxl 读 H0-1 的 `D8/G8/J8/K8/M8/Q8/R8` 七条公式，解析出 `col_index_num`（2/3/4/10/16/19/22），与 `H0_PULL_FROM_ENTITY_VERIFY[].sourceColumnIndex` 逐条比对；并断言 `sourceField` 对应的 H0-2 列字母与该 index 一致。
**Validates: Requirements 5.1, 5.6**

### Property 15: 带入手工优先 / 幂等 / 空索引跳过
`pullH0SummaryFromEntityVerify` 在 `mode='fill_blank'` 下不改已有非空值；连续两次调用结果相同；`confirm_index` 为空/空白的行计入 `skippedNoIndex` 且不被修改；未匹配索引号全部出现在 `unmatchedIndexes`。
**Validates: Requirements 5.2, 5.3, 5.4, 5.5**

### Property 16: H0 列集与 label 对齐源模板且不越界
`resolveConfirmationColumns('H0')` 含 `row_conclusion`；不含 `contact_person`/`contact_phone`/`currency`；12 处 label 与源模板用词逐字一致（守卫用 openpyxl 读 H0-1 表头交叉比对）；每列 key 仍 ⊆ `CONFIRMATION_SOURCE_MANIFEST.H0`。
**Validates: Requirements 6.1, 6.2, 6.4, 6.6**

### Property 17: label override 不 mutate BASE 常量、其余六枢纽零回归
连续调用 `resolveConfirmationColumns('H0')` 后再调 `resolveConfirmationColumns('D0')`，D0 输出的 label 与改造前基线逐字节相同（防浅拷贝写漏导致 BASE 被污染）；六枢纽输出快照全部不变。
**Validates: Requirements 6.5, 6.7, 12.5**

### Property 18: 剔除列不销毁持久化值
对含 `contact_person`/`currency` 非空值的历史 `confirmation-v1` 载荷，改造后读回这些字段值仍在（只是不渲染）。
**Validates: Requirements 6.3**

### Property 19: 四组枚举取值与源模板 DV 逐字一致
守卫用 `coord in dv.sqref` 逐格取 H0-2 `C7`/`L7`/`P7`、H0-1 `C8`、H0-6 `D7` 的 DV `formula1`，拆分后与后端字典标签逐字比对（含 `A. 大额` 的空格与 `B.异常` 的无空格差异，原样保留）。守卫**不得**读 openpyxl 打印的镜像列 sqref。
**Validates: Requirements 7.1, 7.4, 7.5, 7.6**

### Property 20: 渠道另立字段、积极式派生不受影响
H0-1 渲染 `send_channel`（label「函证方式」，绑 `confirmation_send_channel`）与 `confirmation_method`（label「函证类型（积极式/消极式）」，绑 `confirmation_method`）两列；`confirmation_method` 取值仍为 `['积极式','消极式']`；`computeConfirmedAmount` 对「消极式 + 未回函」的分支行为与改造前逐字节相同（反向自检：把 `confirmation_method` 改绑渠道枚举，该派生用例必红）。
**Validates: Requirements 7.2, 7.3**

### Property 21: 枚举改动为 additive
后端字典改动前后，每个既有 key 的既有取值列表为新列表的前缀（只追加不改序不改值）。反向自检：改动任一既有取值必打红。
**Validates: Requirements 7.7, 1.2**

### Property 22: 其余六枢纽枚举绑定未被改动
守卫断言 D0/E0/F0/G0/K0/L0 的组件源码中枚举 key 引用与改造前相同（R7.8 的「本 spec 只接 H0」边界）。
**Validates: Requirements 7.8**

### Property 23: H0-2 补列齐备、optional、条件展开
8 个新字段全为 optional；旧 `entity-verify-v1` 载荷读回后这些键为 `undefined` 且写回不产生 `undefined` 键；第二次发函 6 列在 `is_second_send` 为假时不渲染；两条审计说明逐字取 `C25`/`C26`。
**Validates: Requirements 8.1, 8.2, 8.4, 8.5, 8.6**

### Property 24: H0-3 通用话术含陪同情况、工号、回访段，且 E0 逐字不变
通用模板（`scenariosFor()` 返回的三个场景）文本中含陪同情况占位与工号占位；第三方致电回访段可独立取用；3 个核对点标签逐字取 `A23:A25`；`getTemplate` 在 `cycle='E0'` 下返回的五段银行话术与改造前逐字节相同。
**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6**

### Property 25: 四个 stub 实装且不硬编码 D0 字面量
`handleJumpD01`（reliability / diffReconcile）、`handleJumpRef`（fraudRisk）、`handleDelete`（diffReconcile）四处函数体中不得只有 `console.log`；不得出现 `'D0-1'` 字面量；须调用 `navigateToCycleSheet` 或 `useConfirmationNavigation`。守卫先 `stripComments()` 并断言原始源码含被禁字样（防空转）。`handleJumpB50` 不得被重复实现。
**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.7**

### Property 26: stub 实装对其余六枢纽同样生效
跳转目标按 `getCycleConfirmationMeta(wpCode).summaryCode` 解析；对七个 wpCode 输入分别断言解析出各自的 X0-1。
**Validates: Requirements 10.6**

### Property 27: 公式预设纠偏且只触碰 H0 块
`fix_h0_prefill_presets.py --check` 退出码 0；H0 块 `sheet` 等于 `函证结果汇总表H0-1`（守卫用 openpyxl 断言该 tab 存在、`审定表H0-1` 不存在）；其余 257 块 `json.dumps` 逐字节不变；脚本 round-trip 自检生效。
**Validates: Requirements 11.1, 11.2, 11.4, 11.5, 11.6**

### Property 28: 账面金额无第二真源
若 H0 预设保留取数条目，其解析出的科目集合须等于 `resolve_h0_book_amounts` 对应品种的 `gross`；否则预设须为 `PLACEHOLDER`。
**Validates: Requirements 11.3**

### Property 29: 守卫以源 xlsx 为裁决者且含反向自检
每个源模板保真度守卫文件中须存在 openpyxl 打开 `backend/wp_templates/H/H0 固定资产循环函证.xlsx` 的调用，且含至少一条「复现改造前实现必打红」的反向自检用例。
**Validates: Requirements 12.1, 12.2, 12.3**

### Property 30: 三方枚举交叉锁死
守卫比对「后端 `system_dicts` 标签集合 ↔ 前端 `CONFIRMATION_DICTS` 引用的回退常量 ↔ `H0_MATRIX_DEFAULT_CATEGORIES`」三方，任一方漂移即打红。
**Validates: Requirements 12.4**

## Error Handling

| 失效点 | 处置 | 依据 |
|---|---|---|
| `resolve_h0_book_amounts` 某品种科目解析抛异常 | 该品种 `amount=None` + `logger.warning`，其余品种照常返回 | 单点失败不拖垮整个矩阵 |
| 品种槽 `found=False`（本项目无此科目） | `amount=None`，UI 显示「本项目无此科目」info tag | R3.8 宁缺勿造；`found=False` 与「余额为 0」是两种状态 |
| `_inject_h0_book_amounts` 整体失败 | 捕获后不注入任何键（前端读到 `undefined` → 账面金额行留空可手填） | 与 `_inject_confirmation_population` 同款 fail-open，不阻断 render-config |
| 矩阵比例分母为 0 / 缺失 | 返 `null` 渲染「-」 | R2.4；**绝不用 0 冒充** |
| 品种列 label 被改成枚举外取值 | 保存时校验并提示，不静默接受（否则 SUMIF 恒空） | Property 2 |
| 带入时 `confirm_index` 为空/空白 | 计入 `skippedNoIndex`，该行不修改 | R5.2 |
| 带入时 H0-2 无匹配索引号 | 计入 `unmatchedIndexes` 并在 toast 中列出 | R5.4 |
| `checklist_responses` 批量保存 | 按 `itemId` 去重后提交（同批重复 id 会让**整批被拒**） | 平台铁律；矩阵覆盖 + 品种列定义可能同批写 |
| 幂等脚本 round-trip 失败 | `exit 2`，不写盘 | R11.5；防全文件重排与并发冲突 |
| 守卫读不到源 xlsx | 测试直接 fail（不 skip） | 源模板是唯一裁决者，读不到即无法裁决 |

**注入失败与「本项目无此科目」必须可区分**：注入整体失败 → 键不存在；解析成功但无科目 → 键存在且值为 `null`。前端据此分别渲染「未取数（可手填）」与「本项目无此科目」，不合并成同一提示。

## Testing Strategy

### 后端

| 文件 | 覆盖 | 要点 |
|---|---|---|
| `tests/test_h0_source_template_facts.py` | Property 3/7/14/19/27/29 | openpyxl 直读 H0 xlsx：9 sheet 名与 `sheet_state=visible`、H0-1 28 列表头、下区锚点文字、7 条 VLOOKUP 的 `col_index_num`、五处真实 DV（`coord in dv.sqref` 逐格判定）、`审定表H0-1` 不存在。含反向自检：断言镜像列 sqref 不被采信 |
| `tests/four_table/test_h0_book_amounts.py` | Property 8/9 | 品种 → spec 映射齐备；源码无标准码字面量作查询前缀；`found=False` 返 `None`；异常隔离 |
| `tests/test_h0_book_amount_injection.py` | Property 10/11 | 六枢纽载荷深比较逐字节不变；H0 新增两键且 `rows`/`_format` 不变；wp_code 前缀门控 |
| `tests/test_confirmation_dicts_h0.py` | Property 1/19/21/30 | 9 项 H 类科目在两个字典中齐备；四组新枚举取值与 DV 逐字；既有取值为新列表前缀（additive）；与 `wp_system_map.json` 科目名逐字 |
| `tests/test_h0_prefill_presets.py` | Property 27/28 | `--check` exit 0；H0 块 sheet 名；其余 257 块逐字节不变 |

### 前端

| 文件 | 覆盖 | 要点 |
|---|---|---|
| `h0SummaryMatrix.spec.ts` | Property 4/5/6 | 三个聚合行逐值断言；比例 null 语义；PBT 断言 `Number.isFinite(v) \|\| v === null`；key 形态与重名不撞键（含反向自检：key 取 label 必红） |
| `h0SummaryLowerZone.spec.ts` | Property 7 | 读后端源 xlsx 交叉比对（`fs.readFileSync` 读不了 xlsx → 改为读后端守卫导出的 JSON fixture，或由后端守卫独家裁决、前端只断言常量内部一致性 + 跨格合并条目不含换行拆句） |
| `h0SummaryFromEntityVerify.spec.ts` | Property 15 | 手工优先 / 幂等 / 空索引跳过 / 未匹配回报 |
| `confirmationColumnSpecH0.spec.ts` | Property 16/17/18/22 | H0 列集与 12 处 label；**六枢纽输出快照零回归**；BASE 未被 mutate（先调 H0 再调 D0）；剔除列不销毁值 |
| `h0DictConsumption.spec.ts` | Property 1/2/11/30 | 三处硬编码字面量归零；`h0_book_amounts` 有真实消费点且在 `buildH0SummaryMatrix` 入参链上（反向自检：入参改 `undefined` 必红） |
| `alternativeH05SourceFidelity.spec.ts` | Property 12/13 | 四段齐备 + 3 条编制说明逐字 + 增强标注文案 + 四 title 与 manifest 一致；存量 `companies[]` 深比较 |
| `entityVerifyH0Columns.spec.ts` | Property 23 | 8 字段 optional / 无 `undefined` 键 / 条件展开 |
| `memoTemplatesH0.spec.ts` | Property 24 | 陪同/工号/回访段；E0 五段逐字节不变 |
| `confirmationStubWiring.spec.ts` | Property 25/26 | 四处 stub 非 `console.log`-only；无 `'D0-1'` 字面量；七 wpCode 各自解析出正确 X0-1；`stripComments()` + 反向自检 |

### 实测（不可省，且不接受「挂载无报错」充当验收）

1. **真实 DB 直跑**：对 ≥3 个项目跑 `resolve_h0_book_amounts`，含一个客户用 `1651/1652`（H8）与 `2651`（H9）的项目，逐品种打印 `amount` / `resolved_from` / `found`；断言非标准码项目两品种取到数。
2. **浏览器实测**：登录后打开 H0-1 → 录 ≥2 行明细（不同品种）→ 矩阵三个聚合行出数 + 比例出数 → 增一列品种并改名 → 手工覆盖账面金额 → 「从 H0-2 带入」命中统计 → `postgres` 查 `checklist_responses` 的 7 类新键落库 → **数据完整复原**。
3. **回归**：`resolveConfirmationColumns` 六枢纽快照；`four_table` 后端全量；`confirmation` 前端全量（失败清单与改造前基线逐条比对，新增失败为 0）。
