# Design — J1 披露表 ↔ 附注模板对齐

## Overview

三层收口：**模板结构层**（表名 / columns / guidance / text_sections）、
**载荷层**（合计行、3 段说明、列头投影）、**底稿交互层**（勾稽面板、父行派生、
从 J1-2 带入、可复核性）。

不发明新机制：模板修订沿用 `fix_note_g_cycle_structure.py` 幂等脚本范式，
勾稽面板沿用 H1 的「纯函数引擎 + 紧凑 bar + 折叠明细」范式，
带入沿用 J1-1 的 `normalizeJ1Label` + J1-7 的「精确优先 → 包含匹配 → 未匹配追加」范式。

### 权威源与裁决者

| 序 | 源 | 用途 |
|---|---|---|
| 1 | `backend/wp_templates/J/J1 应付职工薪酬.xlsx` | **运行时权威**（底稿生成时复制）。逐格读出行结构 + Excel 公式（勾稽与行映射真源）。本循环无参考副本，不存在两处不一致风险 |
| 2 | `backend/data/consol_note_sections_{listed,soe}.json` | 第 4 方印证：附注交付物的表名 / 表头 / 行序 |
| 3 | `backend/data/note_template_variant_matrix.json` | 章节号（`应付职工薪酬` → listed 五、40 / soe 八、40） |
| 4 | `backend/data/note_workpaper_sync_registry.json` | sheet 名（`附注披露信息（上市公司）` / `附注披露信息（国有企业）`）——实测已正确，不改 |

`note_check_preset_formulas.json` **无 J1 条目**（`J1*` keys = 0）→ 通常的裁决者缺位，退为源 2。

### 五条裁决

**裁决 1：列头取附注交付口径**（沿用已冻结 Decision 2）。源 xlsx 上市侧写
「上年年末数 / 期末数」，国企侧写「期初余额 / 期末余额」；`consol_note_sections_listed`
五-40-1/2/3 **三张表都是** `项  目 / 期初余额 / 本期增加 / 本期减少 / 期末余额`
→ 附注侧统一，底稿 UI 保留各自源模板列头，同步时由 `j1MovementColumns()` 投影。

**裁决 2：soe 第 3 表名 = `设定提存计划列示`（撤销原 Decision 3 的"允许偏离"）。**
原 spec 记录"模板第三张表 name 重复为「短期薪酬列示」（模板笔误），Sub_Table_Key 改取
text_sections 章节标题「设定提存计划列示」"。这个绕行是错的：前端推
`设定提存计划列示`，模板里没有该表名 → `_source=workpaper` 时投影器只渲染推送的
`sub_table_data`（不与模板 `_tables` 合并），对已同步项目看起来正常，但未同步项目的
seed `_tables` 里是两张同名表（附注 TAB 页签重复 + 按 name 建键互相覆盖），
且契约 P1 必然失败。正解是改模板 —— `consol_note_sections_soe` 五-41-3 的 `title`
就是 `设定提存计划列示`，证明这是致同原本措辞。

**裁决 3：soe 表2 社保「其中」项模板 seed 保持 3 项，不聚合。**
源 xlsx 国企侧是 医疗 / 工伤 / 生育 / 其他（4 项）；附注模板与 consol 是
医疗保险费**及生育保险费** / 工伤保险费 / 其他（3 项）。这是**行**差异而非列差异，
且 `_source=workpaper` 时底稿推送是唯一权威 → 底稿推 4 行附注就显示 4 行，信息更细且不丢。
不做聚合（会让「生育保险费」在附注不可见，且引入不可逆变换）。此结论写入 `guidance`，
避免下次复盘重复提议。

