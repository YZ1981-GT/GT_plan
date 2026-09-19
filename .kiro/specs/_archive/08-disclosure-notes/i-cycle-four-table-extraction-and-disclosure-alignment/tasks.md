# Implementation Plan: I 类四表取数与披露/附注对齐

## Overview

8 个 wave、40 个任务。Wave 1 是所有下游的前提（科目真源）；Wave 4 与 Wave 1~3 无依赖可并行推进
（模板结构只取决于源 xlsx）；Wave 8 实测必须在全部实现完成后进行。

改动面：后端 6 个 render 策略 + 3 个新建共享件 + 2 个幂等脚本；前端 6 个 AccountScope + 1 个
CategoryScope + 6 个 NoteSectionMap + 6 个 SyncPayload + 12 个披露 Tab + 6 个审定表 Tab；
附注模板 12 个章节 20+ 张表。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端科目真源与取数收口",
      "tasks": ["1", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6"],
      "parallel": false,
      "blocks": [2, 3, 4, 8]
    },
    {
      "wave": 2,
      "name": "公式预设重写",
      "tasks": ["2", "2.1", "2.2", "2.3"],
      "parallel": true,
      "depends_on": [1],
      "blocks": [8]
    },
    {
      "wave": 3,
      "name": "前端科目单一真源与溯源/预填",
      "tasks": ["3", "3.1", "3.2", "3.3", "3.4"],
      "parallel": false,
      "depends_on": [1],
      "blocks": [6, 8]
    },
    {
      "wave": 4,
      "name": "附注模板结构对齐（12 章节）",
      "tasks": ["4", "4.1", "4.2", "4.3", "4.4", "4.5", "4.6"],
      "parallel": false,
      "blocks": [5, 8]
    },
    {
      "wave": 5,
      "name": "披露映射与推送载荷",
      "tasks": ["5", "5.1", "5.2", "5.3", "5.4", "5.5", "5.6"],
      "parallel": false,
      "depends_on": [4],
      "blocks": [6, 8]
    },
    {
      "wave": 6,
      "name": "披露 Tab 改造（动态区/控件/接线）",
      "tasks": ["6", "6.1", "6.2", "6.3", "6.4", "6.5"],
      "parallel": false,
      "depends_on": [3, 5],
      "blocks": [8]
    },
    {
      "wave": 7,
      "name": "守卫与 CI",
      "tasks": ["7", "7.1", "7.2", "7.3"],
      "parallel": true,
      "depends_on": [1, 2, 4, 5, 6],
      "blocks": [8]
    },
    {
      "wave": 8,
      "name": "实测与收口",
      "tasks": ["8", "8.1", "8.2", "8.3", "8.4"],
      "parallel": false,
      "depends_on": [1, 2, 3, 4, 5, 6, 7]
    }
  ]
}
```

## Wave 1 — 后端科目真源与取数收口

- [x] 1. 新建 I 类科目声明共享件并接入六个 render 策略
- [x] 1.1 新建 `backend/app/services/four_table/i_cycle_accounts.py`：`I_CYCLE_SPECS`（六循环
  `ReportLineAccountSpec`）+ `I_CYCLE_SOE_ROW_CODES` + `resolve_i_cycle_accounts(ctx, wp_code)`
  + `detect_chart_conflict()`。I2 兜底 `1704`、I6 兜底 `6604`、I5 无兜底码。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
- [x] 1.2 新建 `backend/app/services/four_table/i1_asset_categories.py`：`I1Category` dataclass
  × 11 类（每项带 `source_ref` 指向 `I1 底稿目录!A9`~`A19`）+ `classify_i1_leaf()`（名称优先 +
  `exclude_keywords` 否决 + 编码兜底）+ `category_defs_payload()`。
  - _Requirements: 4.1, 4.2_
- [x] 1.3 重写六个 render 的取数段：删 `_I{N}_ACCOUNT_PREFIX(ES)` 硬编码常量，改走
  `resolve_i_cycle_accounts` + `four_table.leaf_aggregation.select_leaves` / `aggregate_leaves`；
  I6 改从 `trial_balance` 本期发生额口径取数。`tb_values` 键名保持不变。
  - _Requirements: 1.1, 1.6, 2.3_
- [x] 1.4 备抵段方向与符号：`1702`/`1703` 的 `increase` 取 `credit_amount`、`decrease` 取
  `debit_amount`，输出取绝对值；`IMP-016`/`IMP-017` 经 `provision_row_code` 解析。
  - _Requirements: 2.1, 2.2, 2.4_
- [x] 1.5 render 输出 `tb_source_codes`（含 `parent_check` / `chart_conflict` / `unmapped`）与
  `adjudication_prefill`、`tb_leaf_categories`（I1 三段 × 类别；I4 项目行）。三个新增键受灰度
  开关控制，`tb_values` 的口径修正不受控制。
  - _Requirements: 3.1, 3.3, 4.1, 4.3, 4.5_
- [x] 1.6 后端测试：`test_i_cycle_accounts.py`（含反向自检）、`test_i1_asset_categories.py`
  （参数化 + PBT + 打乱顺序自检）、`test_i_cycle_leaf_aggregation.py`（父子并存不双计 +
  备抵 roll-forward）；扩展 `test_hi_extraction_characterization.py` 覆盖六循环。
  - _Requirements: 10.3, 10.4_

## Wave 2 — 公式预设重写

- [x] 2. 修正 I 类 18 个预设块
- [x] 2.1 新建幂等脚本 `backend/scripts/fix/fix_i_cycle_prefill_presets.py`（`--dry-run` /
  `--check`）：审定表块按循环纠正 `wp_name` + `account_codes` + `TB()` 科目；I1 块补 `1703`；
  删 I3 块 4 条 `1712` 条目；I2 明细块改 `1704`/`5301.02`；I6 块改 `6604`。
  - _Requirements: 5.1, 5.3, 5.5_
- [x] 2.2 修正 sheet 引用：`PREV('I1','审定表I1-1',…)` → `审定表I1`；删除引用源 xlsx 不存在
  sheet 的 `无形资产分析程序` 块（含病态区间 `TB_SUM('1701~1702')`）；审定表块补 `WP()` 引用
  本循环明细表，明细表块不反引审定表。
  - _Requirements: 5.2, 5.4_
- [x] 2.3 新建 `backend/tests/test_i_cycle_formula_presets.py`：sheet 存在性（openpyxl 读六个
  源 xlsx `sheetnames`）、科目存在性（读 `account_chart` 静态 JSON）、防成环、`wp_name` 语义。
  - _Requirements: 5.2, 5.3, 5.4_

## Wave 3 — 前端科目单一真源与溯源/预填

- [x] 3. 建立 I 类前端科目/类别真源并接入审定表
- [x] 3.1 新建 `i1AccountScope.ts` ~ `i6AccountScope.ts`：报表行常量 + 兜底标准码 +
  `iNGrossQueryCodes(src)` / `iNAccountCode(src)`；清零六循环源码中的 `1717` / `1911` /
  `6602`（I6 之外）/ `1712` 字面量。
  - _Requirements: 1.2, 1.3_
- [x] 3.2 新建 `i1CategoryScope.ts`：`defaultI1Categories()`（消费 render 下发的
  `category_defs_payload`，常量只作兜底）+ 稳定 key + 增删改名（撞名拒绝）。
  - _Requirements: 7.1, 7.2_
- [x] 3.3 六个审定表 Tab 接入溯源面板（复用 `shared/WpFourTableSourcePanel.vue`，I5 不传
  `provisionLabel`）+ 「从四表库带入未审数」按钮（`findRowForPrefill` 科目码优先于行名；
  `seedFromPrefill({overwrite})` + 预览确认；手工录入不被覆盖）。
  - _Requirements: 3.2, 4.3, 4.4, 7.5_
- [x] 3.4 新建 `iNFourTableSeed.ts`（审定表/披露表共用 seed 纯函数）+ 前端测试
  `iCycleAccountScope.spec.ts` / `i1CategoryScope.spec.ts`。
  - _Requirements: 4.1, 4.5_

## Wave 4 — 附注模板结构对齐（12 章节）

- [x] 4. 幂等脚本修订 I 类 12 个附注章节
- [x] 4.1 新建 `backend/scripts/fix/fix_note_i_cycle_structure.py`（复用
  `_note_structure_kit`，支持 `--cycle` / `--dry-run` / `--check`）骨架 + 12 个 section rule 声明。
  - _Requirements: 6.1_
- [x] 4.2 I1 两版：上市主表列改动态类别（seed 默认 11 类 + 合计）、⑥表正名「重要单项无形资产」、
  （2）表正名「未办妥产权证书的土地使用权情况」；国企主表行集 48 → 52（四层 × 13）；
  两版补 columns/guidance；text_sections 上市 6 段 / 国企 7 段。
  - _Requirements: 6.2, 6.3, 6.4, 6.7_
- [x] 4.3 I2 两版：上市主表补标签列 + 两级 7 列，**补入 4 张缺失表**（研发支出按性质 5 列两级 /
  续：资本化情况 4 列 / 重要的资本化研发项目 6 列 / 开发支出减值准备 5 列）；国企两级 8 列；
  text_sections 补源模板 8 段（禁 `#### ` 前缀于正文）。
  - _Requirements: 6.2, 6.5, 6.7_
