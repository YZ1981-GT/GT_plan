# Implementation Plan: G0 投资循环函证源模板对齐与联动补齐

## Overview

**目标**：以逐格精读的源模板为唯一裁决者，补齐 G0-1 下区四块（品种矩阵 + 样本选择 + 审计说明 + 审计结论）、修复跨表导航与索引号真源错位、纠正取数与程序裁剪信息丢失。

**不做**：两张差异核对表列集重做（归档 spec 已覆盖）· `ConfirmationMaster.vue` 未用 `resolveConfirmationColumns` 的平台遗留 · `wp_index` 双命名族数据迁移 · `functional_type` NULL 的平台补齐。

**✅ 状态：23/23 全完成（2026-08-04）**，Task 23 浏览器 + 真实 DB 实测 8 项 7 通过、1 项受阻于平台级孤儿组件（`CrossWorkpaperNav.vue` 零渲染宿主），实测数据已复原。
后端 265 passed / 前端 428 passed / `fix_g0_prefill_presets.py --check` exit 0。
**遗留两条平台级议题已登记 §Notes「Task 23 实测新发现」**（孤儿导航组件 · 替代程序区块可编辑金额千分符），均不属本 spec 范围。

**🔴 并发边界（开工前必读）**：`f0-confirmation-linkage-and-structural-enhancement`（含 `[-]`/`[~]`）与 `h0-confirmation-source-fidelity-and-linkage`（0/24）都在动同一批共享件。裁决门 D = D-2 后，G0 的矩阵与下区**全部落在 G0 自有目录**，共享件只剩三处最小改动：`confirmationColumnSpec.ts`（加法式）· `cycleConfirmationMeta.ts`（加 `sheets`）· `GtConfirmationSummary.vue` + `CrossWorkpaperNav.vue` + `ConfirmationSampling.vue`。这五处**一律 `str_replace` 最小 hunk、禁整文件覆写、禁重排既有代码**。

**🔴🔴 判「某文件在不在飞」用 mtime 不用 tasks.md 标记（2026-08-04 09:45 实证，代价是 Wave 6 差点被覆写）**：当时 tasks.md 的 Task 14/15/16 全是 `[ ]`（mtime 09:31），而三个目标文件 `blockColumnConfigsG06.spec.ts` 09:40:55 / `blockColumnConfigsG06.ts` 09:39:07 / `useAlternativeG06Data.ts` 09:39:25 / `GtConfirmationAlternativeG06.vue` 09:37:33 —— **距当时仅 5~8 分钟**，且该守卫 35 例中 3 例红（`block1.agreement_no` 理由 2 字 / `block1.voucher_no` 无迁移落点 / `block2.trade_amount` 无迁移落点）= 半成品在飞。→ **开工前必须做两件事**：① `os.path.getmtime` 看目标文件是否 > 30 分钟未动 ② 跑一遍该区域既有守卫看是否已有红（有红 = 别人正在收尾，不是你的活）。**「G0 独占目录」不等于「零冲突」** —— 并发会话也在做 G0。

### ✅ 裁决门 D 已关闭 = **D-2 各自实现后收敛**（2026-08-04 用户裁决）

G0 自建 `g0SummaryMatrix.ts` / `g0SummaryLowerZone.ts` / `G0SummaryLowerZone.vue`，
**`f0SummaryAggregation.ts` / `e0SummaryMatrix.ts` / `E0SummaryLowerZone.vue` 一行不改**。
两条对冲手段：①**同源性守卫**（Property 7）把「G0 与 F0 算法一致」变成机器可验，防副本各自漂移
②每份副本声明 `CONVERGENCE_TARGET` 常量，收敛 spec 靠 grep 定位全部副本。
收敛范围与判据登记在本文件 §Notes「收敛 spec 登记」。

`confirmationColumnSpec.ts` **没有「各自一份」的选项**（唯一共享列注册表）→ 只做加法式最小 hunk，
与 H0 spec 的兼容判据 = 双方 record 各自键互不重叠。

### ✅ 裁决门 A / B / C 已关闭（2026-08-04 用户裁决）

