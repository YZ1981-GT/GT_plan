# Implementation Plan: H2 在建工程披露结构对齐

## Overview

H2 在建工程披露结构对齐分三层（附注模板 / 前端映射 / 守卫）协同，围绕源 xlsx 两级表头重建、垃圾表名清理、columns/guidance 补齐。四表取数与同步触发机制不变。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"], "rationale": "源模板结构确权，后续全部依赖" },
    { "wave": 2, "tasks": ["2"], "rationale": "附注模板结构与列 key 确定，是前端映射的真源" },
    { "wave": 3, "tasks": ["3", "4"], "rationale": "后端守卫与前端映射并行（均依赖模板列 key）" },
    { "wave": 4, "tasks": ["5"], "rationale": "前端契约守卫依赖映射与载荷" },
    { "wave": 5, "tasks": ["6"], "rationale": "CI 挂载依赖两侧守卫就位" },
    { "wave": 6, "tasks": ["7"], "rationale": "浏览器 + DB 实测依赖全链完成" }
  ]
}
```

## Tasks

- [x] 1. 逐 sheet 精读 H2 源 xlsx，确权两级表头与固定行
  - openpyxl 读 `backend/wp_templates/H/H2 在建工程.xlsx` 的两张披露 sheet，记录：上市 6 表 / 国企 4 表的表名、两级表头（期末/上年年末|期初 各含 账面余额/减值准备/账面净值|账面价值）、单级表列、固定行（工程物资：专用材料/专用设备/工器具/工程物资减值准备）。
  - _Requirements: 1.1, 1.2, 2.1_

- [x] 2. 附注模板结构对齐幂等脚本 `fix_note_h2_construction_structure.py`
  - 用 `_note_structure_kit` 的 `two_period_columns`/`flat_columns`/`rule`/`run_section`/`build_cli`。
  - listed §五、23：summary(flat 3) / detail(两级 7，去 header_label) / projectMovement(flat 9) / projectCont(flat 5) / impairment(flat 5) / 「项  目」改名「工程物资」(flat 3)；`drops` 处理迁移残留。
  - soe §八、23：summary(两级 7) / （1）在建工程情况(两级 7) / （2）projectMovement(flat 13) / （3）impairment(flat 3)。
  - 每表补 `guidance`（源模板红字 / 15 号文 / 勾稽提示，不自造）。
  - `--dry-run` 预览、正式应用、`--check` 幂等验证（0 欠账）。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 3.1, 3.2, 3.4, 5.2_

- [x] 3. 后端结构守卫 `test_note_h2_construction_structure.py`
  - `--check` 无欠账 / 表数表名序 / 两级分组自洽 / flat 表态 / columns key 与前端一致 / 无「项  目」。
  - openpyxl 直读源 xlsx tab 名与关键两级表头（账面余额/减值准备/账面净值|账面价值）交叉比对。
  - 反向自检：validate 能抓出「缺 columns」「残留 header_label」「项  目 未清」。
  - _Requirements: 4.4, 2.1, 2.2_

- [x] 4. 前端映射两级列定义 + materials 改名（`h2NoteSectionMap.ts` / `buildH2SyncPayload`）
  - `H2_LISTED_SUBTABLE.materials`「项  目」→「工程物资」。
  - detail(上市) / summary + 情况(国企) 用 `ColumnDef.group` 两级列定义，叶子 key 与模板一致（`end_book`/`end_impairment`/`end_net`|`end_value`/`prior_*`）。
  - `buildH2SyncPayload` 行对象改用叶子 key；`_removed_table_keys` 含「项  目」。
  - _Requirements: 4.1, 4.2, 2.3, 3.3_

- [x] 5. 前端契约守卫 `h2NoteSubtableContract.spec.ts`
  - 复用 `_disclosureSubtableContract.helper` P1~P6 + H2 专属：两级分组、materials 改名、无「项  目」残留、含反向自检。
  - _Requirements: 4.3_

- [x] 6. CI 挂载 `note-h2-structure` job（governance-checks.yml）
  - 跑 `fix_note_h2_construction_structure.py --check` + 两侧守卫测试。
  - _Requirements: 4.4_

- [x] 7. 浏览器 + 只读 DB 实测（chrome-devtools + postgres）
  - 国企披露 Tab 渲染两级表头（期末余额/期初余额 → 账面余额/减值准备/账面价值），无 Vite 错误。
  - 「同步到附注」推送成功：§八、23 `last_sync_at` 前移、`last_sync_wp_id` = H2 底稿、4 张子表（在建工程/（1）在建工程情况/（2）重要在建工程项目本期变动情况/（3）本期计提在建工程减值准备情况）、**无「项  目」孤儿表**。
  - `project_sub_tables` 读时投影实证：在建工程 / （1）在建工程情况 得 `_column_groups=[{期末余额,1,3},{期初余额,4,3}]`（两级），减值准备表 `[]`（单级）。
  - 项目 `2aa00f57`（soe）；空底稿同步产出空表骨架（非造假值），note 由 unsynced-seed 转 synced-empty，属正常状态转换。
  - _Requirements: 5.4_

## Notes

- H1 已于本会话直接修复（非 spec，见 memory）；H3–H10 各自另立 spec，沿用本 spec 范式。
- 不改 `_h2_construction_in_progress.py` 四表取数与灰度默认值。
- 单级表列 key 以既有 `buildH2SyncPayload` 为真源（columns-coverage 已验证），禁反向改载荷键。