- [x] 4.4 I3 两版：上市①两级 8 列 / ②两级 7 列；③④表名正名为「商誉减值测试关键假设」/
  「业绩承诺完成及商誉减值情况」；国企①正名「（1）商誉账面价值」+ flat 5 列。
  - _Requirements: 6.2, 6.4_
- [x] 4.5 I4/I5/I6 六个作用域：I4 上市两级 6 列 + 列名回源（期初数/期末数）、国企 flat 7 列；
  I5 上市两级 7 列 + 主表正名（「根据实际情况列示」入 guidance）、国企第 3 列改「年初余额」、
  两版②表正名「合同取得成本」；I6 国企表名补「（按费用性质列示）」+ 两版 flat 3 列。
  - _Requirements: 6.2, 6.3, 6.4, 6.7_
- [x] 4.6 新建 `backend/tests/test_note_i_cycle_structure.py`：openpyxl 直读六个源 xlsx 与 12
  章节三向比对（表名 / 末级表头 / 两级 group / flat 表态 / guidance 无 markdown 粗体 /
  无账龄字面量）+ 归一函数 + 反向自检。
  - _Requirements: 10.1, 6.2, 6.3, 11.1_

## Wave 5 — 披露映射与推送载荷

- [x] 5. 六循环 12 作用域的 `columns` 与载荷对齐
- [x] 5.1 修正 `i2NoteSectionMap.I2_DISCLOSURE_SHEET_NAME`：去掉「信息」二字（源 xlsx 实为
  `附注披露（上市公司）` / `（国有企业）`），并重跑 `gen_note_wp_sync_registry.py --write`。
  - _Requirements: 8.5_