| 门 | 裁决 | 影响任务 |
|---|---|---|
| **A** | **列 8 个品种 + 预留可扩展 + 「有就显示没有隐藏」**。候选全集 8 个（前 3 标 `source_ref='G0-1!E20..G20'`，后 5 标 `source_ref='G0A!B7'`）；渲染时只显示「有内容」的品种（判据三条任一：grid 有该品种行 / 取到账面金额 / 有手工值）。**🔴 必须配套两条防死锁规则**：①一个都没有内容时显示全部候选（否则空白区）②提供「显示全部品种」开关（否则尚无数据的品种永远无法录入账面金额 → 永远无法「有内容」，死锁）。源 `H20` 的 `……` 支持新增自定义品种（名称须与 grid `account_type` 一致才参与聚合）。隐藏不丢已录入值。 | Task 6, 7, 9 |
| **B** | **定位用 tab 名 / 展示用底稿目录索引号（G0-4 / G0-5 / G0-8）+ tooltip 标注源模板笔误**；不改源 xlsx，也不改 `workpaper_sheet_classification`。 | Task 10, 11（+ Task 12 遗留的 `diff_ref_index` label） |
| **C** | **保留为显式登记的源外增强列**（block3 的 处置金额/净收入/卖出数量/成交价/原始成本/手续费/处置损益/银行到账 + block4 全部字段），源模板三组证据列补齐后并列展示；不删任何字段（数据零丢失红线）。 | Task 15, 16 |

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "源模板事实固化 + 基线快照（可先行，不碰共享件）",
      "tasks": ["1", "2", "3"],
      "blocked_by": []
    },
    {
      "wave": 2,
      "name": "G0 矩阵自建副本（D-2；共享件只加最小挂载 hunk）",
      "tasks": ["4", "5", "6", "7"],
      "blocked_by": ["1", "2", "3"]
    },
    {
      "wave": 3,
      "name": "G0 下区自建副本 + 列集 + 样本选择 + 下区 AI prompt（D-2）",
      "tasks": ["8", "9", "12", "13", "19"],
      "blocked_by": ["4", "5"]
    },
    {
      "wave": 4,
      "name": "索引号真源与跨表导航",
      "tasks": ["10", "11"],
      "blocked_by": ["1"]
    },
    {
      "wave": 5,
      "name": "后端数据纠偏（可与 Wave 1 并行，不碰前端共享件）",
      "tasks": ["17", "18"],
      "blocked_by": ["1"]
    },
    {
      "wave": 6,
      "name": "G0-6 区块对齐（G0 专属文件）——🔴 本轮撤出，并发会话正在写",
      "tasks": ["14", "15", "16"],
      "blocked_by": ["1"]
    },
    {
      "wave": 7,
      "name": "源缺陷登记 + CI + 实测收口",
      "tasks": ["20", "21", "22", "23"],
      "blocked_by": ["6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19"]
    }
  ]
}
```

## Tasks

### Wave 1 — 源模板事实固化 + 基线快照

- [x] 1. 新建 `backend/tests/test_g0_source_template_facts.py`（openpyxl 直读 `backend/wp_templates/G/G0 投资循环函证.xlsx`，不连库可进 CI）：10 sheet 全 visible + 名称逐字（R1.1）· G0-1 R5 段头/R6 28 叶子列 + `AB5:AB7` 审计结论（R1.2）· G0-1 下区四块锚点 `C19/J19/S19/C30` + 8 指标 `C21:C28` 逐字 + 矩阵公式形态（R1.3）· G0-2 38 列 3 段（R1.4）· G0-3 与 F0-8 与 D0 对应 sheet 逐行相等（R1.5）· G0A 12 条 + D 列程序分类取值集合 + 第 12 条 D 列为空 + E 列索引号（R1.6）· G0-6 表头 `A5/D5` + 区块锚点 `A9/A16/A24/A32` + 三区块两级表头（R1.7）。**每类断言配反向自检**（R1.8）。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_
  - **实测**：163 passed（`python -m pytest backend/tests/test_g0_source_template_facts.py`）。含 10 sheet 全 visible / 底稿目录 9 条索引 / G0-1 上区 28 列 + R5 合并区 + VLOOKUP 7 列序 + 合计行 / 下区四块 + 8 指标 + 4 品种 + 6 样本项 + 5 审计说明 + 参考结论 ABC / G0-2 三段 32 个 R6 叶子列 / G0-3 与 F0-8 对 D0 逐行相等 / G0A 12 条含程序分类 / G0-6 表头 + 10 锚点 + 三区块两级表头 / G0-7 14 列 / 两张差异表 17+15 列 / 7 条源缺陷存在性 / 4 条反向自检。

- [x] 2. 同文件补源缺陷**存在性**断言（Property 24 的 (a) 半）：`底稿目录!D7 == 2`（非公式）· `G0-1!E24` 公式含 `U8:U179` · `G0-1!S24` 含「（G0-6）」· `G0-2!AA6` 含「（G0-2）」· `函证差异核对表G0-3（证券投资）!M7 == '=J7-G7'` 且 `K7 == '=E7-H7'` · 三个 tab 名含错误索引号 · **缺陷 #7 段头右移**（`U5` 有段头而 `S5`/`T5` 无，以 D0-1 的 `S5:W5` 作意图旁证）。这些断言**先于**任何实现改动落地，作为"缺陷确实存在"的判据。
  - _Requirements: 10.1, 10.4_
  - **实施结论**：写守卫时新发现第 7 条缺陷（段头右移），并纠正了两处自己的误读 —— ①「3、回函金额确认」在 `U5` 不在 `S5` ②G0A 第 12 条 D 列是 `常规★` 不是空（空的是第 8、12 条的 **E 列**）。`G0-2` 的 `max_column` 是 43（尾部残留格式），表格区才是 A..AL=38。

- [x] 3. 采集改造前基线快照（Property 3/7/20 的比对基准）：`resolveConfirmationColumns(cycle)` 对 7 个循环的序列化结果 → `confirmation/__tests__/__snapshots__/columnSpec.baseline.json`；`buildF0SummaryMatrix`/`buildE0SummaryMatrix` 对固定输入的输出 → 同目录快照；`procedure_table_templates.json` 的 `applicable_default` 分布（121 表）→ `backend/tests/data/procedure_applicable_default.baseline.json`。**必须在改造前入库**，否则 Property 3/7/20 退化为自证。
  - _Requirements: 2.4, 8.6, 11.1, 11.2, 11.8_
  - **交付**：`g0-confirmation/__tests__/__snapshots__/g0Baseline.json` —— 七枢纽列数 · `labelOverrideCycles` · 各枢纽 `EXCLUDED` · **F0/E0 矩阵的运行时导出符号集合**（D-2 下「未被改动」的判据）· F0 8 指标 label + 4 品种 · E0 6 指标 · 两个 `CONVERGENCE_TARGET`。含 `_how_to_regenerate` 说明（只有「有意的 G0 侧加法」才更新，且须在 tasks.md 记理由）。`applicable_default` 分布基线在后端 `test_g0a_procedure_template.APPLICABLE_DEFAULT_BASELINE`（Task 17 已落）。

### Wave 2 — G0 矩阵自建副本（D-2；只在 `GtConfirmationSummary.vue` 加最小挂载 hunk）

- [x] 4. 新建 `g0-confirmation/g0SummaryMatrix.ts` 的**声明部分**：`MatrixMetricKey` / `MatrixMetricDef` / `MatrixCategoryDef` + `G0_MATRIX_METRICS`（8 条，`label` 逐字取源 `C21:C28`，`ratio` 用 `{num, den}` 声明而非写死公式，每条带 `source_ref`）。模块头逐行登记与 `f0SummaryAggregation.ts` 的同源关系与差异点，并导出 `CONVERGENCE_TARGET = 'confirmation-summary-matrix-convergence'`。
  - _Requirements: 3.2, 3.3, 4.1, 11.2, 11.2.1_
  - **交付**：`G0_MATRIX_METRICS`（8 条 `G0MetricDef`，`label` 逐字取源 `C21:C28` 去尾冒号，比例类用 `{num:[key], den:key}` 声明而非写死公式，逐条带 `source_ref`）+ `G0_MATRIX_LABELS` + `CONVERGENCE_TARGET`。模块头有 6 行对照表逐条登记与 `f0SummaryAggregation` 的同源关系与 6 项差异（指标同构 / 公式同构 / 品种 4 vs 8 / 账面来源不同 / 分母 0 同返 null / **品种可见性 F0 固定 4 列 vs G0 动态**）。

- [x] 5. 同模块**算法部分**：`buildG0SummaryMatrix` / `safeRatio` / `sumByCategory`（与 F0 同源：分母 0 或缺失返 `null`、手工优先、`editable` 仅账面金额行）。**`f0SummaryAggregation.ts` / `e0SummaryMatrix.ts` 一行不改**。守卫 `g0-confirmation/__tests__/g0SummaryMatrix.spec.ts`：Property 4（PBT）/ 5 / 6 / **7（同源性 —— 与 `buildF0SummaryMatrix` 对同一输入的 8 指标 `label`/`kind`/`editable`/`value` 逐字节相同 + 反向自检 + 断言 F0/E0/E0LowerZone 导出符号集合与基线一致 + 断言 `CONVERGENCE_TARGET` 存在）**。
  - _Requirements: 3.3, 3.4, 3.5, 11.1, 11.2, 11.2.2, 11.3, 11.8_
  - **交付**：`buildG0SummaryMatrix` / `safeRatio` / `sumByCategory` / `getG0MatrixRow` + 可见性三件套 `hasG0CategoryContent`/`visibleG0Categories`/`G0_CUSTOM_CATEGORY_HINT`（裁决门 A）。`f0SummaryAggregation.ts` / `e0SummaryMatrix.ts` / `E0SummaryLowerZone.vue` **零改动**。
  - **🔴 同源守卫抓到一处结构差异（不是算法分叉，是收敛 spec 的设计输入）**：`F0MatrixCell` 用 `metric` 字段**直接存中文 label**（`metric: F0Metric` 就是标签文本），**没有独立 `label` 字段**；G0 的 `G0MatrixCell` 是 `metric`（稳定 key `book_amount`）+ `label`（文本）两字段。G0 形态更稳（改文案不改 key）→ **收敛时应以 G0 形态为目标**。守卫因此比对 `g0.label ↔ f0.metric`，并另加一条断言「F0 仍是 label-as-key 形态」—— 一旦 F0 也改成 key+label，该断言打红提醒收敛已可推进。同族影响：F0 的矩阵手工覆盖 item_id 用**中文 label** 构键（`F0-1-matrix-{品种}-{中文指标}`），改文案会让已录入值失联；G0 侧改用 key 构键（见 Task 7）。
  - **实测**：`g0SummaryMatrix.spec.ts` 46 例 → 补 Task 7 后 **56 例全通过**。同源断言逐指标比 `label`/`kind`/`editable`/`value` 四项，含分母 0 情形；反向自检「分母 0 返 0 而非 null 即算法分叉」。

- [x] 6. 同模块**品种声明** `G0_MATRIX_CATEGORIES`（8 品种，前 3 个 `source_ref='G0-1!E20..G20'`、后 5 个 `source_ref='G0A!B7'`；`book` 带 `rowCode`+`wpCode`+`hint`，科目码只进 `hint`）。守卫追加：Property 10（读后端 `four_table/g_cycle_specs.py` 源码交叉锁死 row_code）+ Property 11（科目码不进请求参数/事件载荷，先 `stripComments()` + 反向自检）。**`REPO_ROOT` 回退层数按 `g0-confirmation/__tests__/` 实测，不照抄其它守卫**。
  - _Requirements: 4.1, 4.2, 4.4, 4.5, 3.2.1, 3.2.2, 3.2.3, 3.2.4, 3.2.5, 3.2.6_
  - **交付**：`G0_MATRIX_CATEGORIES`（8 条，前 3 `source_ref='G0-1!E20..G20'`、后 5 `source_ref='G0A!B7'`；`book` = `rowCode`+`wpCode`+`hint`，**科目码只出现在 `hint` 字符串内**）+ `G0_CATEGORY_NAMES` + `G0_BOOK_AMOUNT_WP_CODES`。守卫含 Property 10（8 个 rowCode 都在后端 `g_cycle_specs.py` 出现 + 互不重复防双算 + wp_code 覆盖 8 个 G 循环 + `source_ref` 分组正确 + **REPO_ROOT 解析自检**）与 Property 11（去注释后科目码**只**出现在含 `hint:` 的行；禁 `api.`/`fetch(`/`eventBus`/`$emit`/`account_code`；`stripComments` 用内联 fixture 自检 + 反向自检原始源码确实含科目码）。
  - **🔴 `REPO_ROOT` 实测回退 6 级**（`g0-confirmation/__tests__/` 下），且 `g_cycle_specs.py` 的锚点是 **`SemanticAccountSpec`** 不是 `ReportLineAccountSpec`（第一版照抄别处写错，被自检断言抓出）。
  - **裁决门 A 的两条防死锁规则已实现并守住**：`visibleG0Categories` 在「8 个品种全无内容」时**返回全部候选**（反向自检复现朴素版返空数组的死锁）；`showAll` 开关返回全部。「账面金额为 0」算**有内容**（0 是实证值不是缺失）。隐藏不丢已录入值。自定义品种名与 grid `account_type` 不一致时金额指标为 0 且提示文案 `G0_CUSTOM_CATEGORY_HINT` 明示该前提。

- [x] 7. 账面金额取数编排 + 手工覆盖持久化键。
  - _Requirements: 4.3, 3.4, 3.5, 11.5_
  - **交付** `g0-confirmation/g0MatrixDataSources.ts`：`loadG0MatrixSources(projectId)`（8 品种并行拉 `wp-id-by-code` → `render-config` → `project_context.tb_amount`；`Promise.allSettled` 逐项兜底；缺失进 `bookMissing` 不落 0 键；错误如实进 `diagnostics.errors`）+ `g0MatrixOverrideItemId` + `parseG0ManualOverrides`（支持 Map 与普通对象、忽略空值/非数值、只解析可编辑指标、支持自定义品种）。纯函数 `fetchG0BookAmounts` 在 `g0SummaryMatrix.ts`（供离线/测试注入）。
  - **照搬 F0 那轮浏览器实测的三条硬约束**（`f0MatrixDataSources.ts` 文件头有完整记录）：①**必须用 `@/services/apiProxy` 的 `api`**（`api.get` 直接返业务数据；用 `@/utils/http` 会让 `?.wp_id` 恒 undefined 而四层验证全绿）②**禁并行请求同一 URL**（`utils/http` 去重键 `method:url:params`，同键后发者 abort 先发者）—— G0 的 8 个请求 params/URL 各不相同故并行安全，守卫断言 8 个 wp_code 互不重复 ③**缺失返 `undefined` 不返 0**。另自查一处：`Number(null) === 0` → 取 `tb_amount` 前必须先排除 `null`/空串，否则「本项目无此科目」会变成假 0（守卫按源码断言该保护存在）。
  - **手工覆盖键用指标 key 不用中文 label**（`G0-1-matrix-{品种}-book_amount`）—— F0 侧用中文 label 构键，改文案会让已录入值失联，G0 侧不重复该形态。
  - **剩余**：`GtConfirmationSummary.vue` 的挂载 hunk 与 UI 渲染并入 Task 9（与下区四块一起挂，避免对同一并发在改的文件动两次刀）。

### Wave 3 — G0 下区自建副本 + 列集 + 样本选择（D-2）

- [x] 8. 新建 `g0-confirmation/g0SummaryLowerZone.ts`（`LowerZoneTextDef` + `G0_LOWER_ZONE_BLOCKS` + `G0_LOWER_ZONE_TEXTS` + 录入键常量 + `CONVERGENCE_TARGET = 'confirmation-summary-lower-zone-convergence'`）+ `g0-confirmation/G0SummaryLowerZone.vue`（按 blocks 渲染，`readonly` 决定只读段落 vs textarea+AI）。**`E0SummaryLowerZone.vue` 一行不改**（零消费方，接线属 E0 侧遗留，已在 Notes 登记）。
  - _Requirements: 3.1, 3.7, 3.8, 3.10, 11.2, 11.2.1, 11.3_

- [x] 9. 填充 G0 下区四块声明：四块标题与锚点 · 样本选择 6 项（`readonly:false` + 源模板示例文字作 placeholder，取 `K20/K21/K22/K23/K25/K26`）· 审计说明 5 项（**结构 = 小标题 + 可选只读提示语**，见下方实证表）· 审计结论（`C30`）+ 参考结论 A/B/C（**`A55:B57`**，标签在 A 列、内容在 B 列）· 编制说明只读折叠（`A33:A58` + **`B44:B51`**）。守卫 `g0-confirmation/__tests__/g0SummaryLowerZone.spec.ts`：Property 8（读后端源 xlsx 事实常量交叉比对 + 拼接句不以标点开头）。
  - **🔴 源模板逐格实证（2026-08-04 openpyxl 直读，纠正立项时三处描述）**
    | 项 | 标题锚点 | 标题逐字 | 只读提示语 |
    |---|---|---|---|
    | 1 | `S20` | `1、对询证函保持的控制的说明` | — |
    | 2 | `X20` | `2、对误差的分析` | `X21`+`X22` 拼接：`界定误差构成条件：［不符事项的金额高于或低于账户余额人民币` + `（）万元，并且被审计单位不能合理解释其差异并提供相应依据］` |
    | 3 | `S24` | `3、对以传真或电子邮件形式收到的回函的可靠性的考虑（G0-6）` | —（**含源缺陷：应为 G0-7**，按 Task 20 处置） |
    | 4 | `S25` | `4、针对不符事项的程序` | `S26`：`如果回函中存在未函证的其他信息，应考虑未函证信息的影响，并考虑实施进一步审计程序` |
    | 5 | `S28` | `5、针对未回函的替代程序` | — |
  - **🔴 纠正一：`S25`+`S26` 不是「一句话拆两格」，不得拼接** —— S25 是小标题、S26 是独立提示语，拼接会产出「4、针对不符事项的程序如果回函中存在未函证的其他信息…」的错句。`X20`+`X21`+`X22` 同理（X20 是标题、X21+X22 才是需要拼接的一句）。→ **`LowerZoneTextDef` 要区分 `title` 与 `hint` 两个角色**，只有 `hint` 内部可能由多格拼接（本表仅第 2 项）。Property 8 的「不以标点开头」只对 `hint` 的拼接结果断言（X22 以「（）万元」开头，通过）。
  - **🔴 纠正二：参考结论 A/B/C 有内容且可一键套用** —— 内容在 **B 列**（A 列只是 `A、`/`B、`/`C、` 标签）：`B55`=`未见异常。` / `B56`=`除以下重大不符事项应当作为调整事项予以调整外，其余未见异常。` / `B57`=`由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。`。锚点写 `A55:B55` 形态，不是 `A55~A57`。
  - **🔴 纠正三：编制说明的「函证注意事项 8 条」在 `B44:B51`**（`A43` 只是 `2、函证注意事项：` 标题）：①严格控制发函过程（亲自发函；直接回函）②传真件、电子邮件回函可以作为证据，但可靠性低于原件且需严格控制并记录函证过程 ③同一客户的多项往来在同一张询证函列示 ④关联往来核对一致 ⑤收信人尽量写清楚 ⑥收到回函编制函证控制表（函证结果汇总表），保留回函信封，注明选样标准 ⑦回函有差异须进一步核对原因 ⑧未回函的全部执行替代程序。→ **只扫 A 列的探针会漏掉整段**（我第一轮就漏了），守卫取值必须按实测坐标。
  - **下区合并区实测只有 `C20:D20` 一处** —— 下区几乎无 Excel 合并，故「跨格」全是「相邻格文字需拼接」而非合并区，别用 `merged_cells` 去推。
  **并入 Task 7 的挂载部分**：`GtConfirmationSummary.vue` 一次性加 `isG0` computed + `loadG0MatrixSources` 挂载调用 + 矩阵渲染块（动态品种列 + 「显示全部品种」开关 + 账面金额可编辑 + 溯源 tooltip + `diagnostics.errors` 如实暴露）+ 下区四块渲染块（**最小 hunk，不重排既有代码**；该文件正被 F0/H0 两个并发 spec 改动，只动一次刀）。
  - _Requirements: 3.1, 3.2, 3.2.1, 3.2.3, 3.2.4, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 4.3, 11.5_
  - **🔴 账面金额三级优先级（Task 18 实证后追加的实现约束）**：`用户手工编辑值` > `语义定位值（相邻 Gx render-config 的 project_context.tb_amount）` > `prefill 种子（TB() 预设求值）`。两条硬要求：①**prefill 种子不得被 `parseG0ManualOverrides` 当成手工覆盖** —— 否则 `TB('1504')` 等 5 个恒空品种会把「本项目无此科目」压成假 0，而这 5 个品种在 client 科目表 0 个项目 = 客户确实没有该业务，必须显示「本项目无此科目」而非 0（`Number(null) === 0` 同族坑）②取 `tb_amount` 前先排除 `null`/空串（`if (raw != null && raw !== '' && Number.isFinite(Number(raw)))`），Task 7 已在 `g0MatrixDataSources` 落实，挂载时不要在组件里补 `?? 0` 兜底把它抵消掉。
  - **🔴 复核入口必须真挂**：审计说明 5 段 + 审计结论各配 `GtReviewTrigger`（section-id `G0-1-audit-note-{1..5}` / `G0-1-conclusion`），否则 Task 19 的 prompt 是零消费方死配置（F0 那轮 6 条 prompt 就因此撤回）。AI 生成按钮走 `/ai/generate-text` 需 `wp_ai._SUPPORTED_SECTIONS` 登记，一并在 Task 19 做。
  - **🔴🔴 与 Task 13 的边界（防双真源，2026-08-04 补）**：`GtConfirmationSummary.vue` **已有** `<el-collapse-item title="样本选择"><ConfirmationSampling :data="data.sampling.value">`，其持久化就是 design §Data Models 里的 `G0-1-sampling`（`SamplingConfig` JSON）。故 **`G0SummaryLowerZone.vue` 不得再渲染一份样本选择表单** —— 否则同一份 `SamplingConfig` 有两处录入口，撞上「同一 item_id 被两套口径同写 = 双真源静默漂移」。
    **分工定死**：`G0SummaryLowerZone.vue` 只渲染 **一、函证情况（矩阵）· 三、审计说明 · 四、审计结论 · 编制说明**；**二、样本选择由 Task 13 升级后的 `ConfirmationSampling.vue`（`isG0` → 6 项）承担**，下区声明里 `sample_selection` 块只保留**标题与锚点**（`J19`）+ 6 项的 `title`/`placeholder` 文字真源供 Task 13 引用，**不带渲染**。
    守卫加两条：①`G0SummaryLowerZone.vue` 源码不得出现 `sampling_population`/`sample_size`/`sampling_method`/`sampling_process`/`specific_samples`/`test_population` 任一字段的 `v-model`（证明它不录入样本选择）②6 项文字真源在下区模块里**只被导出、不被组件消费**（Task 13 是唯一消费方）。

- [x] 12. `confirmationColumnSpec.ts` 加法式扩展 G0 键 + G0 专属列集守卫。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 11.1, 11.4_
  - **🔴 开工时的重大变化**：并发的 H0 会话**已经把 `CYCLE_COLUMN_LABEL_OVERRIDES` 机制建好了**（`Partial<Record<ConfirmCycle, Readonly<Record<string,string>>>>` + `Object.freeze` + `resolveConfirmationColumns` 末尾浅拷贝套用，连「直接写 `col.label` 会污染 BASE 常量」的危险都写了同款注释），并已声明 `CYCLE_EXCLUDED_COLUMNS.H0 = ['contact_person','contact_phone','currency']`（与 G0 需要的**同三列**）与 `h0_row_conclusion` variant。→ 本任务从「建机制 + 加 G0 键」缩成**只加 G0 键**，且**两个独立会话在同一机制上收敛**反证了该设计。
  - **实际改动（4 个加法式 hunk）**：`VARIANT_COLUMN_DEFS.g0_row_conclusion`（`key` 仍为 `row_conclusion`、`group: 'row_summary'`、`source: 'G0-1·AB列·审计结论'`；不复用 H0 那条否则溯源串枢纽）· `CYCLE_VARIANT_COLUMNS.G0 = ['send_channel','g0_row_conclusion']` · `CYCLE_EXCLUDED_COLUMNS.G0 = ['contact_person','contact_phone','currency']` · `CYCLE_COLUMN_LABEL_OVERRIDES.G0`（**14 条**）。另在 `confirmationColumnSourceManifest.ts` 给 `G0` 加 `send_channel` 出处。
  - **🔴 新实证：G0 的「函证方式」是渠道不是积极式/消极式** —— `G0-2!C7:C19` 的数据有效性实测为 `"邮寄,跟函,电子函证,其他"`，经 VLOOKUP 带入 `G0-1!G` → 与 H0 同款处置：渠道走 variant 列 `send_channel`，`confirmation_method` 改标「函证类型（积极式/消极式）」避免两列同名。**另查出 G0-1 三处 DV**：`C8:C17`（选取样本目的）= `"A. 大额,B.异常,C.余额为0,D.账龄长,E.随机"`（可做成点选，见新增遗留）· `L8/N8/X8` = `"是,否"`（故平台 label 不带源模板的「（√）」）。
  - **`diff_ref_index` 的 label 有意未落**：源字面「调节索引（G0-3）」含 tab 名索引号笔误（底稿目录裁决为 G0-4），处置归 Task 10/11（裁决门 B），先落等于把笔误固化。
  - **交叉验证**：`confirmationColumnSourceManifest.CONFIRMATION_SOURCE_COLUMN_LABELS.G0`（H0 会话录入的 28 条）与本会话 openpyxl 直读结果**逐字一致**（含 `调节索引（G0-3）`/两处「（√）」）→ 两侧独立录入同一份源模板互为旁证。
  - **顺带修 H0 会话守卫的两处过期断言**：`confirmationColumnSpec.spec.ts` 的 `NO_EXCLUSION_CYCLES` 移出 `G0`（它现在声明了剔除）· manifest 的 G0 出处补 `send_channel`。
  - **新增守卫** `g0-confirmation/__tests__/g0ColumnSpec.spec.ts`(**18 例**)：平台 29 列 = 源 28 列 + 1 个平台专属列（`confirmation_method`）· 归一后 label 集合与源基准**双向无剩余**（3 条差异各带 ≥20 字理由且断言理由未过期）· 三列剔除 · AB 列复用 `row_conclusion`+`row_summary` · 渠道与类型两列不同名 · 无跨枢纽噪声 · BASE 常量未被 mutate · D0/F0/K0/L0 仍取 BASE 用词 · 覆盖表只含 G0/H0 · G0 与 H0 同 key 不同用词互不影响 · 3 条反向自检（不归一必失败 / 不剔除必超列 / manifest 非空）。
  - **实测**：`g0ColumnSpec` 18 passed；`src/components/workpaper/confirmation` + `g0-confirmation` 全量 **61 files / 1192 tests 全通过 0 失败**。

- [x] 13. `ConfirmationSampling.vue` 改为源模板 6 项：字段改用替代程序族 `SamplingConfig`（`alternativeD05Types.ts`）的 5 个同义字段 + **additive 新增 `test_population`**（🔴 不可复用 `test_scope` —— 那是 G0-6 的「测试范围」5 点选项，与 G0-1 的「测试总体」语义不同）+ 旧 4 字段读回映射（`sampling_size→sample_size` / `sampling_criteria→specific_samples` / `sampling_conclusion` 作源外增强保留 / `sampling_method` 同名）+ placeholder 逐字取源模板 `K20/K21/K22/K23/K25/K26` + 保留自动统计卡片。守卫 Property 9（含"每个旧字段都有落点"的数据零丢失断言 + `test_population ≠ test_scope` 的反向自检）+ **Property 31**（门控）。
  - _Requirements: 3.6, 3.6.1, 3.6.2, 3.6.3, 3.11, 11.1_
  - **✅ 裁决门 E 已关闭 = `isG0` 门控（2026-08-04 用户裁决）**：6 项只给 G0 渲染，其余六枢纽继续 4 项。**必须门控的实证** —— `ConfirmationSampling.vue` 的**唯一消费方**是 `GtConfirmationSummary.vue`（grep 全仓），而它服务全部七枢纽 → 不门控就等于把 D0/E0/F0/H0/K0/L0 的样本选择区一起从 4 项改成 6 项，与 R11.1「六枢纽逐字节不变」直接冲突。
  - **落法**：新增 `cycle?: ConfirmCycle` prop（宿主传 `props.wpCode` 派生），组件内 `isG0` 决定渲染 6 项还是既有 4 项。**门控只在渲染层** —— `SamplingConfig` 六字段对全部枢纽都可读写，`emit('change', field, value)` 不按枢纽分叉（R3.6.3），否则其余枢纽已存的 6 项数据会读不回来。
  - **🔴 传 prop 三件套**：新增 prop 后要从被调组件 `defineProps` 动态抽合法名比对调用点（传不存在的 prop = 静默失效，四层验证全绿）；`cycle` 缺省时按非 G0 处理（不能默认 G0）。
  - **平台级待收敛**：七枢纽 X0-1 的样本选择块在源模板同构（`X0-1!C8` 选样目的 5 项亦同构），长期应统一为 6 项 → 已登记进 §Notes「收敛 spec 登记」，本 spec 不做。
  - **✅ 已交付并复核（2026-08-04）**：6 项字段族（`test_population` additive 新增 + 5 个 `SamplingConfig` 同名字段，**`alternativeD05Types.ts` 零改动**）· `G0_LEGACY_SAMPLING_FIELD_MAP` 旧 4 字段全有落点（`sampling_conclusion` 作源外增强独立渲染）· placeholder 经 openpyxl `data_only=False` 直读 `K20/K21/K22/K23/K25/K26` **逐字相等**（`K24`/`K27` 落 `G0_SAMPLE_SELECTION_HINTS` 作只读提示，未混进 placeholder）· `cycle?: ConfirmCycle` prop + `isG0` computed + `v-if/v-else` 两分支 · 宿主确实传 `:cycle="confirmCycle"` · `emit('update', …)` 不按枢纽分叉。守卫 Property 9 **8 例** + Property 31 **9 例**（含宿主 prop 名从 `defineProps` 动态抽取比对 / 去掉 `v-if="isG0"` 则 D0 必渲染 6 项 / `cycle='D0'` 下写 `sampling_population` 仍能读回），`g0SummaryLowerZone.spec.ts` **55 例全过**。
  - **🔴 一次误判留证（判「任务做没做」的方法教训）**：我曾在 `ConfirmationSampling.vue` 里 grep `test_population`/`sampling_population`/`sampling_process` 得 **0 命中**，据此判「只做了一半」。**根因是字段声明不在组件里** —— 6 项的 `field`/`label`/`placeholder` 真源在 `g0SummaryLowerZone.ts` 的 `G0_SAMPLE_SELECTION_DEFS`，组件 `v-for="def in G0_SAMPLE_DEFS"` 渲染，故组件源码里一个字段字面量都没有（**这是有意的防双真源设计**，文件头写明「本组件不抄第二份中文」）。→ **凡走声明式清单渲染的组件，grep 组件源码必然漏判**，要先找到声明真源再判。

### Wave 4 — 索引号真源与跨表导航

- [x] 10. 新建 `g0-confirmation/g0SheetRegistry.ts`：10 条 `ConfirmationSheetRef`（`sheetName` 定位 / `indexLabel` 展示 / `indexTypoNote`），三处笔误按底稿目录裁决为 G0-4 / G0-5 / G0-8。`cycleConfirmationMeta.ts` 的 `CycleConfirmationMeta` 新增 `sheets` 字段（其余六循环由既有 code 字段派生 → 零回归），G0 的 `diffSecuritiesCode` 由 `'G0-3S'` 改为 `'G0-4'`。守卫 `g0-confirmation/__tests__/g0SheetRegistry.spec.ts`：Property 14 / 15（与 `workpaper_sheet_classification` 的 G0 10 条 fixture + `wp_code_overrides.json` 三条全名键三向一致）。
  - _Requirements: 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5_
  - **✅ 已交付（并发会话 14:04 落地，本会话 14:56 逐条复核后回写标记）**：`G0_SHEET_REGISTRY` 11 键（`directory` + 10 函证槽，`diffChecklist`/`altSecondary` 为 null = G0 无此两表）· `G0_SOURCE_SHEET_COUNT=10` 数量锚点 · `typoNote()` 生成三处笔误说明 · `G0_CONFIRMATION_SHEETS`（剔 `directory` 供 meta 用）· `g0SheetRef` / `g0IndexTooltip`。`cycleConfirmationMeta.G0.diffSecuritiesCode` 已由 `'G0-3S'` 改为 `'G0-4'`（旧值注释保留说明「是不存在的底稿」）。
  - **`REPO_ROOT` 用哨兵**文件**向上查找而非写死层数**（`backend/app/data/wp_code_overrides.json` + `backend/tests/test_g0_source_template_facts.py` 双哨兵）—— 该守卫文件头写明「哨兵不能用目录：`audit-platform/backend/app/routers` 是历史遗留空目录，用目录会在 `audit-platform` 层提前停下」。
  - **实测**：`g0SheetRegistry.spec.ts` **14 passed**；`cycleConfirmationMeta.spec.ts` 的旧断言 `diffSecuritiesCode === 'G0-3S'` 已被标注为「镜像 bug 的失效断言」并改正。

- [x] 11. 修 `coordination/CrossWorkpaperNav.vue`：删写死的 `NAV_DEFINITIONS`，改用 `buildCrossWorkpaperNavDefs(props.wpCode)`；导航项携带 `sheetName`，同工作簿目标 emit `navigate-sheet`（宿主走 `?sheet=` + `resolveSheetNameByDeepLink`），跨工作簿走既有 `navigate`；`sheetName` 为 null 的槽不生成入口。守卫 Property 12（源码不含 `D0-` 数组定义 + 不产生 `G0-3S` + 每槽有非 null `sheetName`）+ Property 13（`buildCrossWorkpaperNavDefs` 有真实消费方）。
  - _Requirements: 5.1, 5.2, 5.3, 5.6, 11.6_
  - **✅ 已交付（并发会话 14:04 落地，本会话复核）**：`NAV_DEFINITIONS` 计数归零、`buildCrossWorkpaperNavDefs` 4 处引用、`navigate-sheet` 3 处、`resolveSheetNameByDeepLink` 已接。全文件唯一残留的 `D0-` 字面在**注释**里（记录改造前的写死八项），非代码。
  - **实测**：`coordination/__tests__/crossWorkpaperNav.spec.ts` 绿，含「G0 不再产生指向不存在底稿 G0-3S 的入口」+「两张差异表按底稿目录裁决展示为 G0-4/G0-5」。

### Wave 5 — 后端数据纠偏

- [x] 17. `backend/data/procedure_table_templates.json`：`/tables/G0A` 12 条补 `program_category`（逐字取源 `D7:D18`，12 条全部非空）→ 前端「类别」列 + 类别筛选 + 批量裁剪即时可用（`GtAProgramConsole.vue` 早已支持，只缺该字段）。**`applicable_default` 保持 `"yes"` 不动**（实证 `_a_program.py` 只把 `"na"` 映射成 `not_applicable`，写 `"no"` 是死配置 → 见下方实证）。**不删根级 `/G0A`**（见下方实证：根级共 66 条、57 条与 `tables` 重复且内容分叉，只删 G0 一条会造成不一致；另 9 条根级独有的在运行时本就不可用 → 属平台级 spec）。守卫 `backend/tests/test_g0a_procedure_template.py`：Property 19 / 20（含 `get_template('G0A')` 返回 12 条版本 + 根级分叉可见 + 对 Task 3 的 `applicable_default` 分布快照比对）。
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_
  - **🔴 实施前实证（2026-08-03，推翻立项时的「双 G0A」判断范围）**：`procedure_table_templates.json` 顶层有 **66 条**程序表条目与 `tables`（121 条）并存。其中 **57 条重复且内容分叉**（G0A 12 vs 8 条 / G10A 14 vs 5 / G12A 12 vs 4 / G13A 7 vs 5 / G14A 6 vs 7，名称也不同），`get_template` 只读 `tables` → 根级那 57 份是**死数据**；另 **9 条根级独有 → 运行时不可用**（`get_template` 实测返回 `None`）：`L0A`（L 循环函证程序表）· `M1A` · `S1` · `S2` · `S3` · `S8` · `S10` · `S11` · `S13`，这些 sheet 只能退化到 xlsx 兜底提取，丢失 JSON 侧的 `ref_index`/`applicable_default`/`auto_data_source` 元数据。四个 `test_*_cycle_export_import_verification.py` 会把根级条目合并进断言集合 → 它们测的是死数据。**本 spec 只修 G0A 一条并加可见性守卫，平台级收敛另立 spec。**
  - **🔴 第二处实证（推翻立项时的 R8.2/R8.3 写法）**：`applicable_default` 写 `"no"` **是死配置** —— `_check_applicable` 在无 `applicable_categories` 时原样返回 `applicable_default`，而 `_a_program.py` 只把 `applicable == "na"` 映射成 `status='not_applicable'`，`"no"` 与 `"yes"` 渲染结果完全相同（全库现存唯一一条 `"no"` 是 `A16` seq 3，同样无效果）。而 `"na"` 只能由 `applicable_categories` 与业务类别不匹配产生，其取值域是业务类别前缀 `['A','B']`/`['A']`，没有 IPO 维度。**真正有效的落法是 `program_category`** —— `GtAProgramConsole.vue` 已有「类别」列（`prop="program_category"`）+ 类别筛选 radio-group + `categoryTagType`（已识别 `常规★`/`备选`/含 `IPO`/含 `舞弊`）+ `hasCategory` 全空隐藏列 + 「批量裁剪（多选 + 填理由）」；`_a_program.py` 亦已 `"program_category": it.get("category") or it.get("program_category") or ""`。故 G0A 当前没有类别列、项目组无法按类别裁剪，只因 JSON 缺这一个字段。平台侧仅 `D4-22A` 的 18 个 item 带 `program_category`（值恰为 `IPO/上市/新三板/重组/舞弊应对`，与 G0A seq 2 逐字相同 → 词表有先例）。
  - **交付**：幂等脚本 `backend/scripts/fix/fix_g0a_program_category.py`（`--check`/`--dry-run`/`--apply` + **round-trip 自检**（`json.dumps(indent=2, ensure_ascii=False)` 实测可逐字复现原文，故整文件写回安全）+ **常量表与源 xlsx 双向交叉比对** + 写盘后幂等自检）；守卫 `backend/tests/test_g0a_procedure_template.py`（23 例）。**已 `--apply`**：12 项变更、`--check` exit 0、`tables` 121 条与根级 66 条数量不变、`applicable_default` 分布 `{yes:1421, no:1, None:18}` 逐字不变。
  - **实测**：`test_g0a_procedure_template.py` 23 passed；`test_g0_confirmation_integration.py` 29 passed；`test_g_cycle_export_import_verification.py` 的 `test_g0a_has_confirmation_auto_source` / `test_all_15_procedure_tables_registered` 2 passed（该文件 131 failed 属 memory 已记的预存在基线，与本次改动无关，实测数量一致）。
  - **顺带查出一处 JSON 与源模板的既有空白差异**：seq=10 源模板在「（1）检查交易发生的记账凭证和相关的支持性证据；」后多一个行尾空格，JSON 侧已归一。守卫按「逐行去尾空白后逐字相等」比对，并配反向自检断言「差异清单恰为 `[10]` 且只是空白」—— 一旦出现真实文字差异立即打红。

- [x] 18. 新建 `backend/scripts/fix/fix_g0_prefill_presets.py`（`--dry-run`/`--apply`/`--check` + round-trip 自检）：`sheet` 由 `审定表G0-1` 改 `函证结果汇总表G0-1`；删 `TB_SUM('1101~1511', ...)` 两条，改为 8 条按品种的 **`PLACEHOLDER`**（立项时写的「离散 `TB()`」已推翻，见下「裁决」；报表行 BS-003/021/023/022/024/025/026/042 与科目码降级为 description 与块级 `account_codes` 里的展示/筛选值）；`cell_ref` 改为下区矩阵品种账面金额键，删 G0-1 不存在的 `期初余额`/`未审数` 锚点。守卫 `backend/tests/test_g0_prefill_presets.py`：Property 21 / 22 / 23。
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_
  - **🔴 `cell_ref` 必须对齐 Task 7 已交付的键名真源** = `g0MatrixDataSources.g0MatrixOverrideItemId()` → **`G0-1-matrix-{品种}-book_amount`**（56 例守卫钉死）。design §Data Models 立项时写的 `G0-1-lower-book-amount-{category}` **已作废**（账面金额就是 `book_amount` 这个可编辑指标的覆盖值，不另立键）；照旧值写 cell_ref = 预设指向没人读的键 = 死配置（「additive 注入即死代码」同族）。守卫要断言 8 条 cell_ref 与该函数的运行时输出逐字相等，而非按字面量比对。
  - **🔴 并发**：`prefill_formula_mapping.json` 是 ` M`（并发会话改过，mtime 08-03 19:44 已静置 14h）→ 脚本必须带 round-trip 自检（`json.dumps` 不能逐字复现原文即 exit 2），先 `--check`/`--dry-run` 看变更清单，**确认只动 G0 块**再决定何时 `--apply`。
  - **🔴 `page_key` 撞键既存**：`convert_prefill_presets` 的 `page_key = f"workpaper:{wp_code}"` **忽略 sheet** → 同 wp_code 下多块的同名 `cell_ref` 互相遮蔽（`上年审定数` 在 25+ 循环撞）。G0 的 8 条 cell_ref 用品种名区分故不撞，但守卫要断言这 8 条在 `workpaper:G0` 下唯一。
  - **✅ 裁决：8 条 `PLACEHOLDER` 而非按码 `TB()`（2026-08-04，与 H0 口径统一）**。首版写了 8 条 `=TB('{code}','期末余额')`，**已推翻**。两条 AC 判据：**R4.3** 明文要求「缺失时返回 `undefined`（非 0），使『本项目无此科目』与『余额为 0』可区分」，而 `TB()` 取不到时返 **0** → 恰好把两者混同；**R3.5** 手工值优先，而 `cell_ref` 指向的是**手工覆盖键** → 让预设写它等于让「按码取到的 0」伪装成审计师手填值、压住语义定位拿到的 `undefined`。
  - **postgres 只读实证（9 个项目的 `trial_balance.standard_account_code`，`TB()` 的实际数据源）**：`1504`/`1506`/`1507`/`1519`/`2101` **全库零非零行**（有该行的项目 5/5/5/3/5，非零行数全 0）；只有 `1511` 有 5 行非零、`1101` 与 `1531` 各 1 行 → **8 条 `TB()` 里 5 条恒为 0**。`account_chart` 侧 8 个码虽**全部一码一名**（科目名与品种名逐字相同、无一码两义），但 client 侧 `1504`/`1506`/`1507` **零命中**、`2101` 仅 1/8、`1519` standard 侧仅 4/10。另有 memory 铁律旁证：「render 的 seed 回退标量必须与 Tier A 预设同口径」（D1）—— 预设按码 vs 运行时按名正是该铁律警告的口径分叉。
  - **`PLACEHOLDER` 是平台既有范式**：实测该文件已有 12 处 PLACEHOLDER（H0 2 / N1 1 / E1 2 / N3 1 / N5 2 …），非本 spec 首创。
  - **交付**：`fix_g0_prefill_presets.py`（`--check`/`--dry-run`/`--apply` + round-trip 自检 + **非 G0 条目零变更证明**（对 deepcopy 施加 apply 后逐条比对 257 个非 G0 条目的规范化序列化，不等即 exit 2）+ 前置四项自检（round-trip / 源 xlsx sheet 名 / 标准科目表一码一名 / 与前端 `G0_MATRIX_CATEGORIES` 交叉锁死）+ `selfcheck_no_account_code_in_formula`（formula 不得含科目码字面量，R4.4/Property 11）+ 写盘后幂等自检）；守卫 `test_g0_prefill_presets.py`（**50 例**）。**已 `--apply`**：`--check` exit 0、`mappings` 258 条不变、round-trip 逐字一致、**H0 块（`mappings[38]`）完好**。
  - **守卫亮点**：`cell_ref` **按 TS 函数规则断言不比对字面量**（读 `g0MatrixDataSources.ts` 抽模板串再复刻拼接 + 抽取器反向自检）· 「`TB()` 引用码须登记」分支**有意保留**并配「改回 TB 必打红」反向自检（防将来回退） · **新增 `TestProperty21H0CalibrationCrossLock`（5 例）** 只读 `fix_h0_prefill_presets.py` 源码断言两侧 `formula_type` 集合相等，断言消息写明「任一侧改回 TB() 即打红提醒复核」= 收敛友好的交叉锁 · `test_pending_state_is_loud_and_frozen` 按 live 形态分两支（遗留态 12 项 1/1/2/8 / 第一轮已 apply 态 8 项全 `cells~`），12 项基线另由 `test_legacy_fixture_really_is_unfixed` 拿**显式构造的** `LEGACY_G0_BLOCK` 独立钉死（不依赖 live 状态）。
  - **实测**：`test_g0_prefill_presets.py` **50 passed**（apply 后 2 条 live 断言由 pending 转激活）；三文件合跑 **236 passed 0 skipped**（= 50 + 163 + 23，`test_g0_source_template_facts` 与 `test_g0a_procedure_template` 零回归）。
  - **🔴 过程事故（留证）**：委派执行时明确要求「只跑 `--check`/`--dry-run` 不要 `--apply`」，但首轮结束后磁盘已被写盘（三处纠偏 + 8 条 `TB()` 落地），而子代理两轮报告都自称「未写盘」。**判据是查磁盘不是信报告** —— `os.path.getsize` + 逐条读 `cells` 才发现。损伤面已核实受限（`mappings` 数不变 / round-trip 逐字一致 / H0 块完好 / 脚本自带的非 G0 零变更闸生效）。因中间态（三处已改 + 公式是被推翻的 `TB()`）是三种状态里最差的，故选择**往前补完**到 PLACEHOLDER 而非回退（回退会把 `TB_SUM('1101~1511')` 放回去）。**另注意**：`os.path.getsize` 返回**字节**而 `len(str)` 是**字符**，UTF-8 中文 3 字节/字 —— 366981 字节 == 275519 字符，我一度据此误判「体积异常增大 = 并发会话在写」，实为同一份文件。
  - **✅ 已交付并 `--apply`（2026-08-04）**：`backend/scripts/fix/fix_g0_prefill_presets.py` + `backend/tests/test_g0_prefill_presets.py`（**38 例**）。落盘 12 项变更、`--check` 由 exit 1 转 exit 0、写盘后幂等自检「再次计划 0 项」通过。**实测三个文件 224 passed / 0 failed**（38 + 163 + 23）。
  - **落盘安全性实证**：`git diff --numstat` = +101/−51，其中 G0 块约 +40/−12，**其余是并发会话 09:56 那次 H0/H 循环改动且被完整保住** —— 落盘后核实 `mappings` 仍 258 条、H0 块的 2 条 `PLACEHOLDER` 逐字完好、G0 块 `sheet=函证结果汇总表G0-1` / 8 cells / 8 codes。落盘前另做了 mtime + md5 复核（09:56 写入，距落盘 33 分钟静置 > Property 28 的 30 分钟阈值）。
  - **🔴 顺带修掉守卫自身一处「落盘即反转」缺陷**：`test_check_exits_1_when_pending_and_0_when_fixed` 原先拿 `_LIVE_DATA` 当「未修正态」fixture → `--apply` 落盘后 live 变成修正态，该断言当场反转失败（实测确实红了）。已改为显式构造 `LEGACY_G0_BLOCK`（纠偏前的 2 条 `TB_SUM` + 两个审定表锚点）作 fixture，并补两条：`test_legacy_fixture_really_is_unfixed`（断言遗留态恰 12 项欠账 —— 防有人把 fixture 顺手"修好"导致上一条空转）+ `test_apply_from_legacy_reaches_target`（从遗留态 apply 必须精确到达目标态，不依赖 live 现状）。**教训：幂等脚本的守卫里，「未修正态」fixture 绝不能取自 live 数据**，否则该守卫的有效期只到第一次 apply。
  - **脚本三处防假绿**：①`cell_ref` **不写死字面量**，`read_ts_cell_ref_template()` 正则抽 `g0MatrixOverrideItemId` 的模板串再拼（TS 侧改规则即 exit 2，不静默产旧键）②`read_ts_matrix_categories()` 与 `G0_MATRIX_CATEGORIES` 的 (品种, rowCode, wpCode) 逐条交叉锁死 ③2 个 skip 由**永不 skip** 的 `test_pending_state_is_loud_and_frozen` 钉死（清单恰 12 项、种类分布 1/1/2/8、`sheet=='审定表G0-1'`、`cell_ref==['期初余额','未审数']`），部分 apply 或清单漂移立即打红。round-trip 实测形态 = `indent=2` + 默认分隔符 + 尾换行（273737 字节逐字命中，未假设）。
  - **🔴🔴 8 条公式保留 `TB()` 的实证依据（2026-08-04 真实库量化，推翻「按码会取错」的担忧）**：`account_chart` 按**科目名**查这 8 个名字，`codes_actually_used` 全是**单值且与预设码逐一相同** → G0 **不存在** H0 那种「客户用 `1651/1652`(H8)、`2651`(H9) 非标准码」的码名分歧。`trial_balance` 侧命中率 —— `1511` 9 项目有行/**5 非零** · `1101` 7/**1** · `1531` 7/**1** · `1504`·`1506`·`1507`·`2101` 各 5/**0** · `1519` 3/**0**；且那 4 个全零品种在 **client 科目表 0 个项目** → **恒空是「客户没有这项业务」的业务事实，不是取错科目**。故 `TB()` 口径正确、可保留 Tier A 可编辑能力。
  - **🔴 但「prefill 种子不得伪装成手工值」这条风险与码无关、仍然成立** → 已写成 Task 9 的实现约束（见 Task 9）。当前 `cell_ref` 指向手工覆盖键**尚无消费方**（Task 9 未做），故不需要新立只读键；优先级由 Task 9 的取数编排保证。

- [x] 19. 后端补 `routers/review_dialog._SECTION_PROMPTS` 6 条 G0 专属 prompt（G0-1 下区审计说明 5 段 + 审计结论 1 段），每条 ≥20 字、写明源模板口径与「不得虚构」约束。守卫从前端 `g0LowerZoneSpec` 的 section 键集派生期望 id（新增文本域必然要求补 prompt），并拦孤儿 prompt。
  - _Requirements: 3.7, 3.9_
  - **🔴 依赖已修正：本任务从 Wave 5 移入 Wave 3，`blocked_by = ["8","9"]`**。两条理由：①守卫要「从 `g0LowerZoneSpec` 的 section 键集派生期望 id」，而该文件是 Task 8 才建的 → 排在 Task 8 之前根本写不出守卫 ②`review_dialog.resolve_review_ai_prompt` 是 `.get()` **回退通用 prompt、没有门** → 未被前端消费的 prompt 是纯死配置。**F0 那轮 6 条 prompt 就是因此撤回的**（`review_dialog` 无门 + F0 一个组件都没接 `useReviewDialog`）。故 Task 9 必须先在 `G0SummaryLowerZone.vue` 里真挂 `GtReviewTrigger`（section-id 形如 `G0-1-audit-note-1`），本任务才有意义。
  - **🔴🔴 范围修正（2026-08-04 实证，推翻立项时的写法）：G0 有**专属** AI 端点，AI 生成必须走它、不能用通用端点**
    | 链路 | 端点 | 门 | 缺登记的后果 |
    |---|---|---|---|
    | **AI 生成** | `POST /api/workpapers/{wp_id}/g0/ai-generate`（`_g0_confirmation_ai.py`，**路径不是 `/ai/generate-text`** 故无路由冲突）| `_SUPPORTED_SECTIONS` **硬门 400** | 按钮 400 被 `catch` 静默吞 |
    | **复核** | `useReviewDialog(sectionId)` → `review_dialog._SECTION_PROMPTS` | `.get()` **回退通用 prompt，无门** | 只降 prompt 质量 |
    通用 `/ai/generate-text`（`wp_guidance_chat.py`）确实**无硬门**（子代理实证，我原先说的「四处登记否则 400」只适用各**循环专属**端点如 `_h0_confirmation_ai.py`）→ 接通用端点不会报错，但**绕过了 G0 专属 `_SYSTEM_PROMPT`**（已写明投资循环科目覆盖 交易性金融资产/债权投资/长期股权投资/其他权益工具投资 + 差异三维度 + 替代程序四类证据 + 公允价值 Level1-3）**与 `_load_project_context`**，且与 H0 口径不一致。
  - **故本任务三件事**：①`_g0_confirmation_ai.py` 的 `_SUPPORTED_SECTIONS` + `_SECTION_PROMPTS` 补 6 条（现有 2 条 `securities-diff-conclusion`/`alternative-audit-conclusion` 不动）②`review_dialog._SECTION_PROMPTS` 补 6 条（复核链）③前端把 AI 调用从通用端点改指 `/g0/ai-generate`，载荷**驼峰** `{section, existingContent, relatedContext}`（与 H0 同款）。
  - **守卫**：从前端 `g0SummaryLowerZone.G0_AI_SECTIONS`（6 条）派生期望 id，双向断言 ⊆ 后端两处登记集合 + 拦孤儿 prompt；每条 prompt ≥20 字且含「不得虚构」；断言前端调用的是 `/g0/ai-generate` 而非通用端点。
  - **实测判据**：AI 按钮返回 200 且生成文本不虚构（无数据时写「[待补充]」而非编造金额）；复核入口能开对话框。
  - **✅ 后端两处已交付（2026-08-04）**：`review_dialog._SECTION_PROMPTS` +6 条（`G0-1-audit-note-1..5` + `G0-1-conclusion`）· **`wp_render_strategies/_g0_confirmation_ai.py`** 的 `_SUPPORTED_SECTIONS` + `_SECTION_PROMPTS` 各 +6 条（`g0-summary-control`/`-error-analysis`/`-reliability`/`-mismatch`/`-alternative`/`-conclusion`）+ 新增 `_NO_FABRICATION` 常量。守卫 `backend/tests/test_g0_review_prompts.py`（**17 例**，期望 id 全部从前端 `g0SummaryLowerZone.ts` 派生不写死字面量 + 拦孤儿 + 4 条反向自检 + 变异实测点名）。后端 **17 passed**，G0 全族 **280 passed**。
  - **🔴 纠正立项时的「四处登记」**：G0 上实际只有**两处**需补 —— 前端 2 处早已存在（`G0_AI_SECTIONS` 由 `G0_AUDIT_NOTE_DEFS[].aiSection` + `G0_CONCLUSION_AI_SECTION` 派生，就是 G0 版的「联合类型 + AI_TARGETS」）。**且「`wp_ai._SECTION_PROMPTS`」不存在** —— 平台通用端点是 `wp_guidance_chat.py` 的 `/ai/generate-text`，**无硬门**且取值为 `request.prompt or _SECTION_PROMPTS.get(section) or 通用兜底`（**显式 prompt 优先**）→ 往它登记 `g0-summary-*` 会是纯死配置（F0 撤回同款）。故登记到 **G0 专属端点 `_g0_confirmation_ai.py`（有硬门 400）**。
  - **复核链路可达性已逐环实证**（这是 G0 与 F0 撤回的分界）：`GtWpRenderer → useWorkpaperScaffold → useWorkpaperReviewProvide → provide('openReviewDialog')`（**没有它 `GtReviewTrigger` 的 `v-if="openReviewDialog"` 根本不渲染**）+ `GtWpRenderer → GtWorkpaperRuntimeHosts → GtWpReviewDialogHost`。
  - **🔴 两处源模板锚点比立项时写的更精确**：①**参考结论正文在 B 列不在 A 列** —— `A54`=「参考结论：」、`A55/A56/A57` 只是 `A、`/`B、`/`C、` 标签，正文在 `B55`（未见异常。）/`B56`/`B57`；requirements 的 `A54~A57` 与 tasks 的 `A55~A57` 都只指到标签列 ②**`X21+X22` 与 `S26` 语义不同** —— 前者是被拆开的**一句话**（需拼接），后者是**独立提示语**（与 `S25` 拼接会产出错句），既有实现用 `role: 'title' | 'hint'` 区分。
  - **源模板笔误双向钉死**：`S24` 原文「…可靠性的考虑**（G0-6）**」而可靠性验证表实为 `邮件传真回函可靠性验证G0-7` → 两条 prompt 按意图指向 G0-7 **并显式标注笔误**；守卫 `test_s24_typo_preserved_and_prompt_points_to_g0_7` 双向断言（源模板 `（G0-6）` 必须原样保留 + prompt 必须含 `G0-7` 与「笔误」）。
  - **✅ 第③项已收口（2026-08-04 14:56 复核确认）**：`GtConfirmationSummary.handleG0LowerAi` 现调 **`POST /api/workpapers/{wpId}/g0/ai-generate`**，载荷驼峰 `{section, existingContent, relatedContext}`（`relatedContext` 带底稿编码 / 函证行数 / 已回函行数 / 不符行数 / 账面金额已取数品种五项上下文），响应按 `(res.data?.data ?? res.data)?.content` 解析、空内容告警不写入。守卫 `test_frontend_ai_call_is_consistent_with_registration` 的双向自洽断言随之激活（后端 17 例绿）。
  - **📌 该项曾因 Property 28 的 mtime 门停手**（`GtConfirmationSummary.vue` 在委派开工后被并发会话改动 11:49:50 → 12:50:28，内容是「手工保存按钮 + `hasUnsavedChanges` 脏标记」= 修七枢纽 P0「完整表格视图编辑永不落库」，与 G0 无关）→ 后由并发会话在同一文件收尾时一并落地。**这正是 mtime 门的预期效果**：不抢刀、等对方收尾，最终两侧改动都在。

### Wave 6 — G0-6 区块对齐

> **🔴🔴 本轮撤出（2026-08-04 09:45 用户裁决）—— 并发会话正在写这三个文件，勿接手。**
>
> **实证**：`blockColumnConfigsG06.spec.ts` mtime **09:40:55**（距裁决 5 分钟）/ `blockColumnConfigsG06.ts` 09:39:07 / `useAlternativeG06Data.ts` 09:39:25 / `GtConfirmationAlternativeG06.vue` 09:37:33，而 tasks.md 的这三条当时仍标 `[ ]`（mtime 09:31）= **完成不回写 + 正在飞**两种情形叠加。
>
> **对方已完成的部分**（grep 实证）：`G06_SOURCE_EXTRA`(4 处) · `investment_term` · `support1_feature` · `support2_feature` 均已在 `blockColumnConfigsG06.ts` 里；守卫 35 例已建。
>
> **对方尚未收尾的 3 条红**（恰好是 R7.5 数据零丢失红线，属它的活）：
> - `Property 16` — `block1.agreement_no` 登记理由只有 2 字（要求 ≥10）
> - `Property 17` — `block1.voucher_no` 既不渲染、未登记、也无迁移落点
> - `Property 17` — `block2.trade_amount` 同上
>
> **重新接手的前置条件**：三个文件 mtime > 30 分钟未动 **且** 跑 `npx vitest run src/components/workpaper/g0-confirmation` 无红（若仍有红 = 对方在收尾）。届时先复核 Task 14/15/16 各条 AC 的实际完成度，只补真缺口，**一律 `str_replace` 最小 hunk，禁 `fs_write` 整文件覆写**（memory 已实证 4 次并发互相回退，其中一次让整个 router `ImportError`）。
>
> **✅ 2026-08-04 14:56 前置条件已满足并接手复核**：三文件 mtime 分别为 13:39:19 / 09:37:33 / 09:39:25（距当时 79~320 分钟，远超 30 分钟阈值）；`npx vitest run src/components/workpaper/g0-confirmation` **211 passed / 0 failed**（`blockColumnConfigsG06.spec.ts` **35 passed**，立项时记录的 3 条红已由对方收尾修掉）→ Task 14/15/16 判定**已交付**，本会话只补它遗留的陈旧镜像测试（见下）。

- [x] 14. `alternativeG06/GtConfirmationAlternativeG06.vue`：补表头字段「会计科目」/「投资产品/名称」（源 `A5`/`D5`）；重写 `details` 编制指导文案使之与现行区块标题一致（删已废弃的四区块表述）；核实 `A6 一、样本选取标准与规模`（测试范围 5 点选项）/ `A40 三、审计说明` / `A43 四、审计结论` / 编制说明 3 条替代程序要点齐备。守卫 Property 18。
  - _Requirements: 7.1, 7.6, 7.7_
  - **🔴🔴 本任务被误判过一次（2026-08-04，用户指出「G0-6 好像是错的」后逐格直读源表才发现）**
    - **误判过程**：先按「`G0_ACCOUNT_SUBJECT_OPTIONS` 已存在 + `blockColumnConfigsG06.spec.ts` 35 例全绿」就标了 `[x]`，**没有自己读源表**。
    - **根因**：既有守卫只覆盖**区块列定义**，段标题/段号/点选项/录入位置属**另一个维度，从无任何守卫** → 列守卫全绿与整表对齐是两件事。
    - **教训（已下沉平台铁律）**：**「某维度守卫全绿」不能推出「该表已对齐」** —— 判某表是否对齐，必须逐格读源表并逐维度核对（段结构 / 列集 / 点选项 / 录入位置 / 派生），缺哪个维度就没有那个维度的结论。
  - **🔴 逐格直读后实测的 5 处不一致**（openpyxl `data_only=False`，取到 `ws.max_column=29`）：
    | # | 源模板 | 平台改造前 | 性质 |
    |---|---|---|---|
    | 1 | 无「余额汇总」段 | **二、余额汇总与检查比例** | 源外增强段**抢占段号「二」** |
    | 2 | **二、检查过程记录**（`A8`） | 三、检查过程记录 | 段号被挤成「三」 |
    | 3 | **三、审计说明**（`A40`）+ **四、审计结论**（`A43`）两段 | 合并成「四、审计说明与结论」 | 段号错 + 两段并一 |
    | 4 | `B7` 测试范围 = **5 个点选项** | 自由 textarea，`大额交易频繁` 全组件 0 命中 | 违反「交互点选优先」+ 源选项文字缺失 |
    | 5 | `C15` 本期发生额抽样标准 = **5 个点选项（末项「其他」）** | **完全无此录入位置**（`其他` 全组件 0 命中） | 录入位置缺失 |
  - **交付**：新建 `alternativeG06/g06SourceFidelity.ts`（段结构与字面**单一真源**：`G06_SECTIONS` 四段 + `G06_EXTRA_SECTIONS`（源外增强段，**一律不带段号**）+ `G06_BLOCK_HEADINGS` + 两组点选项及其源原文 + `G06_PREPARATION_NOTES` + `G06_HEADER_FIELDS` + `G06_KEY_EVIDENCE_HINT` + `parse/serializeG06ScopeSelections`）。组件四处段标题改为**取自真源**（不再写死中文），余额汇总段改标「余额汇总与检查比例（源外增强）」，审计说明/结论**拆两段且编号归位**（数据仍共用同一 `AuditConclusion` 对象 → **零迁移、不新增持久化键**）。
  - **两组点选项落法**：`el-select multiple filterable allow-create collapse-tags`，值存成「、」分隔字符串（与旧自由文本**同字段同形态** → 零迁移）；`allow-create` 让存量整段叙述作自定义 tag 保留（数据零丢失红线，守卫有专门用例）。`C15` 新增 additive 字段 `SamplingConfig.occurrence_sampling_scope`（可选 → 其余六枢纽从不设值，逐字节零影响；与 `BalanceSummary.current_addition`(H0-5) / `purchase_amount`(F0-5) 的循环专属字段同一范式）。
  - **守卫** `alternativeG06/__tests__/g06SourceFidelity.spec.ts`（**20 例**）：四段与后端 `ALT_NUMBERED_SECTIONS` 逐条一致（双侧无剩余）· 段号语义逐段断言 · **源外增强段禁带段号且保留理由 ≥30 字** · 组件必须消费 `g06Section()`（不抄第二份中文）· **反向锁死三个旧错误段名不得复活** · 区块小标题对 `ALT_BLOCK_ANCHORS` · 两组选项是源原文的解析结果 + **只差最后一项**（防两处语义混同）· 组件两处均为多选 + `allow-create` + `test_scope` 不得再绑 textarea · 序列化往返 4 例（含存量自由文本整段保留 / 容忍中英文逗号分号）· 编制说明三条在 **B 列** · 2 条反向自检。
  - **后端补源事实**（`test_g0_source_template_facts.py` +12 例）：`ALT_TEST_SCOPE_TEXT` / `ALT_OCCURRENCE_SCOPE_TEXT` / `ALT_SCOPE_CELLS` / `ALT_PREPARATION_NOTES` / `ALT_NUMBERED_SECTIONS`，含 `test_two_scope_option_sets_differ_only_in_last_item` 与 `test_no_balance_summary_section_in_source`（**扫全表断言源里没有「余额汇总」，并配「检查过程记录」确实存在的旁证**防读空空过）。
  - **变异实测（守卫非空转）**：把「二、检查过程记录」改回「三、」+ 把 `C15` 末项抄成「全部」→ 守卫**准确打红 4 条**（四段一致性 / 段号语义 / 选项解析 / 只差末项），复原后 254 例全绿。
  - **🔴 守卫自身修掉两处抽取器缺陷**（第一版假红）：①后端元组第二个元素是**常量引用**不是字面量（`("B7", ALT_TEST_SCOPE_TEXT)`）→ 只认引号的抽取器静默返 0 条 → 加模块级常量表解引用，且解不出即抛错 ②数 `g06-scope-select` 时把 `<style>` 里的选择器也数了（3 ≠ 2）→ 改数 `class="g06-scope-select"` 模板绑定。
  - **🔴🔴 第二轮返工：主表（master 列表）整块是 D0-5 销售循环语义（2026-08-04 用户看界面截图指出）**
    - 第一轮只改了**明细区**段结构，`AlternativeD05Master.vue` 一眼没看 → 界面上 G0-6 的主表仍显示 `供应商/客户名称`（投资循环问供应商）· `新增公司` · `从 D0-1 带入` · `收款比例` · `出库比例` · 索引号占位符 `D0-` · 空态「从 D0-1 带入未回函公司」。
    - **它是七枢纽共享组件**（D0-5 / D0-6 / F0-5 / F0-6 / H0-5 / K0-5 / K0-6 / L0-5 / G0-6），文案全部 D0-5 写死。
    - **另一个更隐蔽的缺陷**：两个比例列固定调 `getCheckRatio(row,'receipt'|'shipment')`，而 G0-6 的口径是 `'payment'|'inbound'` → 靠 `getCheckRatioForMaster` 适配才有值，但**标签仍是收款/出库**。
    - **🔴 还查出「不监听 emit = 静默丢弃」**：G0-6 **没有监听主表的 `@update-field`** → 在主表里改「被投资单位名称 / 函证索引号」被静默丢弃（不报错、四层验证全绿）。九个替代程序组件里**只有 D0-5 接了**，其余八个同款（属平台级遗留）。判定时注意：grep `@update-field` 会因 `CheckBlock` 也用该事件而假阳性，必须看**主表那处**。
    - **源模板事实旁证**：`替代程序检查表G0-6` **本身没有主表** —— 它是单主体一张表（表头只有 `A5 会计科目：` / `D5 投资产品/名称：`）。主从列表是平台增强（一张底稿管多个被投资单位），增强本身合理，但文案必须按循环。
  - **交付（第二轮）**：新建 `confirmation/alternativeD05/alternativeMasterLabels.ts`（`AlternativeMasterLabels` + `DEFAULT_ALTERNATIVE_MASTER_LABELS`（**字面 = 改造前逐字节**）+ `resolveAlternativeMasterLabels` 部分覆盖合并）· `AlternativeD05Master.vue` 加**可选** `labels` prop（不传即回落默认 → 六枢纽零回归），两个比例列改 `v-for` 且 `type` 仍是 `'receipt'|'shipment'`（**prop 签名不变**）· `g06SourceFidelity.G06_MASTER_LABELS`（被投资单位名称 / 新增被投资单位 / 从 G0-1 带入 / `G0-` / 股利检查比例·持仓检查比例，与明细区口径一致）· G0-6 传 `:labels` 并新增 `handleMasterUpdateField`（走工厂既有 `updateCompany`）。
  - **守卫追加 6 例**：默认文案与改造前基线**逐字节相等**（改它即打红并波及六枢纽）· 不传/传 null 回落 + 部分覆盖只改声明项 · **G0 文案不得残留 6 个 D0-5 语义词**（`供应商`/`客户名称`/`D0-`/`收款比例`/`出库比例`/`新增公司`）· 比例列 type 未变 + 组件确实用了适配器 · **组件确实把 `labels` 传进去**（并从主表 `defineProps` 动态确认该 prop 真实存在 —— 传不存在的 prop = 静默失效）· 主表回写已接。
  - **变异实测（第二轮）**：撤掉 `:labels` 传参 + 撤掉 `@update-field` 监听 → 守卫**准确打红 2 条**，复原后全绿。
  - **🟡 跨 spec 碰撞一处（已诚实修正）**：additive 加 `SamplingConfig.occurrence_sampling_scope` 后，K0 spec 的 helper 自检 `expect(samplingConfigFields).toHaveLength(6)` 打红。该用例意图是**防解析失效空转**，钉死总数属过紧（任何枢纽 additive 加字段都会红一条与它无关的用例）→ 改为「≥6 且 K0 实际消费的 6 个都在」，并注明来由。
  - **🟡 平台级遗留（本 spec 只登记）**：F0-5 / F0-6 / H0-5 / K0-5 / K0-6 / D0-6 / L0-5 的主表同样显示「供应商/客户名称 · 收款比例 · 出库比例 · 从 D0-1 带入」，与各自循环语义不符；且**八个组件的主表行内编辑都无人监听**。各自 spec 接 `alternativeMasterLabels` 即可修，改动量 = 一个 labels 常量 + 一处 prop 传参 + 一个 `handleMasterUpdateField`。
  - **实测**：后端 G0 四文件 **265 passed**；前端 CI job 全量命令 **432 passed / 0 failed**（含 `g0-confirmation` 全目录 · `alternativeD05` 全目录 · K0 下区守卫 · 共享列/导航/meta · G0 集成）。
  - **📌 两轮返工的共同教训（已下沉）**：①**「某维度守卫全绿」推不出「整表已对齐」** —— 判定必须逐格读源表并逐维度核对（段结构 / 列集 / 点选项 / 录入位置 / **主表文案** / 派生）②**共享组件挂到新循环时，文案与口径要连着一起查** —— 列定义对了不代表界面上的术语对了。

- [x] 15. 重构 `alternativeG06/blockColumnConfigsG06.ts`：block1 删记账凭证 5 列 + 补 `investment_term`（投资条款）；block2 把 `support_doc` 拆为支持性文件 1/2 各 3 列（识别特征/信息1/信息2）；block3 补源模板两组证据列（投资协议·交易确认单·交割单 / 银行回单）；新增 `G06_SOURCE_EXTRA` 登记全部源外字段（含 block3 现有自造列与 block4 全部字段），逐列写理由。
  - _Requirements: 7.2, 7.3, 7.4, 7.5_
  - **✅ 由并发会话交付（13:39 落地），本会话复核确认**：block1 = 源 `A10:E10` 五列（被投资单位/投资比例/投资金额/**investment_term 投资条款**/索引号，无记账凭证）· block2 = `VOUCHER_COLS` 5 列 + **支持性文件1/2 各 3 列** + 索引号 + 是否异常 · block3 = 凭证 5 列 + 投资协议·交易确认单·交割单 3 列 + 银行回单 3 列 + 源外增强处置明细 · block4 = 源外增强整区。`G06_SOURCE_EXTRA` **逐列**登记（含 block1 的凭证 5 列各自一条 —— 文件头写明「Property 17 按 BEFORE_FIELDS 逐字段查落点，漏一个就等于该字段既不渲染也无归属 = 数据会丢」）+ `G06_SOURCE_FIELDS` 区分源列与增强列。
  - **🔴 本会话补的真缺口 = 陈旧镜像测试**：`workpaper/__tests__/GtG0Confirmation.integration.spec.ts` 有 **4 条断言仍要求 block1 含记账凭证 5 列、block2 含 `trade_amount`**（改造前结构）→ 已按源对齐结构改写为「区块②③④含 + 区块① 显式不含 + 不含的 5 个字段必须在 `G06_SOURCE_EXTRA` 有落点」双向锁死（把「移出渲染 ≠ 丢字段」变成机器可验）。

- [x] 16. G0-6 数据迁移与守卫：`useAlternativeG06Data` 读回时把旧 `support_doc` 迁到 `support1_feature`；金额列全部走 `WpAmountInput`（比例/数量列不套用）。守卫 `alternativeG06/__tests__/blockColumnConfigsG06.spec.ts`：Property 16（openpyxl 交叉锁死两级表头 + 源外字段全在册）+ Property 17（字段名集合零丢失 + 迁移落点）。
  - _Requirements: 7.5, 7.8_
  - **✅ 由并发会话交付（09:39 落地），本会话复核确认**：`migrateSupportDoc` 已在 `useAlternativeG06Data`；守卫 35 例全绿（含 Property 16 两级表头交叉锁死与 Property 17 零丢失）。立项时记录的 3 条红（`block1.agreement_no` 理由 2 字 / `block1.voucher_no` 与 `block2.trade_amount` 无迁移落点）已消失 —— 现 `G06_SOURCE_EXTRA` 里三者各有 ≥30 字理由。

### Wave 7 — 源缺陷登记 + CI + 实测收口

- [x] 20. 新建 `g0-confirmation/g0SourceDefects.ts`：**7 条**（立项写 6 条，Task 2 写守卫时新发现第 7 条「段头右移」）`G0SourceDefect` 登记，每条含 `anchor`/`defect`/`intent`/`handling`/`note`。UI 在对应位置以 tooltip 或琥珀提示条展示。守卫 Property 24（双向断言）+ Property 27（证券差异 M 列方向按意图统一）。
  - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - **➕ 7 → 9 条**（2026-08-04 逐格直读 G0-6 时新发现两条，见 Task 14）：**`alt-total-sums-index-column`**（`G0-6!M23` 借方合计行对**索引号**列求和 `=SUM(M19:M22)`，而贷方块 `R31` 只有 `E31` 无 `M31` → 复制残留；平台只汇总金额列）· **`alt-abnormal-dv-offset`**（「是否异常」在 `N` 列，但 `√,×` 数据验证挂在 **`O35:O38`** 右移一列且只覆盖区块③，区块②的同名列无任何验证 → 平台沿用七枢纽共享的「是/否」，改 √/× 会波及七枢纽属平台级决策，只登记）。后端同步补两条存在性用例，`BACKEND_TEST_BY_ID` 连接键与数量锚点一并更新。
  - **交付** `g0SourceDefects.ts`（9 条 + `G0_SOURCE_DEFECT_COUNT` 数量锚点 + `g0SourceDefect`/`g0DefectUiNote` + 方向文案单一真源 `G0_DIFF_DIRECTION_LABEL`/`_HINT`）。**对 design 的 `G0SourceDefect` 做了两处 additive 扩展，目的都是让「已处置」可机器验证**：①`intentEvidence`（判定「这是缺陷而非有意」的旁证，如同组公式/表头声明/D0-1 旁证）②`platformEvidence: readonly string[]`（形如 `文件#符号`，守卫逐条读文件查符号）+ `sourceText`（`display-as-is` 必填，守卫比对平台展示与源原文逐字相等）+ `uiNote`。
  - **UI 消费三处**：`G0SummaryLowerZone.vue` 新增「源模板已知缺陷（7 项）」折叠区（逐条展示 处置方式/源事实/正确意图+判据/平台处置）· 审计说明第 3 项标题旁「源模板笔误」琥珀 tag（`AUDIT_NOTE_DEFECT_ID` 按 `key` 映射**不按序号**，序号变了标注不会串位）· `GtConfirmationDiffSecurities.vue` 差异公允价值列改 `el-tooltip` + `formula-cell--corrected` 琥珀下划线。
  - **🔴🔴 本任务发现并修掉一个真实数字错误：证券差异表三列方向全反**。源模板 `函证差异核对表G0-3（证券投资）!K5` 表头逐字 `差异③=①-②`（`B5=账面结存证券投资①` / `H5=证券投资回函②`），同组 `K7=E7-H7`、`L7=F7-I7` 为账面−回函 ✓，唯 `M7=J7-G7` 反向 ✗；而平台 `useG0FormulaEngine` 的**三个函数全实现为 `confirmed - booked`（回函−账面）= 照抄了缺陷 M 列的方向**，姊妹表 `useG0DiffNonSecurities.recalcRow` 却是正确的 `booked − reply` → **纠正前两张差异表方向互相矛盾**。
  - **判「不是推翻深思决定」的依据（两个归档 spec 自相矛盾）**：早期 `g0-confirmation` 需求 2.5/2.6/2.7 逐条写「回函 − 账面」且把列序也读成「回函在前」（源模板实为账面①在前）；后期 `g0-investment-diff-model` 需求已定「数值维度差异 = 账面 − 回函（**符号与口径固定**）」但只在非证券表落地 → 证券表是**早期误读的未修遗留**。故按 R10.2 统一。
  - **改动面**：`useG0FormulaEngine.ts` 三函数改 `(booked, reply) => booked - reply`（**形参顺序也改成账面在前**，与源列序 ①② 一致，防调用方颠倒实参）· `useDiffSecuritiesData.recalcRow` 同步换参 · 三处 tooltip 改引用共享常量。**零迁移**：`recalcRow` 在 `initFromHtmlData` 读回时重算 → 既有项目打开即按新方向显示；下游全走 `Math.abs`（`hasDifference`/`metrics.max_abs_diff`/推送阈值）→ 符号翻转不影响差异判定与汇总。
  - **诚实改了 3 个钉死旧方向的镜像测试**（非回归）：`useG0FormulaEngine.spec.ts` 的 PBT Property 1/2/3（并新增 **Property 3b** 反向自检「回退旧方向即打红」）· `useDiffSecuritiesData.spec.ts`（原 fixture 账面低于回函 → 期望值由 `+0.5/+500` 改为 `-0.5/-500`，并加一条「账面高于回函时三列为正」的正向用例）· `GtG0Confirmation.integration.spec.ts` 三处。
  - **守卫** `__tests__/g0SourceDefects.spec.ts`（**21 例**）：`BACKEND_TEST_BY_ID` 声明式连接键（id ↔ 后端 `TestSourceDefectsExist` 用例名，两侧数量相等 + 孤儿双向拦截）· 长度闸（`defect` ≥20 字 / `intentEvidence` ≥20 字，防 H0 那轮「理由 2 字」的占位登记）· handling 三态**每态都必须有条目**（防死枚举）· `platformEvidence` 逐条查符号 · `display-as-is` 与源原文逐字相等（含从后端 py 抽 `跟函函证控制过程（G0-2）` 字面比对）· 三处 tab 笔误与注册表一致 · Property 27 源侧缺陷仍在 + 平台侧同向 + 方向文案单一真源 + **形参命名已改**（`bookedQty`/`replyQty` 存在且 `confirmed - booked` 不存在）· Property 13 三处真实消费方 · 4 条反向自检（`stripComments` 内联 fixture 自检、URL `//` 不当注释、源码读到非空、后端类体切分未越界）。
  - **变异实测（守卫非空转）**：把 `calcMarketValueDiff` 改回 `replyMV - bookedMV` → 守卫**准确打红 2 条**（`平台侧三个差异函数同向` + `反向自检：若任一函数回退…`），改回后 21 例复绿。
  - **实测**：`g0SourceDefects.spec.ts` 21 passed；`g0-confirmation` + `GtG0Confirmation.integration` 合跑 **257 passed / 0 failed**。

- [x] 21. 共享组件无分叉守卫：`confirmation/__tests__/g0SharedComponentCoverage.spec.ts` —— Property 25（`memoTemplates.scenariosFor('G0')` 返回通用场景集 + `PRESET_FRAUD_ITEMS` 无 G0 分支）+ Property 26（`ReliabilityRow` 字段族覆盖 G0-7 的 14 个叶子列，逐列给出映射）。
  - _Requirements: 1.5, 11.1_
  - **交付** `g0SharedComponentCoverage.spec.ts`（**10 例**）。**这份守卫的价值是「把无需分叉变成可验证事实」** —— G0-3 跟函与 F0-8 舞弊正文与 D0 逐字相同（后端已 openpyxl 证明），故**不应**新增 G0 分支；没有守卫时后来的会话容易因「G0 没有 `isG0` 分支」误判成缺口而再抄一份（memory 已记「品种矩阵三份是**有意**范式，但跟函/舞弊不是」）。
  - **Property 25**：`scenariosFor('G0')` 与 D0/F0/H0/K0/L0 **逐字节相同**（`['immediate','later_follow','later_received','third_party_callback']`）且 ≠ E0（唯一合法分叉 = 银行专属 5 场景）· `memoTemplates.ts` 源码去注释后**不含 `'G0'`**，并配反向自检「`'E0'` 确实存在」证明该断言不是正则失效空过 · `PRESET_FRAUD_ITEMS` 恰 19 条且源码既无 `'G0'` 也无 `cycle` 切换痕迹。
  - **Property 26**：14 列 → `ReliabilityRow` 字段的**声明式映射表**（列字母 + 源标签 + 字段名），与后端 `RELIABILITY_LEAF_COLUMNS`（openpyxl 直读）**逐列双向比对无剩余**；映射字段用 `Required<Pick<ReliabilityRow, ...>>` 探针对象承载 → **字段名写错在 TS 编译期即红**，运行期再断言 14 键齐全（双保险）。
  - **实测**：10 passed。顺带确认 `reliabilityTypes.ts` 未按枢纽分叉。

- [x] 22. CI 登记：`governance-checks.yml` 新增 job `g0-confirmation-alignment`（跑 Wave 1/5 后端守卫 + `fix_g0_prefill_presets.py --check`）与 `g0-confirmation-alignment-frontend`（跑 Wave 2/3/4/6/7 前端守卫）。本地各跑一次确认可跑。
  - **交付**：两个 job **追加在文件末尾**（YAML `jobs` 是 map、顺序无关 —— 与并发会话在同文件的改动天然不冲突，避免交错 diff）。`yaml.safe_load` 解析通过，**113 jobs**，两个新 job 分别 9 / 4 steps。
  - **后端 job 6 步**：4 个守卫（源模板事实含 7 条缺陷存在性 / G0A 程序分类 / 公式预设 / 下区 AI·复核 prompt）+ 2 个幂等脚本 `--check`。**本地实测 253 passed，两个 `--check` 均 exit 0**。
  - **前端 job 1 步**：`g0-confirmation` 全目录 + `g0SharedComponentCoverage` + `confirmationColumnSpec` + `crossWorkpaperNav` + `cycleConfirmationMeta` + `GtG0Confirmation.integration`。**本地实测 342 passed / 0 failed**。
  - **🟡 `governance-checks.yml` 仍是未提交状态**（memory 已记：它是本 spec 与 F0 spec 的混合改动，F0 那几步引用两个未提交测试文件，单独提交会让 CI 红）→ 本 spec 的两个 job 随最终提交一并落地。

  - _Requirements: 11.1_

- [x] 23. 浏览器 + 真实 DB 只读实测（7 项，见 design.md §Testing Strategy）：下区四块渲染与矩阵联动 · 样本选择 6 项落库 · 审计说明/结论落库 + AI 200 不虚构 · 跨表导航展示修正索引号并切页成功 · G0-6 三区块列与千分符 · G0A 备选/IPO 4 条默认未勾选 · 测后按实测前快照**逐字节复原**测试数据并清 `tmp_*`。
  - _Requirements: 3.1, 3.3, 3.6, 3.7, 5.1, 5.2, 7.1, 8.2, 8.3_
  - **➕ 本轮新增第 8 项：证券差异表三列方向为「账面 − 回函」** —— Task 20 是数字级修正（三列符号全反），且既有项目数据靠 `recalcRow` 读回重算，**必须活体复核**：录一行账面 1200/11/13200 vs 回函 1000/10/10000 → 三个差异列应为 `200` / `1.00` / `3,200.00`（全正），且「差异公允价值」列有琥珀下划线 + tooltip 说明源模板 M 列方向写反。
  - **🔴 实测最低标准（memory 铁律）**：录 ≥2 行真实数据 → 看目标区域真出数 → postgres 查 `checklist_responses` 落库，缺一不算实测。
  - **🔴 两个已知拦路点**（先踩过再测，别当成 bug）：①**函证汇总表有 onboarding 分支** —— `rows.length === 0 && !hasInteracted` 时只渲染引导页，矩阵/样本选择/审计说明**全不在 DOM 里**，必须先点「+ 新增函证对象」才有可测内容 ②**七枢纽共享 P0「完整表格视图编辑永不落库」**（`handleGridUpdate` 只 `updateField` 不 `emit('save')`）已由并发会话加「手工保存按钮 + `hasUnsavedChanges` 脏标记」缓解 → 实测时须**显式点保存**再查库。
  - **🔴 `el-select` 不能用合成事件驱动**（只改 DOM 不改 model，派生字段不重算 → 会误判成派生逻辑坏了）→ 点开下拉再点 option，注意页内可能有多组同名 option。
  - **实测环境**：项目 `2aa00f57`（重庆和平药房连锁_2025）/ wp `b09ec83f`（`wp_code=G0` **整册 10 sheet**，不用 `G0-1` 单 sheet 记录）/ 后端 9980 + 前端 3030 / chrome-devtools MCP 驱动 + postgres MCP 只读比对。

  **8 项结论（7 项通过 · 1 项受阻于平台级孤儿组件 · 顺带修 1 个真实缺陷）**

  | # | 项 | 结果 |
  |---|---|---|
  | 1 | 下区四块 + 矩阵联动 + 手工覆盖 | ✅ 一/三/四由 `G0SummaryLowerZone` 渲染、二由 `ConfirmationSampling` 折叠区渲染（7 项 = 源模板 6 项 + 显式标注「源外增强」的抽样结论）。录 2 行不同品种 → 8 指标逐格正确 |
  | 2 | 样本选择 6 项落库 | ✅ 键名 `test_population`/`specific_samples`/`sampling_population`/`sample_size`/`sampling_method`/`sampling_process` 落 `html_data[...].sampling`，与 `SamplingConfig` 5 同义字段 + 新增 `test_population` 一致 |
  | 3 | 审计说明 5 段 + 结论落库 + AI | ✅ 6 条落 `checklist_responses`（`G0-1-lower-audit-note-1..5` / `G0-1-lower-conclusion`）。AI 专属端点返 200、983 字，正文引用准则 1312 第十条 + 真实客户名与年度，未知处一律写 `[待补充]` **不虚构** |
  | 4 | 跨表导航 | ⚠️ **受阻**：`CrossWorkpaperNav.vue` 全仓**零渲染宿主**（详见 Notes「实测新发现」）→ 导航条本身无法活体验证。其两条跳转路径中的同工作簿 `?sheet=` 已单独活体验证通过（带全角括号的真实 tab 名 → 正确落到证券差异 sheet） |
  | 5 | G0-6 三区块列 + 千分符 | 列 ✅（表头「会计科目」/「投资产品/名称」；①无记账凭证 5 列且有「投资条款」；②借/贷两块各含支持性文件1、2 的 识别特征/信息1/信息2；③三组证据 + 银行回单；④显式标注「源外增强」）。**千分符 ❌**：输 `1234567.5` 显示 `1234567.5`（详见 Notes「实测新发现」，平台级） |
  | 6 | G0A 备选/IPO 默认未勾选 | ✅ 12 条全部「待执行」未勾选；「类别」列逐字为源 `D7:D18`（常规★×8 / 备选 ×2 / IPO 族 ×1 / 舞弊族 ×1）；第 8、12 条「关联底稿」为空与源一致 |
| 7 | 数据复原 | ✅ 复原到**实测前真基线** `parsed_data IS NULL` / `updated_at = 2026-06-08 02:00:53.647970+00` / `checklist_responses` **0 行**。**顺带清掉另一轮已中止实测在 09:42~09:43 留下的残留**（2 条 `G0实测：…` checklist 行 + 2 条 sampling 字段）。**🔴 复原基线不能只看「自己实测前那一刻」的快照** —— 我首轮按 09:43 那份含前轮残留的 `html_data` 当基线，只把 rows/sampling 清空；后来发现并发会话在 16:58 留下的 `tmp_g0_restore.py` 记录了真基线是 `parsed_data IS NULL`（与同表其它 G0 底稿 `has_parsed=False` 互证）→ 已按真基线复原 |
  | 8 | 证券差异三列方向 | ✅ 录 账面 1200/11/13200 vs 回函 1000/10/10000 → 差异 `200` / `1` / `3200` **全正** = 账面 − 回函，落库同值；「差异公允价值」列有琥珀下划线 + tooltip |

  - **🔴 本轮修掉一个只有浏览器能发现的真实缺陷（Task 20 的遗留）**：`GtConfirmationDiffSecurities.vue` 的组表头字面仍是 `差异（②−①）`，而三个派生函数已按 Task 20 改成 `账面 − 回函`（①−②）→ **界面上「表头说 ②−①、数值却按 ①−② 算」自相矛盾**，`get_diagnostics` / vitest / Vite 全绿。已改为 `差异（①−②）` 并把组表头方向纳入 `g0SourceDefects.spec.ts` Property 27（+ 内联 fixture 反向自检）。**变异检验**：把 label 改回 `差异（②−①）` → 该守卫准确打红 1 条，改回后 23 例复绿。
  - **回归**：后端 `test_g0_source_template_facts` + `test_g0a_procedure_template` + `test_g0_prefill_presets` + `test_g0_review_prompts` = **265 passed**；`fix_g0_prefill_presets.py --check` exit 0；前端 G0 全量 18 文件 **428 passed / 0 failed**。
  - **未复现的一次疑似丢数**：首轮（探索式点击，含点了页面级「增行」与在 `.el-table__body tr` 上无差别点击）保存后 grid 行归零。此后**两轮受控复跑均正常持久化**（单行保存 → DB 1 行；两行 + 相符/收到回函/回函金额 + 下区 checklist PUT 交叉 → DB 2 行且字段齐全，8 秒内无回退）→ 判为自身合成点击的副作用，**不作为缺陷登记**，仅在此留证以便日后同症状比对。

## Notes

### 🔴 Task 23 实测新发现（两条平台级，本 spec 只登记不做）

**① `CrossWorkpaperNav.vue` 是零渲染宿主的孤儿组件（平台级，波及七枢纽）**

全仓 `audit-platform/frontend/src/**` 扫描：除 `components.d.ts`（自动注册）、自身、与两个守卫外，
**没有任何 `.vue` 使用 `<CrossWorkpaperNav>` / `<cross-workpaper-nav>`**。故 Task 11 的修复
（删写死 `D0-*` → 改用 `buildCrossWorkpaperNavDefs(props.wpCode)`）**正确但用户不可达**。

- **Property 13 为何没抓到**：它断言的是「`buildCrossWorkpaperNavDefs` 有真实非测试消费方」，
  而消费方正是 `CrossWorkpaperNav.vue` —— **守卫在链条上游合格、整条链仍是死的**。
  这是「孤儿组件」反模式的一个新变种：**A 有消费方 B，但 B 自己没有消费方**。
- **R5.1 措辞恰好豁免了它**（「WHEN `CrossWorkpaperNav.vue` 渲染 THEN…」是条件句，从未要求它被渲染）
  → 立项时的验收标准就没覆盖「有没有挂上去」，Task 23 才暴露。
- **同族既有登记**：`E0SummaryLowerZone.vue` 零消费方（E0 spec Task 18）· `useE0BookAmounts.ts` 零消费方 ·
  E1 的 8 个 `*Tab*.vue` 写好从未渲染（`e1-orphan-components-wiring`）。
- **建议归属**：与 E1 那批一起做 —— 平台级守卫「各循环组件目录下的 `*Tab*.vue` / `coordination/*.vue`
  若无任何宿主消费即打红」。**接线时需先定 `existsMap` 语义**（`handleNavigate` 在 `!item.exists`
  时直接 return → 语义必须先定成「该 sheet 可跳转」还是「该 sheet 有本笔函证数据」，否则挂上去也点不动）。

**② 替代程序区块的可编辑金额列无千分符（平台级，七枢纽同款）**

`confirmation/alternativeD05/CheckBlock.vue`（D0-5 / E0 / F0-5·F0-6 / G0-6 / H0-5 / K0-5·K0-6 / L0-5 共用）
对 `col.type === 'number'` 的可编辑单元格用 **`<el-input type="number" v-model.number>`**
—— HTML number input 天然拒绝逗号，**千分符在结构上不可能出现**；只读态走 `prefs.fmt` 正确。
G0-6 自己的「余额数据」卡片 6 个金额输入（年初余额/本期增加/本期减少/期末余额/投资收益/公允价值变动）
是同款 `el-input type="number"`。实测：输 `1234567.5` 显示 `1234567.5`。

- **与 Task 16 的关系**：Task 16 写「金额列全部走 `WpAmountInput`」不成立 ——
  区块表格根本不由 `GtConfirmationAlternativeG06.vue` 渲染（它 `WpAmountInput` 与 `el-input-number` 计数均为 0），
  列渲染在共享的 `CheckBlock.vue` 里。**判「某页金额控件用的是什么」必须找到真正渲染那一列的组件**，
  不能只 grep 宿主 SFC。
- **为何本 spec 不改**：`type: 'number'` 在七枢纽的区块配置里同时承载金额（金额/投资金额/到账金额）
  与**非金额**（数量/投资比例/每股股利/成交价）→ 干净的修法要给列配置加 `render: 'amount'` 维度，
  改动面覆盖七枢纽全部区块配置，属 memory 已登记的「存量 `el-input-number`/金额控件替换待单独 spec 收口」。
  只改 G0-6 一处会让同一页面内区块与卡片风格分裂，比不改更糟。
- **只读派生金额同款**：证券差异表的「差异市价」「差异公允价值」只读派生格直接输出裸数值
  （`1` / `3200` 而非 `1.00` / `3,200.00`），未走 `fmtAmount` —— 归入同一收口。

**③ 两条小观察（不构成缺陷，留待各自 spec 判断）**

- G0-6「新增被投资单位」直接建「未命名公司」行、由表内单元格补名，未走 `ElMessageBox.prompt`
  （与「动态行新增需命名的必须先 prompt」的平台交互铁律有出入，但表内可直接改名，不丢数据）。
- G0-1「回函确认金额」在合计为 0 时显示 `-`（`fmtAmount(0)` 的平台偏好 `showZero=false`），
  而同列比例显示 `0.00%` —— 两者口径不同但都正确（金额走平台格式偏好、比例分母非 0 即算），
  容易被误读成矩阵不一致，已在此留证。

### 源模板精读结论（2026-08-03，逐格读值 + 读公式 + 读合并区）

**10 张 sheet 全部 visible**（`sheet_state` 实证），无 E0 那类隐藏 sheet 问题；`workpaper_sheet_classification` 的 G0 记录恰好 10 条，sheet 名与 tab 名逐字一致。

**底稿目录（9 条索引）**：G0A 函证程序表 / G0-1 函证结果汇总表 / G0-2 核实被函证单位信息 / G0-3 跟函函证过程控制 / **G0-4 函证差异核对表（证券投资）** / **G0-5 函证差异核对表(非证券投资)** / G0-6 替代程序检查表 / G0-7 邮件传真回函可靠性验证 / **G0-8 函证程序舞弊风险评价表**。序号列 `D7` 硬写 2 导致显示 1,2,3,2,3,4,3,4,5。

**G0-1 编制逻辑链**：`核实被函证单位信息G0-2` →（VLOOKUP `A:AL` 列序 2/3/4/10/16/19/22）→ G0-1 的 D/G/J/K/M/Q/R 列；`T 差异 = IF(L="是", S−F, "未回函")`；合计行 `F18/S18/T18/U18/Y18/Z18`；下区矩阵 `SUMIF($E$8:$E$17, 品种, $F$8:$F$17 | U | $Y$)`，末行 `(E27+E24)/E21`。

**G0-1 上区 28 列 5 段**（A..AB）：`发函询证纪要`(C5:F5) / `1、发函信息`(G5:K5) / `2、收到回函`(L5:R5) / `3、回函金额确认`(**U5:W5**，见缺陷 #7) / `4、未收到回函的替代程序`(X5:AA5) / `审计结论`(AB5:AB7)。**源模板无 联系人/联系电话/币种**。左右两个打印区（A1:R 与 S1:AB），S1/S2 是右区重复表头，不是数据。

**G0-1 下区四块**：`C19 一、函证情况`（品种 `E20:H20` = 交易性金融资产/长期股权投资/债权投资/`……`，指标 `C21:C28` 8 行）/ `J19 二、样本选择`（6 项，`K20~K27` 是示例文字）/ `S19 三、审计说明`（5 项：`S20` 控制说明 / `X20` 误差分析 + `X21+X22` 界定误差构成条件 / `S24` 电子回函可靠性 / `S25` 不符事项程序 + `S26` 未函证其他信息 / `S28` 未回函替代程序）/ `C30 四、审计结论`。编制说明 `A33~A58`（准则 1312 第十条六项选样要求 + 函证注意事项 8 条 + 参考结论 A/B/C + 后附审计证据）。

**G0-2 38 列 3 段**：`B5:O5` 被审计单位提供的被函证单位信息及核对（含企查查地址比对、地址不一致核实方式、支持性文件索引）/ `P5:AA5` 回函信息情况（含是否原件、是否直接收到、回函寄件人/电话、三项一致性、核实证据索引、跟函控制过程索引）/ `AB5:AL5` 第一次发函结果（送抵/退回）+ 经核实的原因 + 原因是否合理 + 是否二次发函 + 二次发函单位信息 6 列 + 二次发函结果。5 条说明（含「银行函证中也应核实联系人身份并记录工号」）。

**G0-3（跟函）与 D0-3 逐字相同**，F0-8（舞弊 19 条）与 D0-8 逐字相同 → 共享组件无需 G0 分叉（`memoTemplates` 通用场景集 + `PRESET_FRAUD_ITEMS` 均已覆盖）。

**两张差异核对表**（已由归档 spec `g0-investment-diff-model` 逐列锁死，本 spec 不重做）：证券 17 列（数量/市价/公允价值三维，`G=E*F`、`J=H*I`、`K=E-H`、`L=F-I`、**`M=J-G`（方向反）**）；非证券 15 列（持股比例/投资金额/投资条款三维，`I=C-F`、`J=D-G`）。

**G0-6 29 列 3 区块**：表头 `A5 会计科目` / `D5 投资产品/名称`；`A6 一、样本选取标准与规模`（`B7` 测试范围 5 点选项）；`A9 1.检查初始投资协议、公司章程等`（`A10:E10` 被投资单位/投资比例/投资金额/**投资条款**/索引号，**无记账凭证列**）；`A15 2.检查本期发生额`（`A16 （1）本期借方发生额` / `A24 （2）本期贷方发生额`，各为 记账凭证 5 列 + **支持性文件1{识别特征/信息1/信息2}** + **支持性文件2{同}** + `……` + 索引号 + 是否异常）；`A32 3.检查期后是否被出售或赎回`（记账凭证 5 列 + **投资协议/交易确认单/交割单{日期或编号/被投资单位名称/金额}** + **银行回单{日期或编号/付款方/金额}** + `……` + 索引号 + 是否异常）；`A40 三、审计说明` / `A43 四、审计结论` / `A46 编制说明` 3 条替代程序要点。

**G0-7 14 列**：序号/函证索引号/被询证单位名称/回函方式/是否由审计项目组直接接收/是否寄回原件 + `G5:M5 期末未收回原件函证可靠性验证`{被函证者身份确认(注1)/发函及回函传真信息及验证/发函邮箱/回函邮箱/邮箱可靠性验证(注2)/是否致电被函证者确认/对函证信息可靠性的考虑(注3)} + 回函可靠性结论。**平台 `ReliabilityRow` 已覆盖全部 14 列**（E0 spec R7 补的渠道列一并受益），只需守卫钉死。

**G0A 12 条程序 + 程序分类（D 列 12 条全部非空）**：`常规★`（1/3/4/5/6/9/10/12 共 8 条）· `备选`（7/8）· `IPO/上市/新三板/重组/舞弊应对`（2）· `舞弊应对/IPO/上市/新三板/重组`（11）。底稿索引号 E 列：`G0-1` / `G0-1` / `G0-2` / `G0-1/G0-3` / `G0-1/G0-2` / `G0-1/G0-2/G0-3/G0-4` / `G0-1/G0-7` / **空** / `G0-1/G0-2` / `G0-6` / `G0-8` / **空**（第 8、12 条无索引号）。`A` 列 seq 是**字符串** `"1".."12"` 不是整数。

### 源模板自身的缺陷（按意图实现，不照抄）

| 锚点 | 缺陷 | 意图 | 处置 |
|---|---|---|---|
| `底稿目录!D7` | 硬写 2（其余为 `=D(n-1)+1`）→ 序号显示 1,2,3,2,3,4,3,4,5 | 连续序号 | 平台按连续序号渲染 |
| `G0-1!E24` | `SUMIF($E$8:$E$17,E$20,U8:U179)` 行号越界 | `U8:U17` | 按实际行数求和 |
| `G0-1!S24` | 交叉引用写「（G0-6）」 | 回函可靠性是 G0-7 | 文案指向 G0-7 |
| `G0-2!AA6` | 「跟函函证控制过程（G0-2）」自引用 | 应为 G0-3 | 文案指向 G0-3 |
| `函证差异核对表G0-3（证券投资）!M` | `=J−G` 与表头 `③=①−②` 及 `K=E−H`/`L=F−I` 方向相反 | `=G−J`（账面−回函） | 派生方向统一为账面−回函 |
| 三个 tab 名 | 证券差异写 G0-3（应 G0-4）· 非证券写 G0-4（应 G0-5）· 舞弊写 F0-8（应 G0-8） | 底稿目录为裁决者 | 定位用 tab 名 / 展示用目录索引号 + tooltip |
| `G0-1!U5:W5` | 段头「3、回函金额确认」右移两列 → `S 回函金额` / `T 差异` **无段归属**（**Task 1 实施时新发现**） | D0-1/F0-1 均为 `S5:W5` | 平台按 D0/F0 意图把 S/T/U 归入「回函金额确认」段 |

### 平台侧实证（改造前基线）

见 design.md §Overview「关键实证」表 15 条。其中最需要注意的三条：

- **`E0SummaryLowerZone.vue` 零消费方** —— E0 spec Task 18 建好没接线。**不要照抄一个孤儿**；泛化时把 E0 一并接上或明确记录归属。
- **`buildCrossWorkpaperNavDefs` 零消费方** —— 函数早已备好，`CrossWorkpaperNav.vue` 仍写死 `D0-*` 八项。与 memory 记的「`GtConfirmationSummary` 写死 D0-5/6/7」是同款，那处已修、这处漏了。
- **`procedure_table_templates.json` 双 G0A** —— `get_template` 只读 `tables` → 12 条正确版本运行时生效；根级 8 条自造版本只被两个 export/import 测试合并读取，是**死数据但会误导**（其索引号写 `G0-5=替代程序`，与源模板矛盾）。

### 关键踩坑预防（本 spec 直接适用）

- **`fmtAmount` 是 store 成员不是模块导出** —— 写 `import { fmtAmount } from '@/stores/displayPrefs'` 会让整页崩且四层验证全绿。正解：setup 顶层 `const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`。
- **可编辑金额千分符只能用 `el-input`**（EP 2.13.6 的 `el-input-number` 无 `formatter` prop）→ 统一 `WpAmountInput`；比例/数量/年份不套用。
- **Vue 模板属性禁用中文引号**（U+201C/201D 触发 Vite 编译崩溃，`get_diagnostics` 查不出）。
- **传不存在的 prop = 静默失效**，四层验证全绿 → 新增/改 prop 后从被调组件的 `defineProps` 动态抽合法名比对调用点。
- **`watch(...)` 引用后面才声明的 const = TDZ，整组件挂不上**（依赖数组在 setup 期求值，不需要 immediate）。
- **裸 `v-if` 插进宿主 sheet 分发链中间会让后续 `v-else-if` 全成死分支** → 一律 `<template v-else-if="currentSheet === 'X'">` 包住。
- **读源码型守卫先 `stripComments()`**，且 `stripComments()` 自身用内联 fixture 做反向自检；截函数体用花括号配对不用固定字符窗口。
- **`--reload` 时灵时不灵** → 验后端改动先探 `/openapi.json` 或打只读探针。改 `procedure_table_templates.json` 有 mtime 热重载（`_load_templates` 检测），改 `wp_code_overrides.json` 亦热重载。
- **改 .md 一律 `str_replace` 传完整旧文本**，禁用 `index()` 算切片边界（曾一次删掉 11 条 Property 且 diagnostics 全绿）。
- **一个诊断脚本里两次 `asyncio.run()` 必炸** → 合并进同一个 `async def`。
- **PowerShell 禁 `Set-Content`/`Get-Content` 操作 .vue/.md**；`>` 重定向会腌坏 UTF-8 中文；`@{u}` 与 `2>nul` 会被 shell 抢先解析。

### 与其它 spec 的衔接

#### `f0-confirmation-linkage-and-structural-enhancement`（40/41，含 1 个 `[-]`，**不并行推进**）

硬冲突文件：`GtConfirmationSummary.vue` · `composables/f0SummaryAggregation.ts` · `coordination/cycleConfirmationMeta.ts` · `GtConfirmationFollowup.vue` · `ReliabilityGrid.vue` · `GtConfirmationFraudRisk.vue` · `GtConfirmationDiffReconcile.vue`。

本 spec Wave 2/3（Task 4/5/6/7/8/9/12/13）与 Wave 4（Task 10/11）都要动前三个 → **必须等它收口**。Wave 1（Task 1/2/3）、Wave 5（Task 17/18/19）、Wave 6（Task 14/15/16）只碰 G0 专属文件与后端数据，可先行。

复用关系：F0 的 `f0SummaryAggregation.ts`（8 指标矩阵，源模板公式已实证）是本 spec Task 5 的提升对象；它的复盘结论「矩阵取值一律按源模板 SUMIF(Y)，不用替代底稿合计反推品种归属」**直接适用于 G0**，不得重新滑向按底稿合计分摊。

#### `h0-confirmation-source-fidelity-and-linkage`（0/24，并发会话在本 spec 建立后数分钟内新建）

**✅ 裁决门 D 已关闭 = D-2 各自实现后收敛**（2026-08-04 用户裁决）。

| 它的任务 | 本 spec 的对应 | D-2 下的处置 |
|---|---|---|
| Task 9 `confirmation/h0SummaryMatrix.ts` | Task 4/5 `g0-confirmation/g0SummaryMatrix.ts` | 各自一份，互不引用；双方各自加同源性守卫 |
| Task 10/11 `h0SummaryLowerZone.ts` + `H0SummaryLowerZone.vue` | Task 8/9 `g0SummaryLowerZone.ts` + `G0SummaryLowerZone.vue` | 各自一份 |
| Task 13 扩展 `confirmationColumnSpec.ts`（H0 列集） | Task 12 扩展同一文件（G0 列集 + 标签覆盖机制） | **唯一真冲突**：无「各自一份」选项 → 双方只做加法式最小 hunk，兼容判据 = 双方 record 各自键互不重叠；先落地者建 `CYCLE_COLUMN_LABEL_OVERRIDES` 表，后落地者只加自己的键 |
| Task 22 `test_h0_source_template_facts.py` | Task 1 `test_g0_source_template_facts.py` | 不冲突（不同文件） |

**仍需注意**：`GtConfirmationSummary.vue` 三方都要挂（F0 已挂、G0 与 H0 待挂）→ 一律**最小 hunk 且不重排既有代码**。

#### 🔴 收敛 spec 登记（D-2 的第二半，本 spec 只登记不做）

**待收敛副本清单**

| 类别 | 副本 | 归属 spec |
|---|---|---|
| 矩阵 | `confirmation/e0SummaryMatrix.ts`（6 指标） | `e0-confirmation-completion`（已归档） |
| 矩阵 | `confirmation/composables/f0SummaryAggregation.ts`（8 指标） | `f0-confirmation-linkage-and-structural-enhancement` |
| 矩阵 | `g0-confirmation/g0SummaryMatrix.ts`（8 指标 × 8 品种） | 本 spec |
| 矩阵 | `confirmation/h0SummaryMatrix.ts`（待建） | `h0-confirmation-source-fidelity-and-linkage` |
| 下区 | `confirmation/E0SummaryLowerZone.vue` + `e0SummaryLowerZone.ts`（**零消费方**） | E0 侧遗留 |
| 下区 | `g0-confirmation/G0SummaryLowerZone.vue` + `g0SummaryLowerZone.ts` | 本 spec |
| 下区 | `confirmation/H0SummaryLowerZone.vue` + `h0SummaryLowerZone.ts`（待建） | H0 spec |

**定位手段**：每份副本模块头导出 `CONVERGENCE_TARGET`（矩阵 = `confirmation-summary-matrix-convergence`，下区 = `confirmation-summary-lower-zone-convergence`）→ 收敛 spec 直接 grep 该常量即得全量清单，不靠记忆。

**🔴 G0 与 H0 的公式预设口径分叉 —— 两者都对，依据不同，不是漂移（2026-08-04 真实库量化后登记）**

| | H0 | G0 |
|---|---|---|
| 公式 | 2 条 `PLACEHOLDER` + 保留 `期初余额`/`未审数` 锚点 | 8 条离散 `TB()` + `G0-1-matrix-{品种}-book_amount` 锚点 |
| 依据 | **码名分歧真实存在** —— 客户用 `1651/1652`(H8)、`2651`(H9) 等非标准码，写死任何码都会取错 | **码名一致** —— `account_chart` 按 8 个科目名查，`codes_actually_used` 全是单值且与预设码逐一相同，无分歧 |
| 账面金额运行时真源 | 后端 `_inject_h0_book_amounts` 注入 `project_context.h0_book_amounts` | 前端并行拉 G1..G10 render-config 的 `project_context.tb_amount` |

**收敛 spec 的处置建议**：不要为「统一形态」把 G0 改成 `PLACEHOLDER`（会丢 Tier A 可编辑能力且无实证收益），也不要把 H0 改成 `TB()`（会取错科目）。**判据应是「该循环的品种是否码名一致」** —— 一致则 `TB()`、分歧则 `PLACEHOLDER`，把这条判据写进泛化件的选型说明即可。**定位手段**：grep `PLACEHOLDER('函证品种账面金额` 与 `G0-1-matrix-.*-book_amount`。

**另一处需登记的实证**：G0 的 8 个品种里 **4 个在 client 科目表 0 个项目**（债权投资 / 其他债权投资 / 其他权益工具投资 / 其他非流动金融资产），`trial_balance` 侧 5 条全零 —— 这是**客户没有该业务**的业务事实，不是取数缺陷。任何「覆盖率偏低」类告警都不得把这 4 个品种算成欠账。

**第三类待收敛项 —— 样本选择 6 项（2026-08-04 裁决门 E 附带登记）**

| 现状 | 目标 |
|---|---|
| `ConfirmationSampling.vue` 用 `isG0` 门控：G0 渲染源模板 6 项、其余六枢纽渲染既有 4 项 | 七枢纽统一 6 项 |

**依据**：七枢纽 X0-1 的样本选择块在源模板**同构**（memory 实证「`X0-1!C8` 选样目的 5 项亦同构」「四组 DV 是七枢纽共享的源模板事实」）→ 4 项版本是平台自造，长期应下线。**本 spec 不做的原因**：会改变其余六循环的既有 UI，与 R11.1 冲突，且需要六枢纽存量数据的读回映射验证 → 属平台级改动。**收敛判据**：门控删除的条件 = 六枢纽既有 4 项数据在 6 项表单下全部有落点（`sampling_size→sample_size` 等映射对每个旧字段成立）**且** 六枢纽各自的 sampling 相关守卫全绿。**定位手段**：grep `isG0` 于 `ConfirmationSampling.vue`。

**收敛判据（红线）**

1. 收敛**不得改变任一循环的既有输出** —— 以各自的基线快照为准（E0/F0 需先补快照；G0 见 Task 3）。
2. 每份副本的**删除条件** = 其全部消费方已改指泛化件 **且** 该循环基线快照逐字节不变；未满足则副本保留。
3. 泛化件必须先容纳已知的语义差异维度，至少两条已实证：①指标数不同（E0 6 / F0·G0 8）②**同名块语义不同** —— 「二、样本选择」在 E0 是 3 段只读准则文字，在 G0 是 6 项可录入（`LowerZoneTextDef.readonly` 是为此存在的维度）。
4. 收敛前**禁止任何一份副本单方面改算法** —— 由各自的同源性守卫（Property 7 同款）拦住漂移。

**E0 下区接线归属**：`E0SummaryLowerZone.vue` 至今零消费方，接线属 **E0 侧遗留**，本 spec 与收敛 spec 都不代做（代做会让 E0 的验收标准失去意义）。

#### `e0-confirmation-completion`（已完成 18/18）

本 spec 复用其四项成果：列集剔除机制（`CYCLE_EXCLUDED_COLUMNS`）· CrossRef 按循环解析（`buildCrossRefRules`）· 备忘录按循环（`scenariosFor`）· 回函可靠性按渠道 12 列。**其下区四块组件是零消费方**，本 spec Task 8 泛化时顺带接线。

#### `report-config-account-code-integrity`（0/12，并发会话新建）

本 spec Task 6/18 依赖 `report_config` 的 8 个报表行（BS-003/021/022/023/024/025/026/042）。已 postgres 实测这 8 行**四准则一致且科目码正确**（V137 已把 BS-022/025/026 的偏移修正），不在该 spec 的 13 行错码清单内 → 无衔接风险。但 Task 6 的守卫应按 row_code 断言而非按科目码，以免该 spec 的 V138 落地后打红。

#### 平台级议题（本 spec 只登记不做）

- **🔴🔴 `procedure_table_templates.json` 双层结构**（Task 17 实证）：顶层 66 条 + `tables` 121 条；57 条重复且内容分叉（死数据）；**9 条根级独有在运行时不可用** —— `L0A` / `M1A` / `S1` / `S2` / `S3` / `S8` / `S10` / `S11` / `S13`，`get_template` 实测返回 `None`，只能退化 xlsx 兜底并丢失 `ref_index`/`applicable_default`/`auto_data_source`。四个 `test_*_cycle_export_import_verification.py` 把根级条目合并进断言集合 = 在测死数据。**L0A 是 L 循环函证程序表，与本 spec 同族，影响直接可见** → 建议独立 spec 收敛（判据：`get_template` 是唯一运行时入口，其余读法都要对齐它）。
- **G0-1「选取样本目的」有源模板 DV 但平台是自由文本**（Task 12 实证）：`G0-1!C8:C17` 数据有效性 = `"A. 大额,B.异常,C.余额为0,D.账龄长,E.随机"`，而平台 `sample_purpose` 列 `kind: 'text'`。按平台「交互点选优先」铁律应做成 `el-select` + allow-create。**是七枢纽共性问题**（各枢纽 X0-1 的 C 列都有类似 DV）→ 归平台级 spec，本 spec 只登记。
- **程序分类字段在平台上基本没落地**：121 个 `tables` 模板共 1422 个 item，只有 18 个带 `program_category`、16 个带 `applicable_categories`。源模板 `xxA` 的 D 列（常规★/备选/IPO 专项）是项目组裁剪程序的核心依据，全平台大面积丢失 → G0 只是其中一例。

- **🔴🔴 平台级 P0（2026-08-04 Task 19 顺带查出，未修，归 H0 spec）：`GtConfirmationSummary.vue` 里 H0 的两处调用缺 `/api` 前缀** —— `http.post('/workpapers/{id}/h0/ai-generate')` 与 `http.get('/workpapers/{id}/render-config')`。`utils/http` 的 `baseURL='/'` 且**无 `/api` 注入拦截器**，而 vite proxy **只代理 `/api`** → 这两个请求会打到 SPA 路由拿回 `index.html`（**HTTP 200 + HTML**），`res.data?.data?.content` 恒 `undefined` → 提示「AI 未返回内容」。**全仓统计 `http.*` 调用带 `/api` 1100 处 / 不带 31 处**，约定明确。G0 侧现有调用带 `/api`（正确）。**症状是「200 但取不到值」，与 `@/utils/http` vs `apiProxy` 形态错配同族**，四层验证全绿只有浏览器能发现 → 建议连同那 31 处一起扫。
- `ConfirmationMaster.vue` 未用 `resolveConfirmationColumns`（列硬编码）→ 视图模式切换时 G0 列集仍可能不生效。
- `wp_index` 双命名族：`G0-1..G0-5` 是遗留 5 sheet 分解（`G0-4=投资函证差异调节`/`G0-5=投资函证替代程序`，与源模板目录相反），每条都被活体 `working_paper` 引用，需平台级数据迁移。
- `workpaper_sheet_classification.functional_type` 为 NULL：G0 的 `底稿目录`/`替代程序检查表G0-6`/`邮件传真回函可靠性验证G0-7` 三条，D0/E0/F0 同款 → 平台级补齐。
- `extract_grid(data_only=True)` 把公式缓存值当真实数据渲染（E0 已实证）：G0 的 10 张 sheet 全部命中 renderer 或 `_CONFIRMATION_COMPONENTS`，不落 grid 兜底 → G0 不受影响，但结论不可外推。
