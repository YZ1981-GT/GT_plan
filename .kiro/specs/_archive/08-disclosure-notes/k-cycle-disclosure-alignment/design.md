# Design Document

K 循环披露表 ↔ 附注对齐

## Overview

沿用 K2 已验证的三层真源与四件套做法，按结构相似度分三批铺开：

| 批 | 循环 | 结构特征 |
|---|---|---|
| 1 | K8 K9 K10 K11 K12 K13 | 损益类单表（3 或 4 列），同构，可共用 helper |
| 2 | K3 K4 K5 K7 | 负债/递延类多表（1~7 表），含债券/政府补助子表 |
| 3 | K1 K6 | 最复杂：K1 37 表（含两级表头、阶段表），K6 两级表头 + 处置组动态表 |

真源与裁决顺序（同 K2）：附注模版 JSON 定列结构与行名 → 校验预设定勾稽 → 源 xlsx 定取数来源与方法论文字。

## Architecture

```
源 xlsx（backend/wp_templates/K/*.xlsx，披露 tab 逐格实证）
   ├─ tab 名 ──────────────> X_DISCLOSURE_SHEET_NAME（逐字，含括号半/全角差异）
   └─ 红/蓝字 ─────────────> 组件方法论块 + guidance

note_template_{listed,soe}.json
   ├─ tables[].name ──────> X_*_SUBTABLE
   ├─ headers ────────────> build{X}*Columns（列数/label 同形）
   ├─ rows[].label ───────> X_*_ROWS（固定行）
   └─ section_number ─────> X_NOTE_SECTION（**实测值**，含 listed 三、章截断后缀）

fix_note_k_pl_structure.py --apply（幂等）
   └─> 表名去泄漏 / 删占位行 / 补 columns(flat) + guidance
```

同步链路与 K2 一致：组件 → `build{X}SyncPayload` → `POST /disclosure-notes/sync-from-workpaper` → `disclosure_notes.table_data`。

## Components and Interfaces

### 1. 共享 helper `composables/kPlDisclosureShared.ts`（批 1）

K8~K13 六循环附注结构同构（单表 + 项目列 + 本期/上期发生额 [+ 第 4 列]），抽公共构造避免六份漂移：

```ts
export interface KPlColumnSpec {
  labelHeader: string          // = 模板 headers[0]
  currentLabel: string         // 通常「本期发生额」
  priorLabel: string           // 通常「上期发生额」
  /** 第 4 列（K12/K13 金额列；K10 国企文本列），无则省略 */
  extra?: { key: string; label: string; format: 'amount' | 'text' }
}
export function buildPlColumns(spec: KPlColumnSpec): ColumnDef[]

export interface KPlRow {
  project: string
  currentAmount: number
  priorAmount: number
  /** 第 4 列值（金额或文本） */
  extraValue?: number | string
}
export function buildPlTableRows(rows: readonly KPlRow[], spec: KPlColumnSpec): Array<Record<string, unknown>>
export function buildPlPayload(args: KPlPayloadArgs): KPlSyncPayload
```

`flat` 标在标签列，`合计` 行由 helper 统一补（`is_total: true`，逐列求和；文本型第 4 列合计置 `null`）。

**各循环 map 仍各自 `const` 声明 `X_DISCLOSURE_SHEET_NAME`** —— `gen_note_wp_sync_registry.py` 的 `_SHEET_CONST` 正则锚定 `const/let/var` 声明，re-export 取不到；`disclosureSheetNameRegistry.spec.ts` 亦按文件名扫。

### 2. 每循环 `kXNoteSectionMap.ts`（批 1 共 6 份）

```ts
export const K8_NOTE_SECTION = { listed: '五、64', soe: '八、65' }
export const K8_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',   // 源 xlsx 实测（原为半角，属漂移）
  soe: '附注披露信息（国企）',
}
export const K8_LISTED_SUBTABLE = { main: '销售费用（按费用性质列示）' }
export const K8_SOE_SUBTABLE = { main: '销售费用' }
export const K8_LISTED_ROWS / K8_SOE_ROWS   // 模板固定行（不含合计）
export function buildK8ListedColumns(): Record<string, ColumnDef[]>
export function buildK8SoeColumns(): Record<string, ColumnDef[]>
export function buildK8SyncPayload(variant, wpId, rows, narrativeText): K8SyncPayload
```

章节号/表名/列/行逐字实测值：

