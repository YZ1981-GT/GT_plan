# Design

## Overview

H7 是 H 循环唯一需要**整体重建**的循环（其余循环只是结构对齐）。四层改动：

1. **模型层**（新建 2 个纯函数文件）：`h7ListedDisclosureModel.ts`（产业 × 类别的动态列 +
   34 行/11 行变动引擎）、`h7SoeDisclosureModel.ts`（4 产业 + 可扩类别行 + 派生）。
2. **映射/载荷层**（新建 2 个文件）：`h7NoteSectionMap.ts`、`h7DisclosureSyncPayload.ts`。
3. **组件层**：两个披露 Tab 由「单行只读 movementRows」重建为真实录入界面
   （动态类别列 / 可扩类别行 / `WpAmountInput` / `fmtAmount` / AI 辅助 / 自动同步）。
4. **模板 + 守卫层**：幂等脚本 `fix_note_h7_biological_assets_structure.py`、
   后端结构守卫、前端契约守卫、CI 两 job。

## Architecture

### 列模型：按产业分组的动态类别列（上市）

源模板合并区实证两级表头：`A9:A10`（项目 rowspan 2）、`B9:C9` 种植业、`D9:E9` 畜牧养殖业、
`F9:G9` 林业、`H9:I9` 水产业、`J9:J10`（合计 rowspan 2）；R10 是 `类别 | ……` × 4。

语义：**每个产业下辖若干由审计师命名的类别列**，`类别` 是第一个槽位的占位表头，
`……` 是「可继续加列」标记。据此：

- `……` 作**列头**必须丢弃（永远收不到数据，与 H1/H8 同款铁律）
- 每产业默认 1 个类别列，叶子 `label` 取源模板字面 **`类别`**（不自造「苹果树」这类内容），
  `group` = 产业名 → 4 组各 span 1；`项目` 与 `合计` 不带 `group`（混合分组，前后端均支持）
- 列 `key` 用**稳定标识** `{industryKey}_{seq}`（`crop_1` / `livestock_1` / `forestry_1` /
  `aquatic_1`），删中间类别不重排 seq → 数据不错位。**不能用 `key: label`**（H1/H8 那样），
  因为四个产业的默认叶子名都叫 `类别` 会撞键。

**两级表不得标 `flat`**（`flat` 会让 `_extract_column_groups` 直接返 `[]`）。

### 行模型：复用 H1/H8 的 MovementCellMap 范式

`h1ListedDisclosureModel` 已有 `MovementCellMap`（`{[rowKey]: {[colKey]: number}}`）+
`rawCell`/`setCell`。H8 已复用其 `cellValue`。H7 表 2 的「本期变动」是**带符号合成**
（加项之和 − 减项之和 + 公允价值变动 + 其他变动），h1 的 `cellValue` 只支持
`sumOf`/`endOf`/`bookOf` → H7 自带一个 `h7CellValue`，多支持一种 `kind: 'delta'`
（`{plus: string[], minus: string[]}`）。存储与取值仍用 h1 的 `rawCell`/`setCell`。

表 1（34 行四层）row kinds：
`section`（一/二/三/四）→ `detail`（可录入）→ `ellipsis`（可录入，参与小计）→
`subtotal`（`sumOf`）→ `calc`（`endOf`：期初+增−减）→ `book`（`bookOf`：原值−折旧−减值）。

表 2（11 行）：`detail` 期初余额 → `delta` 本期变动 → `detail`×7 分项（含 2 个 `ellipsis`）
→ `calc2` 期末余额（期初 + 本期变动）。

### 国企：4 产业 + 可扩类别行

`H7SoeIndustryBlock = { key, label, categories: [{ id, name, begin, increase, decrease }] }`