**裁决 4：三张表是平行勾稽关系，不是父子派生。**
源模板里表1「短期薪酬」行 = `'明细表J1-2 '!J33`，表2 合计 = `SUM(...)`，
表2 各行 = `'明细表J1-2 '!J13` 等 —— **三张表都独立引 J1-2**。
故表1 两行保持可手工编辑（并保留「从审定表/明细表带入」），差异由勾稽面板报出。
反例（不采纳）：把表1 两行做成只读派生 → 用户未编制表2/表3 时汇总表恒 0。

**裁决 5：同表内父行 = Σ 紧邻缩进子行 → 做成派生。**
`B20=SUM(B21:B27)`（社会保险费）、`B41=SUM(B42:B45)`（离职后福利）是同表内父子关系，
且合计行公式显式排除了这些子行 → 父行是纯派生量。通用规则（覆盖两处且对「+ 新增行」自动生效）：
非缩进行若其后紧跟 ≥1 个连续缩进行，则该行三列 = 子行对应列之和。

## Architecture

```
J1TabDisclosureListed.vue / J1TabDisclosureSoe.vue
  │  ├─ 工具栏：同步到附注 / 跳转回附注 / GtIndexChip×3 / GtReviewTrigger
  │  ├─ 表1 汇总（可手工 + 从审定表带入）
  │  ├─ 勾稽面板 J1DisclosureConsistencyPanel（Task 5）
  │  └─ 表2/表3 明细（从 J1-2 带入 / 父行派生 / section 级复核触发器）
  │
  ├── useJ1DisclosureSections（UI 状态 + 防抖落库 + 合计 computed + 两个 pull 编排）
  │      ├── j1DisclosureRowModel（🆕 零依赖 leaf：行模型 + recalc + 合计口径）
  │      ├── j1DisclosureDetailPull（🆕 纯函数：从 J1-2 带入）
  │      │      └── normalizeJ1Label（复用 useJ1Adjudication，不重复实现）
  │      └── j1DisclosureConsistency（Task 3 纯函数：勾稽规则）
  │
  └── j1NoteSectionMap.buildJ1SyncPayload
         ├── withTotalRow（🆕 载荷层统一补合计行，复用 buildDisclosureSubtotal）
         ├── j1MovementColumns（5 列，标签列 flat）
         └── POST /api/projects/{id}/disclosure-notes/sync-from-workpaper
                └── 附注 五、40 / 八、40（3 表 + text_content）
```

**为什么要抽 `j1DisclosureRowModel`**：`j1DisclosureDetailPull` 需要 `recalcDisclosureRow`，
`j1NoteSectionMap` 需要 `buildDisclosureSubtotal`，二者原本都定义在
`useJ1DisclosureSections` 里 → 若让 composable 反过来 import pull 模块就形成循环依赖。
抽成零依赖 leaf 模块并由 composable **re-export**，既消除循环又不动任何既有 import。

## Components and Interfaces

### 1. `backend/scripts/fix/fix_note_j1_employee_comp_structure.py`（新建）

沿用 `fix_note_g_cycle_structure.py`：`--dry-run` / `--check` / `--variant`、
`_aligned_by` 标记、按 `aliases` 游标匹配（容忍已改名 → 幂等）。
新增 `apply_text_sections()`（说明段是有序整体，整体替换而非逐条 diff）。

| variant | 章节 | 动作 |
|---|---|---|
| listed | 五、40 | 3 表补 `columns`+`guidance`；表2 删 `……` 行（14→13）；`text_sections` 4→11 段 |
| soe | 八、40 | 表3 改名；3 表补 `columns`+`guidance`；`text_sections` 3→7 段 |

`guidance` 内容只取：源 xlsx 红字 / CAS 9 条款 / 以「勾稽：」前缀标注的已实证公式关系。

### 2. `j1DisclosureRowModel.ts`（新建，零依赖 leaf）

```ts
export interface J1DisclosureRow { id; label; category; indent?; beginBalance; increase; decrease; endBalance; isSubtotal? }
export function recalcDisclosureRow(row): J1DisclosureRow        // 期末 = 期初 + 增 − 减
export function buildDisclosureSubtotal(id, label, category, rows): J1DisclosureRow  // 只累加非缩进行
```

