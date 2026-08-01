# Implementation Plan: H9 租赁负债 + H10 资产处置损益 披露结构对齐

## Overview

H10 有两个 P0（上市章节号定位落空、两张表同名致试运行明细永进不了附注）+ 行集缺 3 行 +
两级表头压扁 + 国企 sheet 名漂移；H9 结构本就对，只缺 `columns`/`guidance` 与 `_note_texts` 中文 title。
本 spec 修模板 + 载荷 + 双侧守卫 + CI，并实测。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"], "rationale": "源模板与现状确权（章节号/tab 名/行集/两级表头逐字）" },
    { "wave": 2, "tasks": ["2"], "rationale": "模板正名+补行+两级表头+columns/guidance，定 key 真源" },
    { "wave": 3, "tasks": ["3", "4"], "rationale": "H10/H9 载荷分别对齐模板（互不依赖）" },
    { "wave": 4, "tasks": ["5", "6"], "rationale": "两侧守卫并行" },
    { "wave": 5, "tasks": ["7"], "rationale": "平台守卫回归（allowlist/P1_ROUTE/registry）依赖载荷定稿" },
    { "wave": 6, "tasks": ["8"], "rationale": "CI 挂载依赖守卫" },
    { "wave": 7, "tasks": ["9"], "rationale": "实测依赖全链" }
  ]
}
```

## Tasks

- [x] 1. 源模板与现状确权
  - openpyxl 直读两个 xlsx：H10 上市 R8 主表 3 列 / R9~R19 十行+合计 / R27+R28 试运行两级 5 列 /
    R29~R31 三行；H10 国企 R8 四列 / R9~R18 十行 + R20 `合  计`；H9 上市 R7 三列 + R8~R10 空白可扩区 +
    R11~R13 三行；H9 国企 R7 三列 + R8~R12 五行含 `……`。
  - 实证 tab 名：两循环皆 `附注披露信息（上市公司）` / **`附注披露信息（国企）`**（H7 才是「国有企业」）。
  - 实证模板 listed `section_number` 逐字为 `三、资产处置收益（损`（10 字符），两张表同名 `项  目`。
  - 实证全库 H10/H9 四章节 `last_sync_at` 全 NULL（无存量孤儿表待清理）。
  - _Requirements: 1.1, 1.5, 2.1, 2.2, 3.1_

- [x] 2. 模板幂等脚本 `fix_note_h9_h10_structure.py`
  - H10 上市：两张 `项  目` 正名（`资产处置收益（损失以“-”填列）` / `试运行销售损益`，走
    `rule(aliases=[...])` **不进 drops**）；主表补 债务重组/使用权资产/油气资产 三行、删
    `可无限量添加行` 与 `header_label` 假行；试运行表恢复两级 5 列 + 3 行。
  - H10 国企：主表补同三行；四列 flat；`text_sections` 剥 `**` 残迹。
  - H9 两版：`rows=None` 只补 3 列 flat + guidance。
  - 四章节全表补 `guidance`（源模板红字 + 15 号文 + 勾稽提示）。
  - `--dry-run` → 应用 → `--check` 幂等 0 欠账。
  - _Requirements: 1.2, 2.1, 2.2, 2.3, 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 6.5_

- [x] 3. H10 载荷对齐（`h10NoteSectionMap.ts` / `h10DisclosureSyncPayload.ts`）
  - `H10_NOTE_SECTION.listed` → `'三、资产处置收益（损'`；`H10_DISCLOSURE_SHEET_NAME.soe` →
    `'附注披露信息（国企）'`；`H10_MAIN_SUBTABLE.listed` / `H10_TRIAL_SUBTABLE` 改正名；
    新增 `H10_LEGACY_OBSOLETE_TABLES`。
  - 试运行列定义改两级 5 列；`buildH10TrialSubTableRows` 推四个分列键 + 逐列合计；
    **删 `项  目__trial` 与 `_trial_detail` 双写**。
  - 主表列首列补 `flat`；`buildH10NoteTexts()`；载荷补 `_removed_table_keys`。
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 3.3, 3.4, 4.2, 5.1, 5.2, 5.3_

- [x] 4. H9 载荷对齐（`h9DisclosureSyncPayload.ts`）
  - 两版 `columns` 首列补 `flat: true`；新增 `H9_NOTE_TEXT_TITLES` + `buildH9NoteTexts()`
    （中文 title + 空过滤 + 全空不产生键）。
  - _Requirements: 4.2, 5.1, 5.2, 5.3_

- [x] 5. 后端守卫 `test_note_h9_h10_structure.py`
  - Property 1/3/4/7/8：章节号逐字、表名正名且 `项  目` 不复活、行集与源 xlsx 交叉比对、
    试运行表两级 5 列（标签列无 group、不标 flat）、其余三表 flat 且无 group、
    `columns[].label` == `headers`、guidance 非空、`text_sections` 无 `**`、反向自检。
  - _Requirements: 6.1, 6.5_

- [x] 6. 前端契约 `h9h10NoteSubtableContract.spec.ts`
  - Property 1/2/4/5/6/7：载荷章节号/sheet 名/表名逐字命中、无绕过键、`_removed_table_keys`
    含旧名、载荷列 key ≡ 模板列 key、行键 ⊆ 列键、`_note_texts` 中文 title + 空过滤 + 在
    `sub_table_data` 内、三 Tab 同步函数体无自调度（花括号配对 + `stripComments` + 反向自检）。
  - _Requirements: 6.2, 6.3_

- [x] 7. 平台守卫回归
  - `disclosureColumnsCoverage.spec.ts`：H10 allowlist 3 表按 R3「已修好必删」移出；
    `P1_ROUTE` 的 `buildH10SubTableColumns` 改指新契约（`complete: true`），补登记 H9 builder（若被扫到）。
  - `disclosureSheetNameRegistry.spec.ts`：H10 soe sheet 名改动后重跑
    `gen_note_wp_sync_registry.py --write` 并核 diff 范围。
  - _Requirements: 6.2_

- [x] 8. CI 挂载 `note-h9-h10-structure` job
  - `--check` + 后端守卫（需 openpyxl）+ 前端契约。
  - _Requirements: 6.4_

- [x] 9. 实测（真实后端 + 只读 DB）
  - 国企侧（活体项目为国企模板）：推送后核 `八、75` 落库主表 10 行 + 合计、4 列元数据、
    `_last_sync_sheet` 为 `附注披露信息（国企）`、`text_content` 显示中文小标题；
    H9 `八、52` 同样核 5 行含 `……`。
  - 上市侧若无活体则记录为遗留（不临时改项目 `entity_type`）。
  - 数据复原（记录复原前快照，含 `text_content` 全文）。
  - _Requirements: 1.1, 1.5, 3.2, 5.1_

## Notes

- **🔴 改名必须走 `rule(aliases=[...])`，不能进 `drop_tables`**：`drop_tables` 在 `apply_plan`
  之前执行，会把该表连行一起删掉（H2 已踩）。
- **🔴 listed `三、` 章 `section_number` 的 md 截断是既有真源形态**（全库 70+ 条），
  修法是改常量对齐模板，不是改模板编号。
- **🔴 `flat` 必须 seed 与推送两处都加**（H8 实测教训）。两级表**不得**标 `flat`。
- **`项  目__trial` / `_trial_detail` 是绕过键**：投影器只渲染模板里存在的表名，这两个键是孤儿，
  试运行明细在附注永远为空 → 正名后必须删掉它们，否则双真源。
- H10 全库四章节 `last_sync_at` 全 NULL → 无存量污染需清理，`_removed_table_keys` 只作前瞻保护。
- **H7 生产性生物资产不在本 spec 范围**：源模板上市侧是「类别 + `……`」两级列转置矩阵
  （4 大类各 2 子列 + 合计 = 9 数据列），而底稿组件只有单行 movementRows，须按 G6 范式重建，
  另立 spec。其 tab 名是 `附注披露信息（国有企业）`（与 H9/H10 不同），接线时勿套用本 spec 常量。