- 产业行：有类别时金额 = 类别之和（**只读派生**）；无类别时可直接录入（`selfAmounts`）
- `期末账面价值` 恒为派生（`begin + increase − decrease`），不持久化
- 合计行 = 4 产业行之和
- 类别行新增走 `ElMessageBox.prompt` 要求先输入名称（平台交互铁律）
- 类别 `id` 稳定（`crop-1` 递增不复用），删除不影响其余行

### 模板 seed 与推送的关系

`_source=workpaper` 时投影器只渲染推来的 `sub_table_data`，**不与模板 `_tables` 合并**。
故模板 seed 只是「从未同步过的项目看到的骨架」：上市 seed 用 4 个默认类别列（叶子名 `类别`），
国企 seed 用 4 产业 + 每产业 1 个 `其中：1．` 槽位 + 合计（**删掉 4 个 `……` 纯占位行**）。
推送时列/行按实际类别展开。

### 已建立的平台约束（本 spec 必须遵守）

- `sheet_name` 逐字取源 xlsx tab 名 —— H7 国企是 **`附注披露信息（国有企业）`**，
  与 H9/H10 的 `（国企）` 不同，禁套用
- 章节号定位：`sync_from_workpaper` 按 `(project_id, year, note_section)` 精确匹配；
  服务端 `detect_standard_conflict` 会拦跨主体类型推送（409）
- `X_NOTE_SECTION` 的章节号字面量必须**内联**在对象里、对象体内不写注释
  （`gen_note_wp_sync_registry.py` 正则约束）
- `flat` 必须 seed 与推送两处都加（本 spec 只有国企两表是单级）
- `scheduleAutoSync` 挂在保存处理器，**不得**写在同步函数体内（自调度）

## Components and Interfaces

### 前端（新建）

- `composables/h7ListedDisclosureModel.ts`
  - `H7_INDUSTRIES: readonly {key,label}[]`（4 个）
  - `H7ListedCategory = { key: string; label: string; industry: string }`
  - `createDefaultH7Categories(): H7ListedCategory[]`（每产业 1 个，label = `类别`）
  - `H7_COST_MOVEMENT_ROWS: H7MovementRowDef[]`（34 行）
  - `H7_FAIR_MOVEMENT_ROWS: H7MovementRowDef[]`（11 行）
  - `h7CellValue(map, def, colKey, rows)` / `h7TotalCellValue(map, def, cats, rows)`
  - `H7ListedSyncSnapshot = { categories, cost: MovementCellMap, fair: MovementCellMap,
    noteImpairment, notePolicy, noteSupplement }`
- `composables/h7SoeDisclosureModel.ts`
  - `H7_SOE_INDUSTRIES`、`H7SoeCategory`、`H7SoeIndustryBlock`
  - `createDefaultSoeBlocks()`、`industryTotals(block)`、`grandTotal(blocks)`
  - `buildSoeDisplayRows(blocks)` → `{label, begin, increase, decrease, end, kind, industryKey, categoryId}[]`
  - `H7SoeSyncSnapshot = { cost: H7SoeIndustryBlock[], fair: H7SoeIndustryBlock[],
    notePolicy, noteSupplement, noteFairBasis }`
- `composables/h7NoteSectionMap.ts`
  - `H7_NOTE_SECTION`（字面量内联）/ `H7_DISCLOSURE_SHEET_NAME` / `H7_LISTED_SUBTABLE` /
    `H7_SOE_SUBTABLE` / `H7_LEGACY_OBSOLETE_TABLES` / `isH7DisclosureApplicable` /
    `resolveH7CurrentStandard`
- `composables/h7DisclosureSyncPayload.ts`
  - `buildH7ListedColumns(cats)` / `H7_SOE_COLUMNS`
  - `buildH7ListedSubTableData(snap)` / `buildH7SoeSubTableData(snap)`
  - `H7_NOTE_TEXT_TITLES` / `buildH7NoteTexts()`
  - `buildH7ListedSyncPayloads()` / `buildH7SoeSyncPayloads()`
