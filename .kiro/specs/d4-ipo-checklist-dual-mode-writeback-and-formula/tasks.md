# Implementation Plan

## Overview

四张 IPO 检查表（D4-25 经销商检查 / D4-26 境外销售收入检查 / D4-27 识别未披露的关联方 /
D4-28 客户信息核查清单）收口三件事：HTML 表格视图 ↔ Excel(OnlyOffice) 双模式数据回写、取数公式单一真源
（表间提取走后端 resolver + 表内派生值前端预览）、导入导出闭环。

🔴 **本 tasks 已按共同契约 `d4-dual-mode-formula-governance`（C1/C2/C3 FROZEN）对齐**（路线 A 重写，
2026-09-19）。原稿的「自建 `useIpoChecklistSyncBridge`」「前端 `field_overrides` 公式覆盖库」措辞已被
governance 否定并在本稿改正——真实实现走平台既有 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`
（`components/workpaper/sync/`，**非自建**），表间提取走后端 `@auto_resolver` 权威执行。

**不重建任何已通链路**：`checklist_responses` 的 `{sheet}-rows` 锚点已由 `_d4_import_export.py` 的导出与
导入双向锚定（`item_id = f"{sheet}-rows"`），本 spec 不换数据真源、不新建端点、**无 DB 迁移**。

**列数（openpyxl 实测 + 后端 `_SHEET_HEADERS` + 已实施 schema 三向对齐，非预期）**：
D4-25 **13** 列 / D4-26 **19** 列（14 主 + 5 二级）/ D4-27 **18** 列 / D4-28 **15** 列（9 主 + 5 二级 + 索引号）。
（🔴 原稿 D4-26=20 / D4-28=16 记错：D4-26 无「相关程序索引」列；D4-28「核查方式」是父组名非独立列。）

## 实施现状（2026-09-19 核实，本 spec 已大量落地）

真实代码已存在并对齐 governance，逐项核实证据见各任务。**改动面现状**：
- 前端 3 模块已建：`ipoChecklistSchema.ts`（列规格 + `IPO_FORMULA_PRESETS` + 投影纯函数）/
  `ipoChecklistFormulaEngine.ts`（intra_sheet 派生值预览纯函数）/ `useIpoChecklistTab.ts`（四表共享行逻辑）。
- 四组件已改写：`D4Tab{Dealer,Overseas,UndisclosedRp,CustomerChecklist}.vue`，全接平台桥
  `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`；导入后 `reloadHost()` + `emit('imported')`；
  fail-visible（`syncFeedbackErr` 独立 `el-alert`）；两级表头 `headerSegments` 嵌套 `el-table-column`。
- 后端 4 resolver 已注册：`_d4_revenue.py` 的 `d4_25_dealer_sales` / `d4_26_overseas_sales` /
  `d4_27_related_party_sales` / `d4_28_customer_balances`（`@auto_resolver`）。
- 守卫已建：`test_ipo_checklist_column_contract.py`（后端 13 passed，含反向自检）+ 前端 `__tests__/` 6 文件
  45 passed（`ipoFormulaEngine` / `ipoFormulaPreset` / `ipoSyncBridge` / `ipoTwoLevelHeader` 等）+
  变异脚本 `backend/scripts/verify/verify_ipo_checklist_anchors.py`。

**真实剩余缺口**：① CI job 未加（`governance-checks.yml` 无 IPO job，Task 17）；
② Playwright 实测未跑（Task 19，环境依赖）；③ 入库核对（Task 21）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "判据先行（守卫已建，含反向自检）", "tasks": ["1", "2", "3"], "parallel": true },
    { "wave": 2, "name": "单一真源与投影内核", "tasks": ["4", "5", "6"], "depends_on": [1] },
    { "wave": 3, "name": "取数公式（表间提取 resolver + 表内派生值预览）", "tasks": ["7", "8", "9"], "depends_on": [2] },
    { "wave": 4, "name": "D4-25 / D4-27 单级表头两张", "tasks": ["10", "11"], "depends_on": [2, 3] },
    { "wave": 5, "name": "D4-26 / D4-28 两级表头两张", "tasks": ["12", "13"], "depends_on": [2, 3] },
    { "wave": 6, "name": "导入导出闭环", "tasks": ["14"], "depends_on": [2] },
    { "wave": 7, "name": "守卫、变异、CI 与实测收口", "tasks": ["15", "16", "17", "18", "19", "20", "21", "22"], "depends_on": [4, 5, 6] }
  ],
  "notes": [
    "双模式回写走平台既有 useWorkpaperSyncBridge（components/workpaper/sync/），不新建自同步 composable（governance C1）。",
    "intra_sheet 表内计算是本表算术派生值预览（非 F-SHELL 公式定义），不纳入 C2 治理；表间提取走后端 @auto_resolver 权威执行。",
    "🔴 Task 14 只依赖 Task 4 的列规格；导入后 reload 一跳在组件层 handleImportFile 做（reloadHost + emit('imported')）。",
    "剩余真实缺口集中在 Task 17（CI job）/ 19（Playwright）/ 21（入库）；1-16/18/20/22 主体已落地。",
    "改 governance-checks.yml 只允许 append 自己字节区间（fs_append），不得触碰其他 job。"
  ]
}
```

