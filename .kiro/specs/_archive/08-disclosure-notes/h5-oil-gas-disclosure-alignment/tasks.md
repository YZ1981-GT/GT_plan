# Implementation Plan: H5 油气资产披露载荷对齐

## Overview

H5 附注模板结构已与源模板一致，欠账全在前端载荷侧：自造 4 行 vs 模板 15 行四层、列 3 vs 5 且位置化值错列、`_note_texts` 放顶层被静默丢弃、自动同步自调度。本 spec 修载荷 + 补模板 columns/guidance + 双侧守卫。上市侧不建章节（实证 listed 无油气章节）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"], "rationale": "源模板与模板现状确权，后续依赖" },
    { "wave": 2, "tasks": ["2"], "rationale": "模板 columns 定 key，是前端列定义的真源" },
    { "wave": 3, "tasks": ["3", "4"], "rationale": "映射重写与组件修复并行（同一 key 契约）" },
    { "wave": 4, "tasks": ["5", "6"], "rationale": "两侧守卫依赖实现就位" },
    { "wave": 5, "tasks": ["7"], "rationale": "CI 挂载依赖守卫" },
    { "wave": 6, "tasks": ["8"], "rationale": "实测依赖全链完成" }
  ]
}
```

## Tasks

- [x] 1. 源模板与现状确权
  - openpyxl 读 `H5 油气资产.xlsx`：国企 sheet 行 9 表头 5 列、行 10~24 四层 16 行；上市 sheet 为 4 层列转置但**无附注落点**。
  - 实证 `note_template_soe §八、25` 行集已与源模板一致（仅缺 columns/guidance）；`note_template_listed` 油气章节数 **0**；`variant_matrix.you_qi_zi_chan.listed_standalone = null`。
  - 实证 `SyncFromWorkpaperRequest` 无顶层 `_note_texts` 字段 → 现状被静默丢弃。
  - _Requirements: 1.1, 5.1, 6.3_

- [x] 2. 模板补 columns / guidance 幂等脚本 `fix_note_h5_oil_gas_structure.py`
  - 复用 `_note_structure_kit`；表 `油气资产` 补 5 列 `flat_columns`（label/begin/increase/decrease/end），`rows=None` 不动行集。
  - `guidance` 取源模板列示约定（账面价值层「本期增加额/本期减少额」填「—」）+ 四层勾稽（各层 期末 = 期初 + 增加 − 减少；账面价值 = 原价 − 累计折耗 − 减值准备）+ 数据来源（审定表 H5-1）。
  - `--dry-run` → 应用 → `--check` 幂等 0 欠账。
  - _Requirements: 5.1, 5.2, 5.3, 2.4_

- [x] 3. 映射重写 `h5NoteSectionMap.ts`
  - 删本地 `ColumnDef`，改 import 共享类型；`H5_SOE_SUBTABLE` + `H5_SOE_ROW_LABELS`（16 条单一真源）。
  - `H5_SOE_COLUMNS` 3→5 列（label 列 `is_label`+`flat`，金额列 `format:'amount'`）。
  - `buildH5SyncPayload` 改 `layerTotals` 入参 → 构造 16 行**业务键 dict**；层合计只填 `end` 并标 `is_total`，「其中：」行与非期末列为 `null`；账面价值层派生；`_note_texts` **移入 `sub_table_data`** 且带中文 title + 空过滤。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 3.1, 3.2_

- [x] 4. 组件修复 `H5TabDisclosureSoe.vue`
  - 删 `syncToNote()` 内的 `autoSync.scheduleAutoSync(syncToNote)`（自调度）。
  - 新增 `watch([summaryRows, soeDisclosureText], () => autoSync.scheduleAutoSync(syncToNote), { deep: true })`，不加一次性防护。
  - 调用处改传 `layerTotals`（原值/折耗/减值期末），不再传自造 4 行。
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 5. 后端守卫 `test_note_h5_oil_gas_structure.py`
  - `--check` 无欠账 / 表名 / 15 行四层且合计行 `is_total` / flat 表态 / columns key 与前端一致 / guidance；openpyxl 交叉比对源 xlsx 表头与行标签；**listed 豁免断言**；反向自检。
  - _Requirements: 6.1, 6.3_

- [x] 6. 前端契约守卫 `h5NoteSubtableContract.spec.ts`
  - Property 1~8：行标签逐字与序、行形态 dict 无 `values`、5 列对齐、宁缺勿造 null、账面价值派生、`_note_texts` 在 `sub_table_data` 内且不在顶层、读组件源码断言无自调度（先 `stripComments` + 反向自检）。
  - _Requirements: 6.2_

- [x] 7. CI 挂载 `note-h5-structure` job
  - 跑 `--check` + 两侧守卫（需 openpyxl）。
  - _Requirements: 6.1_

- [x] 8. 浏览器 + 真实后端 + 只读 DB 实测
  - 国企披露 Tab 正常挂载（无 Vite 错误），空数据时「同步到附注」按既有语义提示「请先填写披露数据」。
  - **真实后端往返验证**（走 `/api/projects/{pid}/disclosure-notes/sync-from-workpaper`，载荷与 `buildH5SyncPayload` 同形）：返回 `rows_synced: 15` + **`texts_synced: 1`** —— 后者直接证明 `_note_texts` 从载荷顶层移入 `sub_table_data` 后不再被 pydantic 静默丢弃。
  - DB 实证：§八、25 落库 **15 行**；`_sub_table_columns` 列序 `项目|期初余额|本期增加额|本期减少额|期末余额`（5 列、顺序正确，原实现只有 3 列且期末会落进期初列）；`text_content` 含「【补充披露（国资监管要求）】…」；四层期末 5000 / 1200 / 300 / **3500**（= 5000−1200−300，派生正确）；层合计行 `begin`/`increase` 为 **null 而非 0**（宁缺勿造贯通全链）。
  - 数据已完整复原为实测前 seed 态（`last_sync_at=NULL`、无 `sub_table_data`、`text_content` 空）。
  - **未走 UI 端到端**：本项目 H5 无油气资产业务数据，`summaryRows` 依赖 H5-1 审定表 `audited` 列（需走完整审定链），故用真实后端往返替代；载荷形状由 12 项前端契约 + 7 项后端守卫双向锁定。
  - _Requirements: 4.1, 4.2, 3.1_
  - soe 项目：录入后 §八、25 落库 15 行、层合计期末值正确、「其中：」行为 null、`text_content` 含补充披露；静置期无周期重复 POST（验证自调度已除）；数据复原。
  - _Requirements: 4.1, 4.2, 3.1_

## Notes

- **上市侧禁建章节**：源 xlsx 有上市披露 sheet，但 `variant_matrix` listed=null 且 listed 模板实测 0 个油气章节 → 底稿该 sheet 供审计用，不单独披露（宁缺勿造）。守卫固化此事实。
- **`_note_texts` 必须在 `sub_table_data` 内**：顶层会被 pydantic 静默忽略（H5 是本平台第二次踩到，N2/N4/N5 曾因缺 projectId 同类静默失败）。
- **禁自调度**：`scheduleAutoSync` 只能由 watch 实际数据调用，写在同步函数内即假接入。
- 模板行集**不要动**（已与源模板一致），只补 columns/guidance。