### 3. `j1DisclosureDetailPull.ts`（新建，纯函数）

```ts
export function applyDetailPullToDisclosureRows(
  rows: J1DisclosureRow[],
  detail: readonly J1DetailPullRow[],
  options?: { absorb?: Record<string, readonly string[]> },
): { matched: number; appended: number; skippedSubItems: string[] }

export const J1_SOE_SHORT_TERM_ABSORB = { 其他短期薪酬: ['非货币性福利'] }
export const MIN_CONTAIN_LEN = 3
```

匹配策略（每条都对应源模板公式）：

| 披露行 | 源公式 | 策略 |
|---|---|---|
| 工资、奖金、津贴和补贴 | `A18=J1-2!J13`（父行） | 精确匹配；其下「其中：」子项不重复带入 |
| 工伤 / 生育保险费 | `=J1-2!J23` / `J24` | 精确匹配 |
| 其中：医疗保险费 | `A21=J21+J22` | 包含聚合（披露名 ⊂ 明细名：基本/补充医疗保险费） |
| 工会经费和职工教育经费 | `A29=J26+J27` | 包含聚合（明细名 ⊂ 披露名） |
| 其他短期薪酬（**仅国企**） | `B28=J30+J31` | `absorb` 显式别名 |

三条防错约束：

1. **两趟匹配**（先全表精确，再包含聚合）→ 消除行序依赖
2. **包含匹配最短 3 字** → 「其他」（2 字）只走精确 + 队列配对
3. **未匹配「其中：」子项跳过**（金额已含在父行，追加会双算）；只有未匹配且非零的
   **顶层**行才追加

### 4. `j1NoteSectionMap.ts`（改造）

```ts
export const J1_NOTE_TOTAL_LABEL = '合计'   // 附注模板字面，无空格
function withTotalRow(rows, id): J1DisclosureRow[]   // 剔除已有 subtotal 后重算并追加
function mapDisclosureRows(rows, totalId): J1SyncRow[]
```

### 5. `j1DisclosureConsistency.ts`（Task 3，纯函数）

```ts
export interface J1CheckResult { label; rule; left; right; diff; level: 'ok'|'error'; detail?; refs? }
export function buildJ1ConsistencyChecks(input: {
  variant; summary; shortTerm; postEmployment; adjudicationEndTotal?
}): J1CheckResult[]
```

6 类规则（全部有源模板证据）：表1↔表2 合计 / 表1↔表3 合计 / 表1 合计自洽 /
表2·表3 合计排除其中项 / 逐行期末公式 / 表1 合计期末 = J1-1 期末审定合计。

### 6. `J1DisclosureConsistencyPanel.vue`（Task 5）

紧凑单行 bar（`N 项勾稽 · M 项不平`）+ 折叠明细表（规则 / 左值 / 右值 / 差异 / tooltip）。
13px，无 `border stripe`。

## Data Models

### 披露表持久化（`checklist_responses.remark`，JSON）

| item_id | 内容 |
|---|---|
| `J1-disc-{variant}-summary` | 表1 数据行（**不含**合计行，合计为 computed） |
| `J1-disc-{variant}-short-term` | 表2 数据行 |
| `J1-disc-{variant}-post-employment` | 表3 数据行 |
| `J1-disc-{variant}-notes` | `{ key: text }`（listed 3 段 / soe 由 1 段扩为 3 段） |

### J1-2 明细表读入（只读，跨表键）

`J1-2-detail-{shortTerm|postEmployment|severance}` → 行含
`label / isSubItem / indent / unadjBegin / openingAdj / unadjIncrease / ajeIncrease /
unadjDecrease / ajeDecrease`。**审定口径 = 未审 + 调整**。

### 同步载荷