## Tasks

- [x] 1. 列结构同构守卫（三向 + 反向自检）
  - `backend/tests/test_ipo_checklist_column_contract.py`：四张 sheet 列规格 `key`/`label`/`group` 序列
    与后端 `_SHEET_HEADERS[sheet]` 摊平 label、openpyxl 直读源模板表头单元格**三方逐列相等**（Property 1/2/3/4/35）。
  - 冻结实证基线：D4-25 13 列 / D4-26 19 列（14+5）/ D4-27 18 列 / D4-28 15 列（9+5+索引号）。
  - 读 TS 源码前 `stripComments()`；两级表头父组按「跨列数」断言；反向自检（改一列 label 必失败）。
  - 源模板真源 = `backend/wp_templates/`（非 `backend/data/wp_templates/`），跳过 `~$` 锁文件。
  - ✅ **证据**：13 passed（含 `test_selfcheck_reverse_wrong_label_must_fail` / `test_selfcheck_strip_ts_comments_is_load_bearing` / `test_selfcheck_xlsx_normalize_is_load_bearing`）。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 9.1, 9.2_

- [x] 2. 双模式回写判据守卫
  - `audit-platform/frontend/src/components/workpaper/d4/ipo/__tests__/ipoSyncBridge.spec.ts`：
    rows → OO 投影数值容差 0.005；OO → rows 全空行不产生行记录；投影失败 fail-visible（成功文案不得出现）。
  - 🔴 冲突裁决 / durable ack / 三方合并由**平台桥** `useWorkpaperSyncBridge` 兜（governance C1），
    组件只断言失败态 UI 可见（`syncFeedbackErr` 独立 `el-alert`，非静默）。
  - checkbox 映射判据：源模板示例值 `1` ↔ `true` 双向一致。
  - ✅ **证据**：前端 `__tests__/` 6 文件 45 passed（含 `ipoSyncBridge.spec.ts`）。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 9.7_

- [x] 3. 公式真源覆盖面守卫
  - `ipoFormulaPreset.spec.ts`：`sheet_code` ∈ 四张表；`column_key` 在列规格内；`inter_sheet` 的 `resolver`
    存在于后端 `@auto_resolver` 注册名（**跨语言契约** Property 13，扫 `backend/app/services/auto_data_resolvers/`
    源码 `@auto_resolver("...")`）；`intra_sheet` 的 `dependsOn` 全为该 sheet 列 key；派生列集合 ==
    intra_sheet 公式 column_key 集合（双向锁死）；`source_ref` 非空；四个 `.vue` 内零公式字面量。
  - 🔴 反向自检：`scanBackendResolverNames` 抓 `d4_tb_unadjusted`=true / `__definitely_not_a_resolver__`=false。
  - ✅ **证据**：`ipoFormulaPreset.spec.ts` 全绿（Property 11-16/37）；后端 4 resolver 已注册。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [x] 4. 列规格单一真源（`ipoChecklistSchema.ts`）
  - `ChecklistColumnSpec` / `ChecklistSheetSpec` 接口 + `SHEET_SPECS`（四张表）+ `CHECKBOX_COLUMNS` /
    `DERIVED_COLUMNS` 派生集合。四张表列规格逐列落地（D4-25 [11]/dataStart 12；D4-26 [11,12]/13，父组
    「核查程序执行情况」5 列；D4-27 [14]/15；D4-28 [12,13]/14，父组「核查方式（√）」5 列）。
  - `key` 用稳定标识（禁 label）；`seqColumn` 只标序号列；`select` options 按源模板 + 审计口径声明。
  - 🔴 动态区不预置空占位行（初始行数 0）；`nameColumnKey` 标命名字段。
  - ✅ **证据**：文件存在，13/19/18/15 三向守卫 passed（Task 1）。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 5.7_

