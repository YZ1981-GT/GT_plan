# Design

## Overview

三层改动，与 H2/H3/H5/H8 同范式：

1. **模板层**：幂等脚本 `fix_note_h9_h10_structure.py` 覆盖 4 个章节
   （listed `三、资产处置收益（损`、`五、47`；soe `八、75`、`八、52`）：
   - H10 上市两张同名 `项  目` 表**正名**（`资产处置收益（损失以“-”填列）` / `试运行销售损益`）
   - H10 两版主表行集回归源模板 10 行 + `合计`（补 债务重组 / 使用权资产 / 油气资产 三行，
     删 `可无限量添加行` 占位与 `header_label` 假行）
   - H10 上市试运行表恢复两级表头 5 列（`group` = 本期发生额 / 上期发生额）
   - 四表补 `columns` + `guidance`；H10 国企 `text_sections` 剥 `**` 残迹
   - H9 两版只补 `columns`/`guidance`（`rows=None`，结构本就对）
2. **载荷层**：`h10NoteSectionMap.ts` / `h10DisclosureSyncPayload.ts` / `h9DisclosureSyncPayload.ts`
   - 章节号改逐字 `三、资产处置收益（损`；国企 sheet 名改 `附注披露信息（国企）`
   - 表名常量改正名；**删掉 `项  目__trial` 与 `_trial_detail` 双写绕过**
   - 试运行表列定义改 5 列两级，行推四个业务键（收入/成本 分列）而非净额
   - `_note_texts` 抽 `buildH9NoteTexts()` / `buildH10NoteTexts()`（中文 title + 空过滤）
   - `_removed_table_keys` 带上旧名 `项  目`
3. **守卫层**：后端 `test_note_h9_h10_structure.py`（openpyxl 交叉比对 + 反向自检）+
   前端 `h9h10NoteSubtableContract.spec.ts` + CI job `note-h9-h10-structure`。

## Architecture

**同名表是致命的**：`sub_table_data` 以表名为键，模板两张表同名 `项  目` 时后一张覆盖前一张。
既有实现用 `项  目__trial` 后缀键绕过，但**投影器只渲染模板里存在的表名**，该键是孤儿 →
试运行明细在附注永远为空。正确解法只有给模板正名（同 K2「合同取得成本」/ H2「工程物资」范式）。

**章节号定位**：`sync_from_workpaper` 用 `(project_id, year, note_section)` 精确匹配，
`current_standard` 不参与。listed 模板 `三、` 章的 `section_number` 被 md 重建截断为 10 字符
是**既有真源形态**（全库 70+ 条同款），修法是**改常量对齐模板**，不是改模板编号
（会波及整章 + 并发 spec）。

**两级表头唯一机制**：`ColumnDef.group` →（`note_sub_table_projector._extract_column_groups`）
→ `_column_groups` → 前端 `DisclosureEditor.activeTableColumns` 嵌套 el-table-column +
`note_word_exporter._build_two_level_header_rows`。标签列不给 `group`（rowspan=2 混合分组）。
**两级表不得标 `flat`**（`flat` 会让 `_extract_column_groups` 直接返 `[]`）。

**`flat` 必须 seed 与推送两处都加**（H8 实测教训：只加模板会让推送路径继续被前缀推断）。
H10 主表的 `本期发生额`/`上期发生额` 与 H9 的 `期末余额`/`期初余额` 都无共享前缀，推断结果为空，
但仍显式表态以免将来列名变化后被反猜。

**试运行表口径改净额为分列**：源模板要收入/成本分列，载荷已有四个字段（`current_income` 等），
原实现把它们塞进 `extra` 但列定义只声明净额 3 列 → 四列数据无落点。改为列定义 5 列、
行只推四个分列键（净额由附注侧不需要，底稿 UI 保留净额展示）。

## Components and Interfaces

### 后端

