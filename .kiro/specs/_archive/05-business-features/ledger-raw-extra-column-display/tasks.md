# Implementation Plan

## Overview

让 `raw_extra` 业务额外字段在凭证/序时账查询时透出（过滤 `_` 前缀系统标记）并在前端明细表格动态显示，additive 零回归。后端单一 helper + 6 方法接入 + select 补列；前端纯函数 `buildExtraColumns` + 明细表格动态列。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "description": "后端 helper + 纯函数单测（安全网）" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "description": "6 方法补 select raw_extra + 接入 helper + 集成/零回归测试" },
    { "wave": 2, "tasks": ["3.1", "3.2"], "description": "前端 buildExtraColumns 纯函数 + vitest（可与 wave0/1 并行）" },
    { "wave": 3, "tasks": ["4.1"], "description": "LedgerPenetration.vue 明细表格接入动态列" },
    { "wave": 4, "tasks": ["5.1", "5.2"], "description": "零回归门 + 全量回归；Playwright 实测（可选）" },
    { "wave": 5, "tasks": ["6.1"], "description": "可选：export-ledger Excel 同步额外列" },
    { "wave": 6, "tasks": ["7.1", "7.2"], "description": "复盘收尾 P0+P1：辅助明细账动态列 + 修复复制 [object Object]" },
    { "wave": 7, "tasks": ["8.1", "8.2", "8.3"], "description": "P2 增强：列显隐⚙ + 辅助明细/辅助余额 Excel 额外列 + 额外列视觉区分/非标量值防御" }
  ]
}
```

## Tasks

- [x] 1. 后端 helper 与安全网
- [x] 1.1 新增 `_attach_extra_fields` 模块级纯函数
  - 在 `backend/app/services/ledger_penetration_service.py` 顶部（其它模块级 helper 附近）新增 `_SYSTEM_KEY_PREFIX="_"` 与 `_attach_extra_fields(rows)`：每行 `pop("raw_extra")` → 非 `_` 前缀键构建 `extra_fields`（保序）→ 移除 raw_extra 键；raw_extra 为 None/非 dict → `extra_fields={}`；就地修改返回同列表
  - _Requirements: 1.1, 1.5, 2.1, 2.2, 4.1_
- [x] 1.2 helper 纯函数单测
  - 新建 `backend/tests/test_ledger_extra_fields.py`：覆盖 Property 1（`_` 过滤）/2（保序透出）/3（None·空 dict·非 dict·仅系统键 → `{}`）/4（移除 raw_extra 键）/5（既有固定字段不变）/7（同输入同输出）
  - _Requirements: 6.1, 2.1, 1.5, 5.1_

- [x] 2. 6 个查询方法接入
- [x] 2.1 补 select raw_extra + 接入 helper
  - 6 方法各在 `sa.select(...)` 补 `tbl.c.raw_extra`（`get_ledger_entries_cursor` 在 `ledger_sq` subquery 补作 passthrough；`get_aux_ledger_entries_cursor` 在 `stmt` 补），`items`/返回列表构造后调 `_attach_extra_fields(...)`；游标方法在 `items = rows[:limit]` 切片后调用，`next_cursor`/`has_more` 逻辑不变
  - 方法：`get_all_ledger_entries` / `get_ledger_entries` / `get_ledger_entries_cursor` / `get_voucher_entries` / `get_aux_ledger_entries` / `get_aux_ledger_entries_cursor`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.2, 5.1_
- [x] 2.2 端点集成 + 零回归测试
  - 对含 raw_extra 的 tb_ledger 行（真实 PG16 或既有 fixture）验证：序时账明细/凭证/cursor 返回 `extra_fields` 且过滤 `_` 前缀；响应不含原始 `raw_extra` 键；**既有固定字段集合与取值不变（零回归锚点）**；游标 `next_cursor` 不受影响
  - _Requirements: 1.1-1.5, 2.1, 5.1, 5.3, 5.4, 6.1_

- [x] 3. 前端纯函数
- [x] 3.1 新增 `buildExtraColumns` 纯函数
  - 在 `LedgerPenetration.vue` 内（或就近 `.ts` utils，便于 vitest 单测）导出 `buildExtraColumns(items): string[]`：遍历 items 的 `extra_fields` 键，Set 去重 + 数组保首次出现序，全空返 `[]`
  - _Requirements: 3.1, 3.3_
- [x] 3.2 `buildExtraColumns` vitest
  - 新建 `buildExtraColumns.spec.ts`：覆盖 Property 6（并集/保序/去重/空 items→[]/部分行无 extra_fields）
  - _Requirements: 6.1, 3.1, 3.3_

- [x] 4. 前端动态列渲染
- [x] 4.1 `LedgerPenetration.vue` 明细表格接入动态列
  - `extraColumns = computed(() => buildExtraColumns(<当前明细 items>))`；序时账明细表格 + 凭证明细（穿透第三层）表格在固定列后 `v-for="k in extraColumns"` 追加 `el-table-column`（`:prop="\`extra_fields.${k}\`"`、`:label="k"`、`min-width`、`show-overflow-tooltip`、缺失单元格 `?? ''`）；extraColumns 为空不追加列
  - 验证：get_diagnostics 全清 + `curl.exe` 该 vue Vite transform 200
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.3_
- [x] 4.2* 序时账虚拟滚动（el-table-v2）动态列完整化
  - 序时账 >1000 行走 `el-table-v2`（`ledgerVirtualColumns` computed 数组 + cellRenderer 机制），在固定列后按 `buildExtraColumns(ledgerItems)` 键并集追加额外列（文本 cellRenderer，缺失显空）；extraColumns 为空不追加。大账套序时账是常态，避免大数据量下额外列不显示的功能残缺
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 5. 收尾验证
- [x] 5.1 零回归门 + 全量回归
  - 跑后端 ledger_penetration / ledger_import 相关测试全绿；前端 vitest 全绿；确认既有消费者（C24 分录测试 `entries-all`、抽凭 `sample-voucher`、`expenseLedgerMonthlyPull`）不受影响（只读固定字段）
  - 结果（2026-07-25）：raw_extra 专属测试全绿 —— `test_ledger_extra_fields.py`(19) + `test_ledger_penetration_extra_fields.py` + `test_export_ledger_extra_fields.py` 合计 31 passed；前端 `buildExtraColumns.spec.ts` 7 passed。既有消费者只读固定字段不受影响（`_attach_extra_fields` 仅追加 `extra_fields` 键 + 移除 `raw_extra`，固定字段名/取值不变）。`test_ledger_penetration.py` 的 test_entries_api / test_aux_entries_api / test_paginated_sums 与 `test_phase8.py` ReportEngineCache 失败经 git stash 基线验证为**预存在**失败（去掉本特性代码后逐一相同失败），非本特性回归。
  - _Requirements: 5.1, 5.4, 6.1_
- [x] 5.2* Playwright 端到端实测
  - 导入含非关键列的账套（或用已含 raw_extra 数据的项目）→ 序时账明细/凭证明细表格显示额外列、系统标记不显示、无 raw_extra 时视觉不变、0 console error（需实例化项目 + 含 raw_extra 数据，条件不满足则诚实留待）
  - 结果（2026-07-25，重药控股安徽 0ec33ac9/2025，admin/admin123，EventSource 中和防 SSE 跳转）：**全部验证点通过**。①序时账明细（科目 2211.01.01.01，830 行标准 el-table）固定列（日期/凭证号/摘要/借方/贷方/余额）后追加额外列（状态/过账/审核人/过账人/是否自动/是否收付款/最后操作人/创建人.姓名/创建人.工号/凭证登账状态/是否关联回单/是否能点冲销工单/复核人/参考消息/同步状态/通用集团凭证编码/失败原因）；②科目 1221.98.01（1008 行 → **el-table-v2 虚拟滚动**，Task 4.2 cellRenderer 路径）同样固定列后追加额外列，样本行真实业务值（状态=已审核/复核人=李玲/…）；③穿透凭证 0006 → 凭证明细表格固定列（科目编号/科目名称/借方/贷方/摘要）后追加额外列，真实值（状态=已审核/复核人=马成杰/…）；④**系统标记 `_discarded_mappings` 全程不作为列出现**（DB 实证全部 348,802 行 raw_extra 均含该键 → 过滤有效非巧合缺失）；⑤空 raw_extra 科目（项目 df5b8403 / 1002.011，2100 行 el-table-v2）仅显示 6 个固定列、无追加列（视觉与改动前一致）；⑥0ec33ac9 全程 **0 console error**（含 preserved），df5b8403 唯一 1 个 404 是 `/api/projects/{id}` + `/wizard`（项目详情/向导端点，pre-existing，与本功能无关，`/ledger/*` 全 200）。**后端 HTTP round-trip 补证**：`GET /ledger/entries/2211.01.01.01` 每条含 `extra_fields`（12 业务键）、不含顶层 `raw_extra`、不含 `_discarded_mappings`；空 raw_extra 行 `extra_fields={}`。cursor 分页（`?limit=1000&cursor=...`）返 200，raw_extra passthrough 不影响游标。
  - _Requirements: 3.1, 3.3, 5.3_

- [x] 6. 可选增强
- [x] 6.1* export-ledger Excel 同步额外列
  - `export-ledger/{account_code}` 导出在固定列后追加 raw_extra 业务列（复用 `_attach_extra_fields` 口径）；不做则导出保持现状（不阻断主功能）
  - _Requirements: 1.1_

- [x] 7. 复盘收尾（P0+P1）
- [x] 7.1 辅助明细账表格动态列（P0 前后端一致）
  - 后端 `get_aux_ledger_entries`/`_cursor` 已透出 `extra_fields`，前端**辅助明细账表格**（`currentLevel === 'aux_ledger'`，`<el-table :data="auxLedgerDisplay">`，L605）当前无额外列 → 加 `auxLedgerExtraColumns = computed(() => buildExtraColumns(auxLedgerItems.value))` 并在固定列（余额）后 `v-for` 追加 `el-table-column`（与序时账明细 4.1 同款：`:label="k"`、cellRenderer/模板 `row.extra_fields?.[k] ?? ''`、min-width、show-overflow-tooltip；空则不追加）。消除后端透出、前端不显示的不一致
  - 结果（2026-07-25）：`auxLedgerExtraColumns` computed（紧邻 auxLedgerDisplay）+ aux 表 el-table-column v-for（与 4.1 同款）已加；get_diagnostics 全清 + Vite transform 200。
  - _Requirements: 1.4, 3.1, 3.2, 3.3_
- [x] 7.2 修复复制到剪贴板的 [object Object] 回归（P1）
  - `copySelectedRows`（L2170）/`copyCurrentVoucher`（L2189）的 `excludeKeys` 仍含已不存在的 `'raw_extra'` 且未排除 `'extra_fields'` → 复制时 `String(extra_fields对象)` = `[object Object]`。修复：excludeKeys 加 `'extra_fields'`（不再整对象输出），并把 `extra_fields` 的**业务键展开为额外的制表符列**（表头/数据行都追加，键并集用 `buildExtraColumns`；缺失写空）→ 复制到 Excel 得到正确的额外字段列而非 [object Object]
  - 结果（2026-07-25）：抽出纯函数 `buildClipboardTable(rows, excludeKeys)` 到 `ledgerExtraColumns.ts`（排除 `_` 前缀 + excludeKeys[含 raw_extra/extra_fields] + extra_fields 业务键展开为额外制表符列，键并集用 buildExtraColumns，缺失写空）；两复制函数统一调用（共用 `COPY_EXCLUDE_KEYS`）；`buildExtraColumns.spec.ts` 新增 5 个 buildClipboardTable 用例（展开列/缺失写空/内部字段排除/无 extra_fields/空 rows），共 12 tests passed。
  - _Requirements: 2.1, 3.3, 5.4_

- [x] 8. P2 增强
- [x] 8.1* 额外列显隐设置（⚙）
  - 额外列多（真实 17+ 列：状态/过账/审核人/过账人/凭证登账状态…）横向过宽 → 复用 memory 的 `useXDetailColumnPrefs` 范式：⚙ popover 勾选额外列显隐 + localStorage 持久化（key 如 `ledger-extra-column-prefs`）；序时账/凭证/辅助明细三处表格共用可见集合；默认全显
  - 结果（2026-07-25）：`hiddenExtraCols` ref<Set>（存隐藏键，新键默认显示）+ localStorage(`ledger-extra-column-prefs`) load/persist + `visibleExtra()`/`toggleExtraCol()`/`showAllExtraCols()`；三处 extraColumns computed 经 `visibleExtra` 过滤（序时账 el-table + el-table-v2 cellRenderer + 凭证 + 辅助明细共用同一集合）；各明细工具栏加「⚙ 额外列」el-popover（`XExtraAllKeys` 未过滤键列表 + el-checkbox 勾选 + 全显）。纯函数 `visibleExtraColumns(allKeys, prefs)` 导出 + vitest 覆盖。get_diagnostics 全清 + Vite 200 + 29 tests passed。
  - _Requirements: 3.4_
- [x] 8.2* 辅助明细/辅助余额 Excel 导出额外列
  - `export-ledger` 序时账 Excel 已加额外列（6.1*）；对齐 `exportAuxLedger`/`exportAuxBalance`（若存在对应后端导出端点）在固定列后追加 raw_extra 业务列，复用 `_attach_extra_fields` 口径；无对应端点则说明并跳过
  - 结论（2026-07-25，评估后诚实跳过，零改动）：**两者均跳过**。①**辅助明细账 tb_aux_ledger**（凭证行，raw_extra 含 20+ 真实业务字段：状态/过账/审核人/过账人/凭证登账状态/创建人.姓名/来源系统/到期日 等，`_discarded_mappings` 是唯一 `_` 前缀系统标记会被过滤）→ `ledger_penetration.py` **无对应 Excel 导出端点**（仅有查询端点 `GET /aux-entries/{account_code}`，导出端点只有 `export-ledger`/`export-balance`/`export-aux-balance`）→ 按验收「无对应端点则说明并跳过，不新建端点（非本 spec 目标）」。②**辅助余额 TbAuxBalance**（余额行，有导出端点 `export-aux-balance`）→ DB 实证 raw_extra 唯一键是系统标记 `_discarded_mappings`（504433/765305 行，`_attach_extra_fields` 全过滤），**零业务额外字段**；且 design 明确「余额类不在本 spec 范围」→ 追加额外列只会得到空并集列（与现状逐字节一致，无业务价值），诚实跳过。验证：`ast.parse` 通过；`test_export_ledger_extra_fields.py`+`test_ledger_extra_fields.py` 22 passed（零回归）。
  - _Requirements: 1.1, 1.4_
- [x] 8.3* 额外列视觉区分 + 非标量值防御
  - 额外列表头/单元格用不同底色或加"扩展"分组标识，与固定列区分；单元格值为 dict/list 时（真实数据多为标量，防御性）显示 `JSON.stringify` 或友好文本而非 `[object Object]`
  - 结果（2026-07-25）：纯函数 `fmtExtraCell(v)`（null/undefined→空串、object/array→JSON.stringify、标量→String）导出 + 三处 el-table-column 模板 + el-table-v2 cellRenderer 统一调用（不再 [object Object]）；额外列视觉区分 —— el-table-column `class-name="gt-ef-col"`/`label-class-name="gt-ef-col-hd"` + el-table-v2 `class:'gt-ef-vcell'`/`headerClass:'gt-ef-vcell-hd'` + scoped CSS（额外列表头/单元格浅底色区别固定列）；vitest 覆盖 fmtExtraCell。get_diagnostics 全清 + Vite 200 + 29 tests passed。
  - _Requirements: 3.2, 3.4_

## Notes

- 全程 additive 零回归：不改数据库表/列、不改导入写入、既有固定字段名/取值不变。
- 单一 helper `_attach_extra_fields` 是过滤/空值口径唯一真源（Req4.1），6 方法共用。
- 动态列作用域 = 当前结果集键并集（非全表预扫描），序时账全量拉取/凭证一次性全量 → 稳定不闪烁。
- 游标方法把 raw_extra 作 subquery passthrough 列，不参与 keyset 排序/游标。
- 只透出过滤后的 `extra_fields`，不透出整个 `raw_extra` JSONB（避免系统标记泄露 + 减小 payload）。