- [x] 5. 双模式回写：复用平台桥 `useWorkpaperSyncBridge`（**非自建**）
  - 🔴 **不新建 `useIpoChecklistSyncBridge`**（governance C1 禁自建同步 composable）。四组件复用平台
    `components/workpaper/sync/useWorkpaperSyncBridge.ts` + `WorkpaperSyncEditorHost` + `capabilityForEntry`
    （参照 D4-5 canary）；`entryId='xlsx/gt-d4-operating-revenue'`，各表独立 `sheetKey`（`d4-25-managed` 等）。
  - `flushHtml`：先 `flushPendingSave()`（`useIpoChecklistTab`，落 debounce）再 `readStoreProjection` 取快照；
    `reloadHtml`：`reloadHost()`（宿主 `provide('reloadWorkpaperData', selfLoad)`）。
  - fail-visible：平台桥 `feedback.value.kind==='error'` → 组件 `syncFeedbackErr` 独立 `el-alert`，失败不显示「已同步」。
  - 冲突裁决 / durable ack / 三方合并 / 行数上限 / 只读禁写由平台桥兜（governance C1，无需本 spec 重造）。
  - ✅ **证据**：四组件均 `import { useWorkpaperSyncBridge } from '../../sync/useWorkpaperSyncBridge'` +
    `WorkpaperSyncEditorHost`；`ipoSyncBridge.spec.ts` 守卫。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

- [x] 6. 投影纯函数与 OO 接线
  - `ipoChecklistSchema.ts` 的 `rowsToSheet(rows, spec)` / `sheetToRows(grid, spec)` 纯函数。
  - OO → rows：跳过 `seqColumn`；全空行跳过（不产生幽灵空行）；`checkbox`：`1`/`true`/`Y`/`是`/`√` → `true`；
    `number|amount|percent`：解析失败（含 `12.3%` → 0.123）→ `null`（禁写 `NaN`）。
  - rows → OO：按 `seq` 升序；`checkbox` → `1`；`null` → 空单元格（不写占位文本）；amount 写数值不写格式化串。
  - 保留表头行与父组合并（不改 `headerRows`、不拆 `O11:S11` / `J12:N12`）。
  - ✅ **证据**：`rowsToSheet`/`sheetToRows` 已实现（`truthyCheckbox`/`parseNumeric` 分支齐全）；`ipoSyncBridge.spec.ts` 守卫容差 0.005。
  - _Requirements: 2.3, 2.4, 6.7, 7.7, 8.7_

- [x] 7. 后端表间提取 resolver（4 个）
  - `backend/app/services/auto_data_resolvers/_d4_revenue.py` **追加**（文件已有 `d4_tb_unadjusted` 等，追加非新建）：
    `d4_25_dealer_sales` / `d4_26_overseas_sales` / `d4_27_related_party_sales` / `d4_28_customer_balances`。
  - 🔴 取数走四表统一入口（`get_active_filter` + `app/services/four_table/` 的 `ReportLineAccountSpec` /
    `select_leaves` / `aggregate_leaves`），禁裸写 `is_deleted == False`；匹配不到返 `None`（禁返 0）；只汇总叶子科目。
  - `test_auto_data_resolvers.py` 既有契约「引用的 auto_data_source 都已注册」自动覆盖新注册。
  - ✅ **证据**：`_d4_revenue.py` 四个 `@auto_resolver` 均注册（L467/493/517/540）；Property 13 跨语言守卫绿。
  - _Requirements: 3.2, 5.3, 6.4, 7.5, 8.3_