- `backend/scripts/fix/fix_note_h9_h10_structure.py`（新建，复用 `_note_structure_kit`）
  - `_TARGETS`：`h10_listed`（`三、资产处置收益（损`）/ `h10_soe`（`八、75`）/
    `h9_listed`（`五、47`）/ `h9_soe`（`八、52`）
  - H10 上市：`rule('资产处置收益（损失以“-”填列）', flat 3 列, ROWS_LISTED, guidance,
    aliases=['项  目'])` + `rule('试运行销售损益', 两级 5 列, TRIAL_ROWS, guidance, insert=True)`
    —— **改名走 `aliases` 不进 `drops`**（`drop_tables` 在 `apply_plan` 前执行，会连行删掉）
  - H10 国企：`rule('资产处置收益（损失以“-”号填列）', flat 4 列, ROWS_SOE, guidance)` +
    `strip_markdown_marks` 处理 `text_sections`
  - H9 两版：`rule('租赁负债', flat 3 列, None, guidance)`
- `backend/tests/test_note_h9_h10_structure.py`（新建）

### 前端

- `h10NoteSectionMap.ts`：`H10_NOTE_SECTION.listed` → `'三、资产处置收益（损'`；
  `H10_DISCLOSURE_SHEET_NAME.soe` → `'附注披露信息（国企）'`；
  `H10_MAIN_SUBTABLE.listed` → `'资产处置收益（损失以“-”填列）'`；
  `H10_TRIAL_SUBTABLE` → `'试运行销售损益'`；新增 `H10_LEGACY_OBSOLETE_TABLES = ['项  目']`
- `h10DisclosureSyncPayload.ts`：试运行列定义改两级 5 列；`buildH10TrialSubTableRows` 只推
  四个分列键 + 合计；删 `__trial` / `_trial_detail`；`buildH10NoteTexts()`；`_removed_table_keys`
- `h9DisclosureSyncPayload.ts`：两版 `columns` 首列补 `flat`；`buildH9NoteTexts()`
- `composables/__tests__/h9h10NoteSubtableContract.spec.ts`（新建）

## Data Models

H10 上市主表列（3 列 flat）：`label/current_amount/prior_amount` → `项目/本期发生额/上期发生额`

H10 国企主表列（4 列 flat）：上列 + `non_recurring_amount` → `计入当期非经常性损益的金额`

H10 上市试运行表列（5 列两级）：

```
{ key: label,          label: 项目,   is_label: true }                 ← rowspan=2，无 group
{ key: current_income, label: 收入,  group: 本期发生额, format: amount }
{ key: current_cost,   label: 成本,  group: 本期发生额, format: amount }
{ key: prior_income,   label: 收入,  group: 上期发生额, format: amount }
{ key: prior_cost,     label: 成本,  group: 上期发生额, format: amount }
```

H9 上市列（3 列 flat）：`label/end_balance/prior_balance` → `项目/期末余额/上年年末余额`
H9 国企列（3 列 flat）：`label/end_balance/begin_balance` → `项目/期末余额/期初余额`

H10 主表行集（源 xlsx listed R9~R19 / soe R9~R18，两版仅括注用语不同）：

```
持有待售的非流动资产（处置组）处置利得 / 固定资产处置利得 / 在建工程处置利得 /
生产性生物资产处置利得 / 无形资产处置利得 / 债务重组中因处置非流动资产产生的利得 /
非货币性资产交换产生的利得 / 使用权资产处置利得 / 油气资产处置利得 / 试运行销售损益 / 合计
```

上市各行带 `（损失以“-”填列）` 后缀（源模板字面，注意 `债务重组` 与 `使用权资产`/`油气资产`
三行源模板用**半角引号** `"-"`，模板统一为全角 `“-”` 以对齐载荷 `H10_NOTE_TEMPLATE_LABEL`）。

H10 上市试运行表行集：`固定资产试运行销售 / 研发样品销售 / 合计`

`_note_texts` 标题映射：

```
listed-interest    → 租赁负债利息费用说明        (H9)
soe-guidance       → 补充披露说明                (H9)
disclosure-note    → 资产处置收益说明            (H10)
```

## Correctness Properties

### Property 1: 章节号与表名逐字命中模板

*For any* 变体，载荷 `section_id` SHALL 逐字等于模板 `section_number`，
`sheet_name` SHALL 逐字等于源 xlsx tab 名，推送的每个非元数据表名 SHALL 存在于模板
`tables[].name`（无孤儿子表）。

