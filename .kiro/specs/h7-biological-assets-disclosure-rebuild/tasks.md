# Implementation Plan: H7 生产性生物资产披露重建

## Overview

H7 是 H 循环唯一需要整体重建的循环：两个披露 Tab 只有单行只读 `movementRows`，
既无章节映射也无载荷，`disclosure-sync-path-buildout` 曾接线后撤回。本 spec 按源模板
重建模型 / 映射 / 载荷 / 组件 / 模板 / 双侧守卫 / CI，并实测。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"], "rationale": "源模板确权（合并区/行集/tab 名逐字）" },
    { "wave": 2, "tasks": ["2", "3"], "rationale": "上市与国企数据模型互不依赖，可并行" },
    { "wave": 3, "tasks": ["4"], "rationale": "章节映射与载荷依赖两个模型定 key" },
    { "wave": 4, "tasks": ["5"], "rationale": "模板 seed 必须与载荷 key 一致，故在载荷之后" },
    { "wave": 5, "tasks": ["6", "7"], "rationale": "两个 Tab 重建互不依赖" },
    { "wave": 6, "tasks": ["8", "9"], "rationale": "两侧守卫并行" },
    { "wave": 7, "tasks": ["10"], "rationale": "平台守卫回归依赖组件与载荷定稿" },
    { "wave": 8, "tasks": ["11"], "rationale": "CI 挂载依赖守卫" },
    { "wave": 9, "tasks": ["12"], "rationale": "实测依赖全链" }
  ]
}
```

## Tasks

- [ ] 1. 源模板与现状确权
  - openpyxl 直读 `H7 生产性生物资产.xlsx`：确认上市两表合并区
    （`A9:A10`/`B9:C9`/`D9:E9`/`F9:G9`/`H9:I9`/`J9:J10` 与 R51:R52 同构）、
    R10/R52 为 `类别 | ……` × 4、表1 R11–R44 共 34 行、表2 R53–R64 共 11 行（R61 空）；
    国企 R8/R25 为 5 列、两表各 13 行（4 产业 × 3 + 合计）。
  - 确认 tab 名：上市 `附注披露信息（上市公司）`、国企 **`附注披露信息（国有企业）`**。
  - 确认模板现状：上市第 2 表名为 `项  目`、两表各 1 个 `header_label` 假行、
    4 表 `columns=0` 无 guidance；国企两表各 4 个 `……` 占位行；
    `variant_matrix` 上市 `五、24` / 国企 `八、24`。
  - _Requirements: 1.1, 1.2, 1.3, 3.2, 4.1, 4.4_

- [ ] 2. 上市数据模型 `h7ListedDisclosureModel.ts`
  - 4 产业常量 + `H7ListedCategory`（`key = {industryKey}_{seq}` 稳定）+
    `createDefaultH7Categories()`（每产业 1 个，label 取源模板字面 `类别`）。
  - `H7_COST_MOVEMENT_ROWS`（34 行四层，含 3 个 `ellipsis` 参与小计）、
    `H7_FAIR_MOVEMENT_ROWS`（11 行，含 2 个 `ellipsis`）。
  - `h7CellValue` 支持 `section/detail/ellipsis/subtotal(sumOf)/calc(endOf)/book(bookOf)/
    delta(plus,minus)/calc2`；`h7TotalCellValue` 合计列。
  - 复用 `h1ListedDisclosureModel` 的 `MovementCellMap`/`rawCell`/`setCell`。
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.7, 1.8_

- [ ] 3. 国企数据模型 `h7SoeDisclosureModel.ts`
  - `H7_SOE_INDUSTRIES`（4 个，label 取源模板 `一、种植业` 等）+ `H7SoeIndustryBlock`
    （`categories[{id,name,begin,increase,decrease}]` + `selfAmounts`）。
  - `industryTotals`（有类别取类别之和、无类别取 `selfAmounts`）、`grandTotal`、
    `buildSoeDisplayRows`（产业行 + 类别行 + 合计），`end` 恒派生不持久化。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 4. 章节映射与载荷 `h7NoteSectionMap.ts` / `h7DisclosureSyncPayload.ts`
  - 章节号字面量**内联**（`五、24` / `八、24`），sheet 名逐字（国企「国有企业」）；
    `H7_LISTED_SUBTABLE`/`H7_SOE_SUBTABLE` 对齐模板正名后的表名；
    `H7_LEGACY_OBSOLETE_TABLES = ['项  目']`。
  - `buildH7ListedColumns(cats)`（两级，`group` = 产业；项目/合计 无 group；不标 flat）、
    `H7_SOE_COLUMNS`（5 列 flat）。
  - `buildH7ListedSubTableData` / `buildH7SoeSubTableData` / `buildH7NoteTexts`
    （中文 title + 空过滤）/ `_removed_table_keys`。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_

- [ ] 5. 模板幂等脚本 `fix_note_h7_biological_assets_structure.py`
  - 上市：第 2 表 `项  目` → 「（2）以公允价值计量」（走 `rule(aliases=)` **不进 drops**）；
    两表删 `header_label` 假行；两表补两级 5 数据列 + guidance；行集按源模板 34/11 行。
  - 国企：两表补 5 列 flat + guidance；行集 13 → 9 行（删 4 个 `……` 纯占位行）；
    `text_sections` 补源模板 R39「注：应披露公允价值确认依据。」+ R40 恢复「（3）」前缀，
    裸表名加 `#### ` 前缀。
  - `--dry-run` → 应用 → `--check` 幂等 0 欠账。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 6.4_