| 循环 | listed 章节号 | listed 表名 | soe 章节号 | soe 表名 | 列数 |
|---|---|---|---|---|---|
| K8 | 五、64 | 销售费用（按费用性质列示） | 八、65 | 销售费用 | 3/3 |
| K9 | 五、65 | 管理费用（按费用性质列示） | 八、66 | 管理费用 | 3/3 |
| K10 | 五、68 | 其他收益 | 八、69 | 其他收益 | 3/**4**（末列「是否为政府补助」） |
| K11 | **三、资产减值损失（损** | 资产减值损失（原泄漏名 `项  目`） | 八、74 | 资产减值损失 | 3/3 |
| K12 | **三、营业外收入（注：** | 营业外收入（原泄漏名） | 八、76 | 营业外收入 | **4**/**4** |
| K13 | **三、营业外支出（注：** | 营业外支出（原泄漏名） | 八、77 | 营业外支出 | **4**/**4** |

### 3. 幂等脚本 `backend/scripts/fix/fix_note_k_pl_structure.py`

范式照 `fix_note_k2_structure.py`：`--dry-run` / `--check`、`_aligned_by`、写前 `validate_section`。动作：

1. K11/K12/K13 listed 表名 `项  目` → 科目名
2. 删占位说明行（`可无限量添加行` / `......` / `……`），语义入 `guidance`
3. 13 张表补 `columns`（显式 `flat`）+ `guidance`，删 `_column_groups`

### 4. 组件改造（12 份）

- 载荷调用改为传第 4 列值（K12/K13 `nonRecurringAmount` / K13 `nonRecurring`；K10 soe 政府补助标记）
- 可编辑金额 `el-input-number` → `WpAmountInput`；只读金额 → `fmtAmount`
- K9/K11/K12/K13 补 AI 辅助（prompt ≥20 字 + 「不得虚构」）
- 保留既有审计分析列（变动额/变动率/占比/备注），仅在**载荷层**投影掉

## Data Models

载荷（`{key: list[dict]}` 唯一规范形态）：

```json
{
  "营业外收入": [
    {"label": "捐赠利得", "current_amount": 0, "prior_amount": 0, "non_recurring_amount": 0},
    {"label": "合计", "current_amount": 0, "prior_amount": 0, "non_recurring_amount": 0, "is_total": true}
  ],
  "_note_texts": [{"section": "k12-note", "title": "营业外收入说明", "text": "…"}],
  "_removed_table_keys": ["项  目"]
}
```

`_removed_table_keys` 含各循环的历史泄漏表名（`项  目` 等），清理既有项目残留。

## Correctness Properties

### Property 1: sheet_name 等于源 xlsx tab 名

每循环 `X_DISCLOSURE_SHEET_NAME[variant]` 逐字等于该循环源 xlsx 中含「附注」且含对应变体标识的 tab 名。守卫以 openpyxl 实读，不依赖 registry。

**Validates: Requirements 1.1, 1.2, 1.4**

### Property 2: 章节号存在于模板

`X_NOTE_SECTION[variant]` 能在对应 `note_template_*.json` 的 `section_number` 集合中找到。

**Validates: Requirements 2.1**

### Property 3: 子表名逐字一致

`X_*_SUBTABLE` 每个值都在该章节 `tables[].name` 中。

**Validates: Requirements 2.2**

### Property 4: 列同形

`columns` 列数 = 模板 `headers` 长度；标签列 label = `headers[0]`；每列 label 与 `headers` 同位一致。

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 5: 显式 flat

每张表至少一列 `flat: true`，且同表不得同时出现 `group`。

**Validates: Requirements 3.4, 4.1**

### Property 6: 载荷不含审计分析列

`sub_table_data` 行对象的键集合 ⊆ `columns` 键集合；不含 `变动额` / `变动率` / `占比` / `备注` 对应键。

**Validates: Requirements 3.5**

### Property 7: 无占位说明行与泄漏表名

修订后章节的 `rows[].label` 不含 `可无限量添加行` / `......` / `……`；`tables[].name` 不含泄漏名。

**Validates: Requirements 2.4, 3.6**

### Property 8: 合计行为派生值

末行 `is_total` 且每个金额列 = 各明细行该列之和（容差 0.01 元）；文本型列合计置 `null`。

**Validates: Requirements 3.1**

## Error Handling

- 自动同步失败静默（不打断录入），落库真相以 `_last_sync_at` 为准。
- `WpAmountInput` 非法输入回退上一次有效值且不 emit。
- 幂等脚本写入前自校验，不过则只打印不落盘。
- 模板缺章节/缺表时脚本告警跳过而非抛错（幂等）。

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 契约（前端） | `composables/__tests__/kPlNoteSubtableContract.spec.ts` | 六循环 × 两变体，共享 helper P1~P5 + 列同形 + 合计 + 第 4 列 |
| sheet 名（前端→无法读 xlsx） | 后端 `test_note_k_sheet_names.py` | openpyxl 实读 tab 名 vs `.ts` 常量正则 |
| 结构（后端） | `tests/services/test_note_k_pl_structure.py` | 表名 / 列 / flat / guidance / 无占位行 / `_aligned_by` + 反向自检 |
| 跨循环守卫 | `disclosureColumnsCoverage.spec.ts` | `P1_ROUTE` 登记 |
| CI | `governance-checks.yml::note-k-pl-structure` | `--check` + pytest |
| 实测 | chrome-devtools + postgres 只读 | 每批抽 2 个循环两变体 |

## 风险

| 风险 | 缓解 |
|---|---|
| listed `三、` 章截断章节号看着像 bug，后人可能"修正" | 常量注释写明是模板既有形态 + 契约 P2 锁死 |
| 改模板对既有项目不生效（生成时快照） | 交付说明写明；既有项目经「同步到附注」整表覆盖 |
| 并发会话回退共享文件 | 幂等脚本 + 契约测试；共享文件改动用 `str_replace` |
| 六循环 map 重复导致漂移 | 抽 `kPlDisclosureShared.ts`，sheet 名常量仍各自 `const` 声明（生成脚本正则要求） |