**Validates: Requirements 1.1, 1.3, 1.5**

### Property 2: 旧表名进 `_removed_table_keys` 且不复活

改名后模板 SHALL NOT 再含 `项  目`；载荷 `_removed_table_keys` SHALL 含 `项  目`；
载荷 SHALL NOT 含 `项  目__trial` / `_trial_detail` 绕过键。

**Validates: Requirements 1.2, 1.4**

### Property 3: 行集与源 xlsx 一致且无假行

*For any* H10 变体，模板主表行标签序列（空白归一后）SHALL 等于源 xlsx 对应区段 + `合计`；
SHALL NOT 含 `可无限量添加行` 或 `row_type=header_label`；
`H10_NOTE_TEMPLATE_LABEL` 每个变体标签 SHALL 出现在对应模板行集中。

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

### Property 4: 两级表头正确、单级表 flat

H10 上市试运行表 `columns` SHALL 有 5 列且 `group` 为两个各 span 2 的分组、标签列无 `group`、
SHALL NOT 标 `flat`；其余三表 SHALL 显式 `flat` 且无 `group`。
*For any* 表，`columns[].label` 序列 SHALL 等于 `headers`，金额列 SHALL `format=amount`。

**Validates: Requirements 3.1, 3.2, 4.1, 4.2, 4.3**

### Property 5: 载荷列 key ≡ 模板列 key 且行键 ⊆ 列键

*For any* 变体与表，载荷 `columns[].key` 序列 SHALL 等于模板 `columns[].key` 序列；
每个推送行的键 SHALL ⊆ `columns[].key` ∪ 结构标记（`is_total`/`row_type`/`row_key`/`remark`）。

**Validates: Requirements 3.3, 4.1**

### Property 6: `_note_texts` 中文标题与空过滤

*For any* 非空文本 SHALL 有非空中文 `title`；空白文本 SHALL 不产生条目；
全空时 SHALL 无 `_note_texts` 键；`_note_texts` SHALL 在 `sub_table_data` 内。

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 7: 无自调度与 guidance 非空

三个披露 Tab（H9 两版 + H10 Base）的同步函数体 SHALL NOT 含 `scheduleAutoSync`；
四个章节的每张表 `guidance` SHALL 非空；H10 国企 `text_sections` SHALL NOT 含 `**`。

**Validates: Requirements 4.4, 4.5, 6.3**

### Property 8: 幂等与零回归

连续两次运行脚本第二次 SHALL 为空操作；附注 JSON SHALL 可解析；四章节之外内容不变。

**Validates: Requirements 6.5**

## Error Handling

- `run_section` 在 `validate_section` 有 errs 时不写文件；`rows=None` 表示不动行集。
- 改名用 `rule(aliases=[...])`，**绝不进 `drop_tables`**（drop 在 `apply_plan` 前执行会连行删掉）。
- `buildH9NoteTexts` / `buildH10NoteTexts` 对 `undefined`/`null`/空串一致过滤，不抛错。
- 源 xlsx 读取失败时守卫直接 fail（不 fallback）。
- 载荷侧改名不影响既有项目：H10 全库 `last_sync_at` 均为 NULL（无人同步过）→ 无存量孤儿表需清理，
  `_removed_table_keys` 只作前瞻保护。

## Testing Strategy

- 后端：`fix_note_h9_h10_structure.py --check` + `test_note_h9_h10_structure.py`
  （Property 1/3/4/7/8 + openpyxl 交叉比对 + 反向自检）。
- 前端：`h9h10NoteSubtableContract.spec.ts`（Property 1/2/4/5/6/7；Property 7 读组件源码先
  `stripComments` 并按花括号配对截取函数体，含反向自检）。
- 平台守卫回归：`disclosureColumnsCoverage.spec.ts`（H10 allowlist 3 表须移出、`P1_ROUTE`
  改指新契约）、`disclosureSheetNameRegistry.spec.ts`（H10 soe sheet 名改动后需重生成 registry）。
- CI：`note-h9-h10-structure` job。