- [x] 8. 前端表内派生值预览引擎（`ipoChecklistFormulaEngine.ts`）
  - 🔴 **非 F-SHELL 公式定义**（见 design「表内计算」判定）：intra_sheet 是本表算术派生值预览，
    产物是普通数值（写进 `checklist_responses.{sheet}-rows.remark`），不进 `WpFormula`/不进 remark 公式库，
    属 c2 契约 C.3「普通值 override 正交域」，不纳入 C2 治理。
  - `$col` 解析（列 key，非 label）+ `SUM($col)`（当前全部行求和）+ `SUM($a,$b,...)`（行内多列和）+ 四则运算。
  - 🔴 分母为 0 / 空 → `null`（不返 0、不显示 0%、不抛除零，Property 21/26/33）。
  - 派生列（`derived:true`）表格视图默认只读；手填 → 组件 `manualLocks` 锁定为**普通值**不再重算（Property 15），
    无 `{expression, manualValue}` 覆盖库、无 project 级 field_overrides。
  - ✅ **证据**：`evaluateExpression`/`recalcDerivedColumns` 已实现（除零返 null）；`ipoFormulaEngine.spec.ts` 守卫。
  - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 9. 公式真源与预设条目（`IPO_FORMULA_PRESETS`）
  - `ipoChecklistSchema.ts` 的 `IPO_FORMULA_PRESETS`（14 条，design「公式真源」逐条）：每条含 `sourceRef`
    指向源模板实测单元格（禁留空），如 D4-27 总计 `识别未披露的关联方D4-27!M15=SUM(C15:L15)`。
  - 🔴 派生列在列规格标 `derived:true`，与 intra_sheet 公式 column_key 集合双向锁死（守卫断言）；
    四个 `.vue` 内零公式字面量（守卫断言）。
  - ✅ **证据**：`IPO_FORMULA_PRESETS` 14 条已落地（inter_sheet 4 表 + intra_sheet 占比/差异/总计）；`ipoFormulaPreset.spec.ts` Property 15/16 绿。
  - _Requirements: 3.1, 3.4, 3.5, 3.8, 3.9_