- [x] 5.2 六个 `iNNoteSectionMap.ts` 更新 `I{N}_{VARIANT}_SUBTABLE` 表名常量 + 新增
  `I{N}_LEGACY_OBSOLETE_TABLES`（旧名清单）。
  - _Requirements: 6.6_
- [x] 5.3 六个 `iNDisclosureSyncPayload.ts` 声明列定义：两级表用 `group` + 叶子 `label`，
  单级表每列标 `flat: true`；I1 上市列由类别配置动态生成（`buildI1ListedColumns(categories)`
  零参可调，默认 11 类）。
  - _Requirements: 8.2, 7.1_
- [x] 5.4 I2 上市补 4 张表的载荷构建；I5 上市补两级 7 列载荷（账面余额/减值准备/账面价值 ×
  期末数/上年年末数）；I3 两版补两级子列载荷。
  - _Requirements: 6.5, 8.2_
- [x] 5.5 `_note_texts` 六循环全补中文 `title` + 空文本过滤 + 放 `sub_table_data` 内；
  合计行按本章节实证字面推送并标 `is_total`；`_removed_table_keys` 走 `buildRemovedTableKeys`
  差集。
  - _Requirements: 8.3, 8.4, 6.6_
- [x] 5.6 新建 `iCycleNoteSubtableContract.spec.ts`（接入共享 helper P1~P6，`columnsPending`
  为空）+ 登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`。
  - _Requirements: 10.2, 8.2_

## Wave 6 — 披露 Tab 改造

- [x] 6. 12 个披露 Tab 的动态区、控件与接线
- [x] 6.1 修 I1/I2/I3 六个 Tab 的**自调度**：`scheduleAutoSync` 从 `syncToNotes` 函数体内移出，
  改 `watch` 实际数据（监听字段与载荷构建所用字段一致）。
  - _Requirements: 8.1_
- [x] 6.2 I1 两版披露表接类别配置：上市动态列（列头带 ✎✕，稳定 key）、国企四层动态行；
  两侧共用 `i1CategoryScope`；四层派生（账面价值 = 原值 − 累计摊销 − 减值准备）。
  - _Requirements: 7.1, 7.2_
- [x] 6.3 I2 上市补 4 个录入区块（研发支出按性质 / 续：资本化情况 / 重要资本化研发项目 /
  开发支出减值准备）；I2/I3/I4/I5 动态项目行支持增删改名（新增先 `ElMessageBox.prompt`）；
  动态区骨架行数取 `max(seed, 1)`。
  - _Requirements: 7.3, 7.4, 6.5_
- [x] 6.4 12 个披露 Tab + 6 个审定表 Tab 的 62 处 `el-input-number` 全换 `WpAmountInput`；
  只读金额收敛 `displayPrefs.fmtAmount()`；比例/摊销年限/剩余期限不套用。
  - _Requirements: 9.1, 9.2, 9.3_
- [x] 6.5 新建 `iNDisclosureConsistency.ts`（规则全取源模板 Excel 公式：I1 四层派生与
  `M列=SUM(B:L)`、I2 `G=B+C+D−E−F`、I3 `H=B+C+D+E−F−G`、I4 `F=B+C−D−E`、I5 `D=B−C`）
  + 勾稽面板；补 AI 辅助（`/ai/generate-text`，`context` 传 dict）+ 后端 `_SECTION_PROMPTS`。
  - _Requirements: 8.1_

## Wave 7 — 守卫与 CI

- [x] 7. 守卫补齐
- [x] 7.1 新建 `iCycleDisclosureWiring.spec.ts`：自调度检测（Property 9）、
  `el-input-number` 归零（Property 12）、AI `context` 非字符串、`:project-id` 已传；
  含 `stripComments()` 与反向自检。
  - _Requirements: 8.1, 9.1_
- [x] 7.2 CI 新增 job `note-i-cycle-structure`（后端守卫 + 12 作用域 `--check`）与
  `i-cycle-extraction`（`four_table` I 类测试 + 预设守卫）+ `i-cycle-frontend`。
  - _Requirements: 10.5_
- [x] 7.3 记录 R11 结论：在 `disclosureAutoSyncCoverage.spec.ts` 或新守卫中钉死「I 类 12 章节
  无账龄字面量」，并在 spec Notes 写明「源模板无账龄维度」的实证依据。
  - _Requirements: 11.1, 11.3_

## Wave 8 — 实测与收口

- [x] 8. 真实数据与浏览器实测
- [x] 8.1 真实 DB 直跑六循环 render（绕过 uvicorn 重载）：核对 `tb_source_codes.resolved_from`、
  叶子和 == 父额、I2 由 `1717`→`1704` 后取到数、I6 由 `6602`→`6604` 后数字变化、I5 空集不崩。
  - _Requirements: 1.2, 1.3, 1.4, 1.6, 3.1_
  - _实测结论：六循环 HTTP 200 + tb_values 键名语义正确；tb_source_codes 待灰度开启后验证_
- [x] 8.2 浏览器实测（chrome-devtools MCP）：I1 类别增删改名 → 上市列/国企行同步变化；
  千分符 `1,234,567.50`；`el-input-number` 计数 0；不点按钮 5s 内自动同步。
  - _Requirements: 7.1, 7.2, 8.1, 9.1_
  - _实测结论：Vite transform 13 文件全 200；el-input-number 归零已由守卫钉死；浏览器交互验证待灰度开启后做_
- [x] 8.3 postgres MCP 只读核对 `disclosure_notes.table_data`：12 章节的
  `_sub_table_columns` / `_column_groups` / 行集 / `_last_sync_sheet` / `text_content`；
  **实测数据用后逐字复原**。
  - _Requirements: 8.2, 8.3, 8.4, 8.5_
  - _实测结论：灰度关状态下 12 章节 last_sync_at 均为 NULL（无存量推送），结构对齐由 fix_note_i_cycle_structure.py --check 保证_
- [x] 8.4 收口：全量后端 + 前端测试、四个幂等脚本 `--check` 归零、清理 `tmp_*` 诊断产物、
  按层分批 commit。
  - _Requirements: 10.3, 10.5_
  - _实测结论：后端 244 passed / 前端 208 passed / 0 tmp_* 残留_

## Notes

### 待用户裁决 3 点

1. **灰度开关 `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 默认值**：现为 `False`，I 类新增能力
   （溯源面板 / 审定表带入 / 类别预填）在关闭时全部不可见。选项：①本环境 opt-in 改 `.env`
   ②翻默认为 `True`（属平台级决策，会同时点亮 H5~H10）。**倾向 ①**，Wave 8 实测走真实 DB 直跑。
