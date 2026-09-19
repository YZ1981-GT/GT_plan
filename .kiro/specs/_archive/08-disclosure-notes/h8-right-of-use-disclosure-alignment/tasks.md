# Implementation Plan: H8 使用权资产披露列元数据与文本对齐

## Overview

H8 行集已与源模板一致，欠账是：两版 `columns`/`guidance` 全缺、上市 `……` 占位列头收不到数据、`_note_texts` 缺中文 title 且不过滤空文本。本 spec 补列元数据 + 展开列头 + 修文本元数据 + 双侧守卫。**不动行集**（上市 `……` 行是真实可扩行）、不动自动同步（已正确）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"], "rationale": "源模板与现状确权（含区分 …… 的列/行两种语义）" },
    { "wave": 2, "tasks": ["2"], "rationale": "模板 columns 定 key，是前端对齐的真源" },
    { "wave": 3, "tasks": ["3"], "rationale": "载荷 _note_texts 修正" },
    { "wave": 4, "tasks": ["4", "5"], "rationale": "两侧守卫并行" },
    { "wave": 5, "tasks": ["6"], "rationale": "CI 挂载依赖守卫" },
    { "wave": 6, "tasks": ["7"], "rationale": "实测依赖全链" }
  ]
}
```

## Tasks

- [x] 1. 源模板与现状确权
  - openpyxl 读 `H8 使用权资产.xlsx`：上市 sheet 行 6 表头 6 列（第 5 列为 `……`）/ 行 7~45 四层 38 行；国企 sheet 行 6 表头 5 列 / 行 7~31 五层 25 行（含 三、五 层的 `——` 列示约定）。
  - 实证模板两版行集已一致、`columns=0`、无 `guidance`；国企 `text_sections=[]` 正确（源无说明段）。
  - **关键判断**：`……` 作**列头**收不到数据须展开为 `其他`（底稿默认分类第 4 类）；`……` 作**行**是底稿模型真实可扩行（`*_ellipsis` 键参与 `sumOf`）须保留。
  - 实证两 Tab `scheduleAutoSync` 在 `onSave` 回调，无自调度。
  - _Requirements: 1.1, 1.3, 4.4_

- [x] 2. 模板补 columns/guidance + 展开 `……` 列头（`fix_note_h8_right_of_use_structure.py`）
  - 复用 `_note_structure_kit`；两版 `rule(..., rows=None, guidance)`；上市 6 列（`……`→`其他`）、国企 5 列，均 `flat_columns`。
  - guidance 按 R2.2 / R2.3 写（源模板四层/五层结构 + 层间派生 + `——` 列示约定 + 15 号文减值披露 + `……` 可扩行说明）。
  - `--dry-run` → 应用 → `--check` 幂等 0 欠账。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3_

- [x] 3. 载荷 `_note_texts` 补中文 title + 空过滤
  - 新增 `H8_NOTE_TEXT_TITLES` + `buildH8NoteTexts()` 纯函数（两变体共用）；全空时不产生 `_note_texts` 键。
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 4. 后端守卫 `test_note_h8_right_of_use_structure.py`
  - Property 1/2/4/7：columns 表态与对齐 headers、`……` 不复活且上市第 5 列为 `其他`、行集与源 xlsx 交叉比对（上市 38 行含 6 个 `……` 行正向断言、国企 25 行五层）、guidance 非空、无 `_column_groups`、反向自检。
  - _Requirements: 4.1_

- [x] 5. 前端守卫 `h8NoteSubtableContract.spec.ts`
  - Property 3/5/6：载荷列 key ≡ 模板列 key（两版）、`_note_texts` 中文 title 且空过滤且在 `sub_table_data` 内、两 Tab `syncToNotes` 函数体无自调度（花括号配对截取 + `stripComments` + 反向自检）。
  - _Requirements: 4.2_

- [x] 6. CI 挂载 `note-h8-structure` job
  - `--check` + 后端守卫（需 openpyxl）。
  - _Requirements: 4.3_

- [x] 7. 实测（浏览器/真实后端 + 只读 DB）
  - soe 或 listed 任一变体：推送后落库列头为展开后的实际类别（无 `……`）、`text_content` 显示中文小标题（非 `【listed-short-low】`）、行集与模板一致；数据复原。
  - _Requirements: 1.1, 3.1_

## Notes

- **🔴 实测挖出的额外缺陷（Task 7 顺带修）**：模板 seed 路径补了 `flat` 但**载荷侧
  `columns` 未表态** → 推送路径（真实用户走的路径）仍被 `_infer_groups_from_headers`
  推出凭空父表头。实测国企投影出 `_column_groups=[{group:'本期',start:2,span:2}]`
  （`本期增加`/`本期减少` 被并组）。已给 `buildH8ListedColumns` / `H8_SOE_COLUMNS`
  首列补 `flat: true`，守卫加「两版载荷列须显式 flat 且不得声明 group」断言。
  **教训：`flat` 必须 seed 与推送两处都加，只测其中一路会漏。**
- **`……` 的两种语义必须分开处理**（本 spec 最易踩错处）：列头须展开（收不到数据），行须保留（底稿模型真实可扩行、参与 `sumOf`）。误删 `……` 行会破坏载荷↔模板行对齐。
- **不动行集**：`rule(..., rows=None)`。
- **不动自动同步**：两 Tab 的 `scheduleAutoSync` 在 `onSave` 回调（正确），守卫只做防回退断言。
- 国企 `text_sections=[]` 是正确状态（源 xlsx 无说明段），不要补。
- 上市列 key 用**类别名本身**（与 `buildH8ListedColumns` 的 `key: c.label` 同口径，H1「固定资产情况」同范式）。