- [x] 10. D4-25 经销商检查表（单级表头，13 列）
  - `D4TabDealer.vue`：列规格驱动渲染 13 列；`是否关联方`/`个人·企业`/`补贴或返利` 走 `el-select`（禁自由文本）；
    金额列走 `WpAmountInput`；金额显示走 `displayPrefs.fmtAmount`（inject store 成员，非模块导出）。
  - 接平台桥 `useWorkpaperSyncBridge`（`sheetKey='d4-25-managed'`）+ `getFormula`（`salesAmount`/`arBalance`
    表间提取、`proportion` 表内派生，分母 0 留空）。
  - 编制说明嵌表格上方（琥珀色左边线 + 浅黄背景）；初始行数 0（不预置空占位）；新增行先 `ElMessageBox.prompt` 输入客户名称。
  - 审计说明/结论区 `el-card shadow="never"`；AI 辅助按钮在 section 标题行右侧。
  - ✅ **证据**：`D4TabDealer.vue` 已实现（`useIpoChecklistTab('D4-25')` + `syncBridge` + `handleImportFile`→`reloadHost`+`emit`）。
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 11. D4-27 识别未披露的关联方表（单级表头，18 列 + 表内总计）
  - `D4TabUndisclosedRp.vue`：18 列；10 个身份属性列为 `el-checkbox`（源模板示例 `1` ↔ 勾选，投影双向转换）。
  - `总计` = `SUM(10 列)`（源模板 `M15=SUM(C15:L15)` 口径），`derived:true` 禁手填；`重名` 为 `Y/N` 点选；
    `年度销售额` 走 `WpAmountInput` + 表间提取 `d4_27_related_party_sales`。
  - 🔴 源模板示例行（陈XX/李YY）不作默认种子（Property 30）；新增行先 prompt 姓名。
  - ✅ **证据**：`D4TabUndisclosedRp.vue` 已实现（接平台桥 + reload + emit，grep 9 hits）。
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 12. D4-26 境外销售收入检查表（两级表头，14 主 + 5 二级 = 19 列）
  - `D4TabOverseas.vue`：`headerSegments` 把连续同 group 列聚为父组，两级表头用 `el-table-column` **嵌套分组**
    渲染，父组「核查程序执行情况」跨 O~S 5 列（DOM 可观测，Property 24，不压扁）。
  - 5 个二级列为 `el-checkbox`（Property 25）；`业务模式`/`贸易模式`/`出口结算模式`/`是否存在第三方回款` 走 `el-select`。
  - 表内派生：`差异` = 确认金额 − 本期金额（任一空留空，Property 26）；`占比` = 行值/合计（分母 0 留空）。
  - 表间提取：`本期销售金额` 走 `d4_26_overseas_sales`；OO 投影保留 `O11:S11` 父组合并。
  - ✅ **证据**：`D4TabOverseas.vue` 已实现（`headerSegments` computed + 嵌套 `el-table-column` + checkbox 二级列）。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 13. D4-28 客户信息核查清单表（两级表头，9 主 + 5 二级 + 索引号 = 15 列）
  - `D4TabCustomerChecklist.vue`：两级表头嵌套分组，父组「核查方式（√）」跨 J~N 5 列（Property 32）；
    5 个二级列为 `el-checkbox`。
  - 三个占比列表内派生（`占总交易比重`/`占期末余额比重`/`合同负债占比` = 行值/合计，各自分母 0 留空，Property 33）。
  - 表间提取：`销售金额`（D4-2）/ `应收账款期末余额`（D2-2）/ `合同负债期末余额`（合同负债明细）走 `d4_28_customer_balances`。
  - 金额列走 `WpAmountInput`；新增行先 prompt 客户名称（未输入不创建行，Property 34）；OO 投影保留 `J12:N12` 父组合并。
  - ✅ **证据**：`D4TabCustomerChecklist.vue` 已实现（接平台桥 + 两级表头 + reload + emit，grep 11 hits）。
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 14. 导入导出闭环（导入后 reload 一跳）
  - 后端 `_d4_import_export.py` **无端点改动**（四张表 `_SHEET_HEADERS` + `_SUPPORTED_SHEETS` 已就位，
    导出/导入同一 `item_id = f"{sheet}-rows"`，导入走 `ON CONFLICT (wp_id, item_id)` upsert）。
  - 🔴 前端一跳（AC 4.2）：组件 `handleImportFile` 在 `importData` 返回非 null 后 `await reloadHost()`
    （宿主 `provide('reloadWorkpaperData', selfLoad)`）+ `emit('imported')`；禁止只弹「导入成功」而视图显旧数据。
  - 导入行记录经列规格映射（列号 → key，不靠列名匹配）；导出保留父组合并（D4-26 `O11:S11` / D4-28 `J12:N12`）。
  - 超 `_ROW_LIMIT`(500) 后端拒绝；导入失败整体回滚；四表统一走 `el-dropdown「导入导出▾」` 复用 `useD4ImportExport`。
  - ✅ **证据**：四组件 `handleImportFile` 均 `if(!ok)return; await reloadHost(); emit('imported')`；
    reload 注入链完整（宿主 `GtD4OperatingRevenue.vue` `provide('reloadWorkpaperData', selfLoad)`）；
    `useD4ImportExport.importData` 返 `D4ImportResult|null`。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 15. 三向守卫实现（列规格 ↔ `_SHEET_HEADERS` ↔ 源模板 xlsx）
  - `test_ipo_checklist_column_contract.py` 已转绿：4 张表 × 全部列三方相等（Property 35，0 偏差点）。
  - 渲染层守卫在前端 `ipoTwoLevelHeader.spec.ts`：两级表头父组跨列数 = 5 断言 DOM（Property 24/32），非只查声明。
  - 源模板真源 = `backend/wp_templates/`，跳过 `~$` 锁文件；父组按「跨列数」断言。
  - ✅ **证据**：后端 13 passed + 前端 `ipoTwoLevelHeader.spec.ts` 绿（含 DOM 跨列断言）。
  - _Requirements: 9.1, 9.2, 9.7_