- 组件重建：`h7/core/H7TabDisclosureListed.vue`、`h7/core/H7TabDisclosureSoe.vue`

### 后端

- `backend/scripts/fix/fix_note_h7_biological_assets_structure.py`（新建）
- `backend/tests/test_note_h7_biological_assets_structure.py`（新建）
- `_SECTION_PROMPTS` 补 H7 披露文本域 AI prompt

### 前端守卫

- `composables/__tests__/h7NoteSubtableContract.spec.ts`（新建）
- `composables/__tests__/h7DisclosureModel.spec.ts`（新建，派生公式）

## Data Models

上市列（默认 6 列，两级；`group` 由产业承载）：

```
{ key: 'label',      label: '项目', is_label: true }          ← rowspan 2，无 group
{ key: 'crop_1',      label: '类别', group: '种植业',     format: 'amount' }
{ key: 'livestock_1', label: '类别', group: '畜牧养殖业', format: 'amount' }
{ key: 'forestry_1',  label: '类别', group: '林业',       format: 'amount' }
{ key: 'aquatic_1',   label: '类别', group: '水产业',     format: 'amount' }
{ key: 'total',       label: '合计', format: 'amount' }        ← rowspan 2，无 group
```

`headers` = `['项目','类别','类别','类别','类别','合计']`（源模板 R10 字面）；
`_column_groups` = `[{种植业,1,1},{畜牧养殖业,2,1},{林业,3,1},{水产业,4,1}]`。

国企列（5 列 flat）：`label/begin/increase/decrease/end` →
`项目/期初账面价值/本期增加额/本期减少额/期末账面价值`。

国企 seed 行（9 行，源 13 行里 4 个 `……` 纯占位行删除）：

```
一、种植业 / 其中：1． / 二、畜牧养殖业 / 其中：1． /
三、林业 / 其中：1． / 四、水产业 / 其中：1． / 合计
```

`_note_texts` 标题映射：

```
listed-policy       → 计量模式与折旧政策
listed-impairment   → 减值测试与可收回金额说明
listed-supplement   → 补充披露（数量、寿命、风险与管理措施）
soe-policy          → 计量政策与折旧方法
soe-fair-basis      → 公允价值确认依据
soe-supplement      → 风险情况与管理措施
```

## Correctness Properties

### Property 1: 上市行集与源 xlsx 一致且 `……` 行保留

*For any* 上市表，模板与载荷的行标签序列（空白归一后）SHALL 等于源 xlsx 对应区段
（表1 R11–R44 共 34 行、表2 R53–R64 共 11 行）；表1 SHALL 保留 3 个 `……` 行、
表2 SHALL 保留 2 个 `……` 行，且它们 SHALL 参与所属小计。

**Validates: Requirements 1.1, 1.2, 1.7, 4.4**

### Property 2: 上市两级表头与源模板合并区一致

*For any* 上市表，`columns[0]`（项目）与末列（合计）SHALL NOT 带 `group`；
其余列 SHALL 带 `group` 且 `group` ∈ 4 个产业名；`_column_groups` SHALL 由
`columns[].group` 派生一致；SHALL NOT 出现 `……` 作列名；SHALL NOT 标 `flat`。

**Validates: Requirements 1.3, 1.4, 1.6, 4.3**

### Property 3: 类别列增删的 key 稳定性

*For any* 类别序列，`buildH7ListedColumns` 的 key SHALL 唯一；删除中间类别后剩余类别的
key SHALL 不变；新增类别的 key SHALL 不与已删除的 key 冲突。

**Validates: Requirements 1.5**

### Property 4: 上市派生公式

*For any* `MovementCellMap`，SHALL 满足：小计 = 分项之和；期末余额 = 期初 + 增 − 减；
账面价值 = 原值 − 累计折旧 − 减值准备；公允价值表 本期变动 = 加项 − 减项 + 公允价值变动 +
其他变动，期末余额 = 期初 + 本期变动；合计列 = 各类别列之和。