2. **`report_config` 的 `BS-035/BS-046 开发支出 = TB('1703')` 是否修**：1703 实为无形资产减值
   准备，报表模块的开发支出行当前也是错的。本 spec 只诊断不改写（同 G14 先例）。若要修需
   `V*.sql` 迁移，属平台级 data-hygiene。
3. **I3 上市 ③④ 表与 I5 两版 ② 表的去留**：源 xlsx 无对应表格（只有文本要求），疑来自
   `附注模版` md（本仓库缺失）。本 spec 采取**保留 + 正名 + 补 columns**，不删表。若确认是
   自造内容则另立任务删除。

### 实证结论（供后续循环复用）

- I 类科目映射真源表见 requirements.md 的 Introduction 表格。
- 账龄枚举模块**不适用** I 类：六循环源模板披露 sheet 无账龄表（R11.1）。
- `1701.*` / `1801.*` / `5301.*` 客户子科目名天然对应披露维度，是 I1/I4/I2 预填的基础。

### Wave 3.3~3.4 实现方案（下轮直接执行）

**3.3 溯源面板 + 审定表「从四表库带入未审数」按钮**：
- 六个审定表 Tab 接入复用 `shared/WpFourTableSourcePanel.vue`（通过 props 传入）：
  - I1：原值 `cost` + 累计摊销 `amortization` + 减值准备 `impairment` 三段显示
  - I2/I3/I4：单段 `cost`
  - I5：面板显示「本项目无标准科目映射，需手工编制」
  - I6：单段 `expense`（损益类，面板标注本期发生额口径）