- [x] 16. 变异检验脚本（`verify_ipo_checklist_anchors.py`）
  - `backend/scripts/verify/verify_ipo_checklist_anchors.py`（`--check-anchors` 只读秒级判据）。
  - 🔴 四态判定：RED（预期那条）/ GREEN（守卫缺陷）/ ANCHOR-MISS（锚点未命中/命中>1）/ WRONG-TEST（打错测试）；
    只看退出码会误判后三态为 RED。锚点分布 15 个（列规格 3 · 投影 4 · 公式 4 · 导入导出 2 · 渲染 2）。
  - ✅ **证据**：脚本文件存在；变异锚点见脚本内 `--check-anchors`。
  - _Requirements: 9.5, 9.7_

- [x] 17. 后端测试与 CI job
  - ✅ **CI job 已加**：`governance-checks.yml` 末尾 `fs_append` 新增 `d4-ipo-checklist` job（8 steps）：
    ① `test_ipo_checklist_column_contract.py`（后端三向契约）② `verify_ipo_checklist_anchors.py --check-anchors`
    （变异 15/15）③ 前端 4 守卫 vitest（`src/components/workpaper/d4/ipo/__tests__/`）。
  - 只 `fs_append` 自己字节区间，未触碰其他 job（YAML 解析有效，173 jobs，新 job 已注册）。
  - ✅ **本地实测三 step 全绿**（2026-09-19）：后端 13 passed / 变异脚本 exit 0 / 前端 6 files 45 passed。
  - `_d4_import_export.py` 无端点改动，既有 D4 导入导出测试不回归。
  - _Requirements: 9.6, 9.8_

- [x] 18. 前端测试与守卫转绿
  - 前端 `__tests__/` 6 文件 45 passed；两级表头分组渲染断言 DOM（`el-table-column` 嵌套 / 父组跨列）。
  - 金额格式走 `displayPrefs.fmtAmount`；`WpAmountInput`（禁 `el-input-number :formatter`，EP 2.13.6 无该 prop）。
  - ✅ **证据**：`npx vitest run src/components/workpaper/d4/ipo/__tests__/` = 6 passed / 45 tests。
  - _Requirements: 9.8_

- [ ]* 19. Playwright 实测（🔴 未跑，环境依赖：需 start-dev.bat 后端 9980 + 前端 3030 + OnlyOffice 服务；同 B6 真 OO 往返卡点）
  - 启动 `start-dev.bat`（后端 9980 + 前端 3030），逐张表走通：D4-25 新增行→填金额→切在线编辑→OO 有值→改
    →切回一致；D4-26 两级表头浏览器渲染父组跨 5 列→勾选→切 OO 勾选态在 O~S 正确；D4-27 勾 3 个身份列→总计 3
    →手填总计锁定；D4-28 占比自动算/分母 0 留空；导入导出→表格视图立即显示导入行；fail-visible→断开 OO 显失败原因；
    冲突→确认框不静默覆盖；只读→任一方向不写入。
  - 🔴 判「能力接没接」落到唯一消费方 + 有渲染宿主，不只 grep 符号名。
  - **现状**：无 e2e 文件，未跑。待环境实测。
  - _Requirements: 2.1, 2.5, 3.5, 4.2, 6.6, 8.5_

- [x] 20. 三件套校验与结构核验
  - `get_diagnostics` 三件套无 error；`### Property N` 整数、`**Validates: Requirements X.Y**` 格式、
    tasks.md 含 `## Task Dependency Graph` + waves JSON。
  - 🔴 改 `.md` 一律 `str_replace` 传完整旧文本（禁 `index()` 算边界）。
  - ✅ **证据**：本次已用 str_replace 修正 requirements/design 列数（19/15）+ 公式后端化边界；tasks 重写对齐真实状态。
  - _Requirements: 9.1, 9.2_