**Validates: Requirements 1.8**

### Property 5: 国企行集、派生与可扩类别

国企载荷行 SHALL 为 4 产业行 + 各自类别行 + 合计；产业行有类别时 SHALL = 类别之和；
`期末账面价值` SHALL = 期初 + 增 − 减（读时派生，不持久化）；合计 SHALL = 4 产业行之和；
模板 seed SHALL 为 9 行且 SHALL NOT 含 `……` 占位行。

**Validates: Requirements 2.2, 2.3, 2.4, 2.5, 4.4**

### Property 6: 载荷定位与列键一致

*For any* 变体，载荷 `section_id` SHALL 逐字等于模板 `section_number`；`sheet_name` SHALL
逐字等于源 xlsx tab 名；推送表名 SHALL 存在于模板；载荷 `columns[].key` 序列在**默认类别**下
SHALL 等于模板 `columns[].key` 序列；每行键 SHALL ⊆ 列键 ∪ 结构标记。

**Validates: Requirements 3.1, 3.2, 3.3, 4.2**

### Property 7: 旧表名与 `_removed_table_keys`

模板 SHALL NOT 再含 `项  目`；上市载荷 `_removed_table_keys` SHALL 含 `项  目`。

**Validates: Requirements 4.1**

### Property 8: `_note_texts` 中文标题与空过滤

*For any* 非空文本 SHALL 有非空中文 `title`；空白文本 SHALL 不产生条目；全空时 SHALL 无
`_note_texts` 键；SHALL 位于 `sub_table_data` 内。

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 9: 无自调度、金额控件合规、缺口清单变短

两个 Tab 的同步函数体 SHALL NOT 含 `scheduleAutoSync`；SHALL NOT 出现自造
`toLocaleString` 金额格式化；金额录入 SHALL 用 `WpAmountInput`；
`MISSING_SYNC_PATH` SHALL NOT 再含这两个组件。

**Validates: Requirements 3.5, 3.7, 5.4, 5.5**

### Property 10: 幂等与零回归

连续两次运行脚本第二次 SHALL 为空操作；附注 JSON SHALL 可解析；两章节之外内容不变；
guidance SHALL 非空；`text_sections` SHALL 无裸表名。

**Validates: Requirements 4.5, 4.6, 4.7, 6.4**

## Error Handling

- `run_section` 在 `validate_section` 有 errs 时不写文件。
- 上市第 2 张表改名走 `rule(aliases=['项  目'])`，**绝不进 `drop_tables`**
  （drop 在 `apply_plan` 之前执行会连行删掉）。
- `h7CellValue` 对未知 `kind` 返回 0，对缺失 cell 返回 0，不抛错。
- `buildH7NoteTexts` 对 `undefined`/`null`/空串一致过滤。
- 国企删除最后一个类别行时产业行自动转为可录入（不清零已有金额）。
- 源 xlsx 读取失败时守卫直接 fail（不 fallback）。

## Testing Strategy

- 后端：`fix_note_h7_biological_assets_structure.py --check` +
  `test_note_h7_biological_assets_structure.py`（Property 1/2/5/7/10 + openpyxl 交叉比对
  含合并区 + 反向自检）。
- 前端：`h7DisclosureModel.spec.ts`（Property 3/4/5 派生公式，含 PBT）+
  `h7NoteSubtableContract.spec.ts`（Property 1/2/6/7/8/9；读源码断言先 `stripComments`
  并配反向自检）。
- 平台守卫回归：`disclosureAutoSyncCoverage.spec.ts`（`MISSING_SYNC_PATH` 移出 2 项）、
  `disclosureColumnsCoverage.spec.ts`（`P1_ROUTE` 登记 `buildH7ListedColumns`）、
  `disclosureSheetNameRegistry.spec.ts`（新增 H7 条目，需重生成 registry）。
- CI：`note-h7-structure` + `note-h7-frontend`。