```
{
  wp_id, year, sheet_name, section_id, current_standard,
  sub_table_data: {
    <表1名>: [ ...数据行, { label: '合计', is_total: true } ],
    <表2名>: [ ... ], <表3名>: [ ... ],
    _note_texts: [ { section, title, text } ]
  },
  columns: { <三个表名>: ColumnDef[5] }
}
```

行形态 `{ label, values: [期初, 增加, 减少, 期末], is_total? }`；空值走 `nullableAmount → null`
（0 保留为 0）。

### 附注模板节点（修订后）

6 张表各：`name` / `headers[5]` / `columns[5]`（标签列 `is_label`+`flat`，
4 金额列 `format: amount`）/ `rows`（末行 `is_total`）/ `guidance`；无 `_column_groups`。

## Correctness Properties

### Property 1: 子表名逐字存在且唯一

推送的三个子表名必须逐字出现在对应 variant 的模板章节 `tables[].name` 中，且互不重复。
不满足即产生孤儿子表（附注 TAB 永空 + 底稿数据丢失）。
守卫：`j1NoteSubtableContract.spec.ts`（共享 helper）+ 后端结构测试。

**Validates: Requirements 1.1, 9.2**

### Property 2: 每张表表头声明三态明确

每张表的 `columns` 必须在 `flat`（单级）与 `group`（多级）之间明确表态，不得都无、不得并存。
J1 三张表均为单级 → 全部标 `flat`；未表态会被 `_infer_groups_from_headers` 按
「本期增加/本期减少」前缀反猜出凭空的「本期」父表头。
守卫：`j1NoteSubtableContract.spec.ts` + `test_note_j1_employee_comp_structure.py`。

**Validates: Requirements 1.2, 1.5**

### Property 3: 载荷三张表末行必为合计行且字面一致

`buildJ1SyncPayload` 输出的每张表末行 `is_total === true`，且 `label` 等于
`J1_NOTE_TOTAL_LABEL`（`合计`，无空格）—— 与模板 `rows` 里 `is_total` 行的字面一致。
守卫：`j1NoteSyncPayload.spec.ts`。

**Validates: Requirements 6.2**

### Property 4: 合计只累加非缩进行

合计行各列 = 该表全部**非缩进**数据行对应列之和（源模板合计公式显式排除「其中：」明细行）。
守卫：`j1NoteSyncPayload.spec.ts`。

**Validates: Requirements 6.3**

### Property 5: 补合计行幂等

对已含 `isSubtotal` 行的输入再次调用 `withTotalRow`，结果仍只有 1 个合计行且数值不变。
守卫：`j1NoteSyncPayload.spec.ts`。

**Validates: Requirements 6.3**

### Property 6: 带入结果与披露行顺序无关

`applyDetailPullToDisclosureRows` 对同一明细输入，披露行正序与倒序排列时各行结果相同
（由"先全表精确、再包含聚合"的两趟匹配保证）。
守卫：`j1DisclosureDetailPull.spec.ts`。

**Validates: Requirements 7.6**

### Property 7: 「其中：」子项不双算

已匹配父行的金额取明细父行值，不叠加其子项；未匹配的明细「其中：」子项被跳过而非追加。
守卫：`j1DisclosureDetailPull.spec.ts`。

**Validates: Requirements 7.5**

### Property 8: absorb 别名必需性（反向自检）

不传 `J1_SOE_SHORT_TERM_ABSORB` 时，国企骨架下「非货币性福利」必被追加为多余行
—— 用反向断言证明该别名不是可省的装饰。
守卫：`j1DisclosureDetailPull.spec.ts`。

**Validates: Requirements 7.2, 9.3**

### Property 9: 模板行无假数据

修订后 6 张表的 `rows` 不含 `……` 占位行、不含空 `label` 行、不含 `row_type: header_label`
的压扁表头残留。
守卫：`test_note_j1_employee_comp_structure.py` + 脚本 `--check`。