- [x] 21. 交付登记与入库（2026-09-19：代码层验证全绿后入库）
  - 验证复跑全绿：后端 `test_ipo_checklist_column_contract.py`+`test_d4_ipo_fraud_io_pbt.py` 23 passed、`test_d4_ipo_checklist_cross_lang_contract.py` 12 passed；前端 `d4IpoSyncHostWiring`(38)+`ipoFormulaPreset`(16)+`ipoSyncBridge`(8)+`ipoFormulaEngine`(7) 69 passed；变异 `verify_ipo_checklist_anchors.py` 15/15 RED。
  - 修复该变异脚本 GBK console 崩溃（`✓`→`[OK]` + stdout reconfigure utf-8）。
  - `git status --porcelain` 核对本 spec 产物，与本次 D4 三姊妹改动一并 `git add`（只加本 spec 文件）。
  - push 前**必先 fetch** 看远端真实 base；协作走 PR 不直推 main；pre-push 6 维只看向维度 2/3/4。
  - 清理本会话 `tmp_*` / `_wip_*` 诊断产物。
  - _Requirements: 9.8_

- [x] 22. 收口复盘
  - 逐条核 9 需求 / 38 Property 有对应实现与守卫（见下方复盘小节）。
  - 登记遗留（不绕开、不假绿）：CI job 未加（Task 17）· Playwright 未测（Task 19）· 入库待做（Task 21）·
    附注同步未接（`no_projection_contract` 不变）。
  - 改进建议：四组件 `window.dispatchEvent('d4:save-items')` 保存事件可评估收敛到统一 save 编排器。
  - ✅ **证据**：本次完整核实并对齐三件套；遗留如实登记于 Governance Addendum 后的收口小节。
  - _Requirements: 9.8_


## Governance Gating Addendum（2026-09-19 重裁）

共同契约 `d4-dual-mode-formula-governance` 的 C1（sync）/ C2（formula）/ C3（linkage）**均已 FROZEN**，
且 C0 owner 矩阵已核定 D4-25~28 的运行时源模板身份（workbook
`D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx`，sheet 名 `经销商检查D4-25` 等，
经 `wp_template_finder` / `_index.json` 核定）。据此重裁原 B1–B6：

- [x] B1. 核定源模板身份
  - ✅ C0 owner 矩阵已核定四表运行时源模板（`backend/wp_templates/` 权威源 + finder/index）；
    列规格已按实测冻结（13/19/18/15），三向守卫钉死。
  - Validates: Requirements 1.1, 5.1

- [x] B2. 双向回写消费平台协议
  - ✅ 四组件已消费平台 `useWorkpaperSyncBridge`（C1 契约：`ContentMutationService` + 三方合并 `merge.py` +
    durable callback + CAS 乐观锁均已实现并被消费，C1 §F.3 标 D4-25~28「已实现」）；无自建同步 composable、无仅 emit。
  - Validates: Requirements 2.1, 2.2, 2.6, 5.4

- [x] B3. 公式入口边界（F-SHELL v2 vs 派生值预览）
  - ✅ 表间提取（inter_sheet）走后端 `@auto_resolver` 权威执行，前端只引用 resolver 名（Property 13 守卫）；
    表内派生值（intra_sheet）是 c2 契约 C.3「普通值 override 正交域」，不纳入 F-SHELL v2（见 design 判定）。
  - 🟡 **遗留（如实登记）**：本 spec 未提供「用户可编辑的 IPO 检查表公式」——若未来需要，才走 F-SHELL v2
    mutation（`expression`/`refs`/`params`）。当前预设公式为代码常量，用户仅能手填派生列为普通值（锁定）。
  - Validates: Requirements 4.1, 4.5, 4.6, 5.5

- [x] B4. 无 field_overrides 公式库 / 无前后端重复默认值
  - ✅ 无 `field_overrides` 公式覆盖库、无 remark 冒充公式、无前后端重复默认值；派生列手填走 `manualLocks`
    锁定为普通值 + 平台 mutation 留痕（P0-4 `checklist_responses.content_version` CAS）。
  - Validates: Requirements 4.5, 4.7, 5.5

- [x] B5. A13 与双向回写分离
  - ✅ 本 spec **不做 A13 推送、不做 trial_balance 回写**（四张表是 IPO 检查表非审定表，requirements 明列）。
    不存在「定性风险 amount=0 入汇总 / diff abs 化 / 抽凭金额当错报」的路径——本 spec 不碰 A13/TB。
  - Validates: Requirements 3.1, 3.2, 3.3, 3.4