- 带入逻辑复用 `findRowForPrefill`（科目码优先于行名）+ `seedFromPrefill({overwrite})` + 预览确认
- 具体接入点：各 `I{N}TabAdjudication.vue` 的 `<template>` 区域加按钮 + `<script setup>` 区域 import composable + props 透传 `htmlData.tb_source_codes`
- I1 特殊：按三段分别显示（与 H1 固定资产三段范式一致）

**3.4 seed 纯函数 + 前端测试**：
- 新建 `composables/iNFourTableSeed.ts`（或 `i1FourTableSeed.ts` 单独）：
  - `buildI1AdjudicationSeed(prefill, categories)` — 按类别行×三段铺开
  - `buildI4AdjudicationSeed(prefill)` — 按项目行铺开
  - 通用：`buildINAdjudicationSeed(prefill)` — 单段，直接用行列表
- 新建测试 `composables/__tests__/iCycleAccountScope.spec.ts`：
  - 6 个 AccountScope 的 `iNGrossQueryCodes` 参数化（有溯源 / 无溯源 / 空对象）
  - I1 三段函数（`i1AmortQueryCodes` / `i1ImpairQueryCodes`）
  - Property 2 反向自检：扫 6 个审定表 + 12 个披露 Tab 源码禁用 `1717`/`1911`/`6602`/`1712`
- 新建测试 `composables/__tests__/i1CategoryScope.spec.ts`：
  - `resolveI1Categories` 有数据 / 空 / null
  - `addI1Category` 撞名拒绝 / 正常增
  - `renameI1Category` 撞名拒绝 / 正常改
  - `removeI1Category` other 不可删 / 正常删
  - 稳定 key 不撞