- [ ] 6. 重建 `H7TabDisclosureListed.vue`
  - 两张动态列表格（按产业分组表头 + 类别列增删改名 + 合计列只读派生），
    金额录入用 `WpAmountInput`、只读金额走 `fmtAmount`；派生行只读并带公式 tooltip。
  - 3 个文本域（政策 / 减值 / 补充）+ AI 辅助 + 复核；源模板红字作方法论上下文块。
  - 接 `useDisclosureAutoSync`（`scheduleAutoSync` 放保存处理器，**不得**放同步函数体内）。
  - _Requirements: 1.3, 1.4, 1.5, 1.8, 3.5, 3.6, 5.4, 5.5, 5.6_

- [ ] 7. 重建 `H7TabDisclosureSoe.vue`
  - 两张 5 列表格（4 产业 + 可扩类别行，新增走 `ElMessageBox.prompt` 先输名称）；
    产业行有类别时只读派生、无类别时可录入；期末列恒派生。
  - 3 个文本域（政策 / 公允价值依据 / 风险与管理措施）+ AI 辅助 + 复核。
  - 接自动同步（同上约束）。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.5, 3.6, 5.4, 5.5, 5.6_

- [ ] 8. 后端守卫 `test_note_h7_biological_assets_structure.py`
  - Property 1/2/5/7/10：行集与源 xlsx 交叉比对（含 `……` 行保留正向断言）、
    两级表头与合并区一致、国企 9 行且无 `……`、`项  目` 不复活、
    columns/guidance 齐备、`text_sections` 完整且无裸表名、反向自检。
  - _Requirements: 6.1, 6.4_

- [ ] 9. 前端守卫 `h7DisclosureModel.spec.ts` + `h7NoteSubtableContract.spec.ts`
  - 模型：Property 3（key 稳定性）+ Property 4（上市派生公式，含 PBT）+ Property 5（国企派生）。
  - 契约：Property 1/2/6/7/8/9（表名/章节号/sheet 名逐字、列 key ≡ 模板 key、行键 ⊆ 列键、
    两级 group、`_removed_table_keys`、`_note_texts` 规范、无自调度、无自造 toLocaleString、
    `WpAmountInput` 已用）。
  - _Requirements: 6.2_

- [ ] 10. 平台守卫回归
  - `disclosureAutoSyncCoverage.spec.ts`：`MISSING_SYNC_PATH` 移出
    `H7TabDisclosureListed.vue` / `H7TabDisclosureSoe.vue`（清单只许变短）。
  - `disclosureColumnsCoverage.spec.ts`：`P1_ROUTE` 登记 `buildH7ListedColumns`
    （参数化 builder 不得叫 `buildXColumns` 被 sweep 空入参调用 → 对外零参导出）。
  - 重跑 `gen_note_wp_sync_registry.py --write` 新增 H7 条目并核 diff 范围。
  - 后端 `_SECTION_PROMPTS` 补 H7 六个披露文本域 prompt（写明源模板口径 + 不得虚构）。
  - _Requirements: 3.7, 5.6, 6.2_

- [ ] 11. CI 挂载 `note-h7-structure` + `note-h7-frontend`
  - `--check` + 后端守卫（需 openpyxl）；前端两份守卫 + 平台三份回归。
  - _Requirements: 6.3_

- [ ] 12. 实测（真实后端 + 只读 DB）
  - 国企侧活体：录入产业与类别 → 不点按钮自动同步 → 核 `八、24` 落库两表、9+ 行、
    5 列元数据、派生金额、`_last_sync_sheet` 为「国有企业」、`text_content` 中文小标题。
  - 上市侧若无活体则记录为遗留（不临时改项目 `entity_type`）。
  - 复原前先完整快照（含 `text_content` 全文），实测后逐字复原。
  - _Requirements: 6.5_

## Notes

- **🔴 上市列 `key` 不能用 `key: label`**（H1/H8 那样）：四个产业的默认叶子名都是源模板字面
  `类别`，用 label 作 key 会撞键 → 用稳定 `{industryKey}_{seq}`。
- **🔴 `……` 两种语义相反**：作**列头**必须丢弃（永远收不到数据）；作**行**是真实可扩明细行
  且参与小计，必须保留（上市表1 三个、表2 两个）。国企的 `……` 是**行形态的「加更多」标记**，
  在动态类别行模型下不需要，故 seed 删除（与上市的可扩明细行不同：上市那三处在模型里有
  对应的 `*_ellipsis` 键）。
- **🔴 国企 sheet 名是 `附注披露信息（国有企业）`**，与 H9/H10 的 `（国企）` 不同，禁套用。
- **🔴 改名走 `rule(aliases=[...])`，不能进 `drop_tables`**（drop 在 `apply_plan` 前执行）。
- **🔴 `X_NOTE_SECTION` 字面量必须内联且对象体内不写注释**（registry 生成器正则约束，
  H10 两种写法都踩过）。
- 上市两表是两级表头 → **不得**标 `flat`；国企两表单级 → **必须**标 `flat`。
- 源模板 R7「有公益性生物资产的企业应增设『公益性生物资产』项目」是**说明段**（已在
  `text_sections`），本 spec 不为公益性生物资产建表（源模板未给结构，宁缺勿造）。