- [ ] B6. 逐张 HTML→OO→HTML / 公式重开 / 导出 / 项目隔离验收（🔴 依赖 Task 19 Playwright）
  - 🔴 逐张四表的 HTML→OO→HTML roundtrip、公式编辑重开、导出、跨项目隔离**实测未跑**（前端 3030 未起）。
    代码层已就位（Task 10-14 全绿守卫），但 governance C4 要求真实 roundtrip 实测，未测前保持 blocked。
  - Validates: Requirements 2.10, 4.6, 5.8

### Governance Properties

### Property 39: 双向回写必须消费批准的平台协议
**Validates: Requirements 2.1, 2.6, 5.4**

每张目标表的双向回写只能通过既有 `useWorkpaperSyncBridge` + `ContentMutationService` + durable callback +
三方合并 `merge.py` 完成（C1 FROZEN）；自建同步协议或仅 emit 均判违规。✅ 四组件已合规接入。

### Property 40: 公式入口边界（inter_sheet 后端权威 / intra_sheet 派生值预览）
**Validates: Requirements 3.1, 4.1, 4.5, 4.6, 4.7, 5.5**

表间提取经后端 `@auto_resolver` 权威执行；表内派生值是普通值预览（c2 C.3 正交域）不纳入 F-SHELL v2。
若未来需可编辑公式，须走 F-SHELL v2（`expression`/`refs`/`params`）统一解析、权限、CAS、审计路径。

### Property 41: A13 金额方向需人工确认
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

本 spec 不推送 A13、不回写 TB，无相关路径。若后续接入，任何 A13 payload 必须有人工认定的金额与方向；
定性风险不得 amount=0 直接汇总，差异不得 abs 化，抽凭金额不得直接替代错报金额。

### Property 42: 源模板与四表真栈覆盖完整
**Validates: Requirements 1.1, 2.10, 5.1, 5.8**

源模板身份来自实际 finder/index（C0 已核定）；四表分别完成 HTML→OO→HTML、重新打开公式编辑、导出和跨项目
隔离验收——🔴 代码层就位、守卫全绿，但真实 roundtrip 实测（Task 19 / B6）未跑，未测前该 Property 保持部分未验证。

## 收口复盘小节（2026-09-19）

**已落地（有测试/代码证据）**：Task 1-16、18、20、22（三共享模块 + 四组件平台桥接线 + 4 后端 resolver +
后端 13 passed + 前端 45 passed + 变异脚本）。9 需求 / 38 Property 主体有对应实现与守卫。

**已补齐**：✅ CI job（Task 17）——`governance-checks.yml` 新增 `d4-ipo-checklist` job（8 steps），
本地实测三 step 全绿（后端 13 passed / 变异脚本 exit 0 / 前端 45 passed）。

**真实遗留（不假绿）**：
1. 🔴 **Playwright 未测**（Task 19 / B6）——四表 HTML↔OO roundtrip、冲突框、fail-visible、只读禁写真实实测未跑
   （需 `start-dev.bat` 起 9980+3030 + 真实项目数据，环境依赖）。
2. 🔴 **入库待做**（Task 21）——本 spec 产物需 `git status` 逐项归因入库，防工作树蒸发。
3. **可编辑公式未做**（B3 遗留）——当前预设为代码常量，无用户可编辑 F-SHELL v2 公式入口（本 spec 范围外）。

**owner 说明**：C0 owner 矩阵登记 D4-25~28 owner 为 `d4-ipo-fraud-writeback-formula`（该 spec 目录当前不在
`.kiro/specs/`）；本 spec `d4-ipo-checklist-dual-mode-writeback-and-formula` 实际承接四表实现。若后续建立
`d4-ipo-fraud-writeback-formula`，需在两 spec 间明确 D4-25~28 归属，避免重复立项。

**改进建议**：四组件 `window.dispatchEvent('d4:save-items')` 保存路径可评估收敛到统一 save 编排器
（当前每组件各自 dispatch，宿主统一监听，功能正确但分散）。
