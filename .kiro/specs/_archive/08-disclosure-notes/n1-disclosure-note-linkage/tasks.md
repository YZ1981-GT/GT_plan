# Implementation Plan

## Overview

5 波、11 个任务。Wave 0 先核实外部事实（DB 真实 sheet 名、模板表名/列头、N3 是否已推送同章节），Wave 1 落纯函数载荷层 + 单测，Wave 2 接组件按钮（推送 + 反向跳转），Wave 3 接正向跳转与定向刷新，Wave 4 守卫与零回归门。每波结束跑 `get_diagnostics` + 前端 `curl.exe` Vite transform 200 + 相关 vitest。

**执行结果（2026-07-26）**：全部任务完成（含 5.3* live round-trip）。关键数据：前端 288 测试全绿（N1 全套 162 + n1NoteSectionMap 26 + 正向 59 + 反向 36 + useNoteRefresh 5），后端 63 测试全绿，覆盖率守卫 `--strict` 48/48 通过，live round-trip 对真实项目 0ec33ac9/2025/五、30 备份→sync→断言→恢复 `RESTORED_IDENTICAL=True`（零污染）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "parallel": true },
    { "wave": 1, "tasks": ["2.1", "2.2"], "parallel": false },
    { "wave": 2, "tasks": ["3.1", "3.2"], "parallel": false },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3"], "parallel": true },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3"], "parallel": false }
  ]
}
```

## Tasks

- [x] 1.1 核实外部事实（DB + 模板 + N3 现状）
  - postgres 实测 `workpaper_sheet_classification`（wp_code=N1）：披露 sheet 真实名为全角括号 `附注披露信息（上市公司）` / `附注披露信息（国企）`
  - 脚本 dump 模板确认：listed 五、30（section_title「递延所得税资产与递延所得税负债」）/ soe 八、31 各 4 张子表；**soe 抵销后净额表仅 3 列（项目/期末/期初），listed 为 5 列（含互抵金额）→ 两变体列结构本质不同**；soe 表 3 名为「未确认递延所得税资产明细」
  - grep 确认 N3 目录零 `sync-from-workpaper` 调用 → 方案 A 所有权可直接落地
  - _Requirements: 1.1, 2.3, 3.1, 5.2_

- [x] 1.2 零回归基线
  - 基线：N1 前端 162 测试、后端 `test_n1_*` 45 测试、正/反向跳转 spec、覆盖率守卫 `--strict` 全绿
  - _Requirements: 8.2, 8.4_

- [x] 2.1 新建 `composables/n1NoteSectionMap.ts`
  - `N1_NOTE_SECTION` / `N1_DISCLOSURE_SHEET_NAME` / `N1_SUB_TABLE_KEYS` / `N1_GROUP_LABELS`（逐字取模板）
  - `buildN1SyncPayload(variant, snapshot, ctx)` 纯函数：四张子表 + `columns`（键集合与 `sub_table_data` 相同）+ `_note_texts`（空则不写）+ `current_standard` + `year`
  - `sumNullable` 可空求和（全 null → null，不塌成 0）；负债段/互抵缺失 `null`
  - 亏损到期按 `expiryYear` 聚合 + 合计 + 备注合并
  - _Requirements: 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.4, 4.1, 4.2, 9.1_

- [x] 2.2 载荷纯函数单测 `n1NoteSectionMap.spec.ts`（26 测试）
  - Property 1（章节号从 `note_template_variant_matrix.json` 读取比对）、2（键一致 + 行字段均在 columns 声明内）、3（columns label 逐字对齐模板 `tables[].headers`，含 soe 3 列 vs listed 5 列断言）、4、5、9、10、11
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 3.1 披露组件接「同步到附注」
  - `N1TabDisclosureListed.vue` / `N1TabDisclosureSoe.vue`：`buildSnapshot()` + `syncToDisclosureNotes()`（`http.post` 读 `resp.data`，按 `created` 区分「新建/更新」提示，`ERR_CANCELED` 静默，失败明确报错）
  - 负债段取 `crossSheet.n1ToN3Correspondence.liabilityPart`，缺失时提示「负债段暂无数据，待 N3 编制后重新同步」
  - `syncYear` = props.year → `useAuditContext().year` → 当前年（不依赖后端默认自然年）
  - listed 侧把内联 emit 收敛为 `_emitNoteUpdated`（与 soe 一致），同步成功后 emit（携 `accountCode:'1811'` + `sectionIds`）
  - _Requirements: 2.1, 2.6, 2.7, 3.3, 3.4, 4.1, 4.4_

- [x] 3.2 披露组件接「↩ 跳转回附注」
  - `el-dropdown split-button`：主按钮当前变体，下拉可切另一变体；`projectId` 缺失时提示
  - `DISCLOSURE_NOTE_SECTION_MAP` 新增 `N1: { listed: '五、30', soe: '八、31' }`
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 4.1 正向跳转加 N1 分支
  - `noteDisclosureJump.ts`：`isN1DeferredTaxNoteSection`（精确 `===`）+ `N1_DISCLOSURE_SHEET_LISTED/SOE` + 分支置于 E1 之前（通用回退之前）+ `wpCode` union 加 `'N1'` + N3 备选入口注释扩展位
  - `DisclosureEditor.vue` 族标签映射加 `N1: '递延所得税资产'`
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 4.2 跳转契约测试
  - 正向 +5 用例：五、30/八、31 命中 N1；五、3/八、3/五、31/八、32/五、300 不命中；通用 sheet 名不抢占；不抢占 G1(五、3)/I5(五、31/八、32)
  - 反向 +3 用例：N1 条目 + year 参数 + 与 `n1NoteSectionMap.N1_NOTE_SECTION` 一致；交叉守卫 checks 加 `['N1', isN1DeferredTaxNoteSection]`
  - _Requirements: 1.4, 5.3, 6.4_

- [x] 4.3 附注定向刷新登记 N1
  - `useNoteRefresh.ts`：`isN1DeferredTax`（accountCode `1811` + `isN1DeferredTaxNoteSection(current)`）纳入刷新条件（复用正向谓词单一真源，fail-open 不变）
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 5.1 覆盖率守卫登记
  - `check_disclosure_columns_coverage.py` 的 `COLUMN_BUILDERS` 加 `buildN1SyncPayload`；`--strict` 48 调用点全覆盖、0 未覆盖
  - _Requirements: 8.1_

- [x] 5.2 模板对齐守卫 + 零回归门
  - 模板对齐守卫内置于 `n1NoteSectionMap.spec.ts`（直接读 `note_template_{listed,soe}.json` 与 `note_template_variant_matrix.json` 比对，模板改动即失败）
  - 零回归：前端 288 测试、后端 63 测试（含 `test_wp_disclosure_sync`）、覆盖率守卫全绿；7 个改动前端文件 Vite transform 全 200
  - _Requirements: 8.2, 8.3, 8.4_

- [x]* 5.3 live round-trip（真实项目 0ec33ac9 / 2025 / 五、30）
  - 备份受影响 12 列 → HTTP sync（200，`rows_synced=7`、`texts_synced=1`、`created=false` 命中既有 note）→ `GET /api/disclosure-notes/{pid}/{year}/{section}` 断言投影 `_tables`（2 张表、headers `['项目','期末余额','上年年末余额']`、资产行 `[150000,100000]`、**负债小计 `[null,null]` 且 is_total**、`text_content` 含探针）→ 精确恢复 + `RESTORED_IDENTICAL=True`
  - 临时脚本跑完即删，真实项目零污染
  - _Requirements: 2.1, 2.6, 9.3_

## Notes

- **共用章节铁律**：N3（递延所得税负债）**不得**推送 `未经抵销的递延所得税资产和递延所得税负债` 与 `以抵销后净额列示的递延所得税资产或负债` 两张子表（会整表覆盖 N1 数据）；N3 只能发布跨底稿键供 N1 取用。若将来确需双向推送，须先按 design Decision 1 方案 B 引入 `sub_table_merge_mode`（独立变更 + 全量回归）。
- **不改后端**：`sync_from_workpaper` / 投影器 / 附注引擎均未改动；`year` 由前端显式传（后端 `_resolve_target_year` 只作兜底）。
- **两变体列结构差异**（实现期发现，已写入设计与测试）：soe 抵销后净额表 3 列 vs listed 5 列，禁按 variant 只换 label 硬套。
- 全部改动**未 commit**；未做浏览器 Playwright（live HTTP round-trip 已覆盖 sync→投影→文本→恢复全链）。