**Validates: Requirements 1.4**

### Property 10: 前端常量与模板无双真源漂移

`J1_SUB_TABLE_KEYS` 的表名、`j1MovementColumns()` 的 5 个 label 与模板
`tables[].name` / `headers` 逐字一致（后端测试直接读 `.ts` 源码断言）。
守卫：`test_note_j1_employee_comp_structure.py`。

**Validates: Requirements 6.4**

## Error Handling

| 情形 | 处理 |
|---|---|
| J1-2 明细未编制（读到空数组） | `pullDetailSections` 返回全 0，UI 提示"未取到 J1-2 明细表数据，请先编制明细表"，不改动任何行 |
| 部分披露行未匹配 | 保持原值（不清零手工录入），UI 如实报"命中 N 行 / 追加 M 行 / K 个子项未匹配" |
| 明细金额非数值 / 缺字段 | `num()` 归 0，绝不产生 `NaN` 写入（`nullableAmount` 亦拒绝 NaN/Infinity） |
| 模板缺章节 | 修订脚本 `[FATAL]` 退出且不写文件；契约 P2 报红 |
| 修订后结构校验失败 | 脚本**不写文件**并打印全部错误（避免半修订落盘） |
| 表名迁移目标已被占用 | 打 `[WARN]` 跳过改名，不覆盖既有表 |
| 同步接口失败 | 组件 `ElMessage.error` 并保留本地数据；自动同步失败不写 synced 基线 |
| AI 服务不可用 | `aiGenerate` 静默失败（不阻断编制） |

## Testing Strategy

| 层 | 测试 | 现状 |
|---|---|---|
| 模板结构（后端） | `backend/tests/services/test_note_j1_employee_comp_structure.py` | 30 passed |
| 模板幂等（脚本） | `fix_note_j1_employee_comp_structure.py --check` + CI job `note-j1-structure` | 通过 |
| 子表契约（前端） | `j1NoteSubtableContract.spec.ts`（共享 helper 5 Property） | 22 passed |
| 载荷合计行 | `j1NoteSyncPayload.spec.ts` | 15 passed |
| 列定义契约 | `j1h4DisclosureColumns.spec.ts`（既有） | 13 passed |
| 明细带入纯函数 | `j1DisclosureDetailPull.spec.ts`（含反向断言） | 23 passed |
| 勾稽引擎 | `j1DisclosureConsistency.spec.ts` | Task 3.2 待做 |
| 父行派生 | `useJ1DisclosureSections.spec.ts` 扩充 | Task 4.3 待做 |
| 崩溃类 | `curl http://localhost:3030/src/.../X.vue` 看 200（Volar 查不出 SFC 结构损坏） | 6 文件全 200 |
| 活体 | Playwright / chrome-devtools + postgres 只读验 `_last_sync_at` + 字段值 | Task 10.1 待做 |

**上市侧无法活测**：8 个在册项目 `applicable_standard_v2.entity_type` 全为 `soe`，
唯一 listed 适用项目已软删 → 上市侧只能靠契约测试 + 纯函数单测覆盖，交付说明须写明。

## 风险

| 风险 | 缓解 |
|---|---|
| 并发会话回退模板 JSON | 幂等脚本 + `--check` + CI job；测试红了先重跑脚本 |
| 改模板对既有项目不生效（`_tables` 是生成时快照） | 交付说明写清「新建项目 / 重新生成附注才可见」；既有项目靠底稿「同步到附注」整表覆盖 |
| 父行派生吞掉历史手工值 | 只对**存在缩进子行**的父行生效；无子行时行为不变 |
| 带入把交付物骨架冲掉 | 按标签匹配填充而非重建行；未匹配行保持原值；未匹配顶层项追加而非替换 |
| 抽 leaf 模块打断既有 import | composable re-export 全部符号，`get_diagnostics` 逐个消费方复查 |
