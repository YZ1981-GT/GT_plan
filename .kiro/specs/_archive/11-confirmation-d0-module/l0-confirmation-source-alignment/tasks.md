# Implementation Plan: L0 债务循环函证源模板对齐

## Overview

四波 20 任务。**Wave 1/2 零碰共享件可立即推进；Wave 3 碰七枢纽共享件，须与 `k0-confirmation-source-alignment` 协调为同一次刀，且遵守其 R11.5（`f0-confirmation-linkage-and-structural-enhancement` 仍有 `[-]`/`[~]` 期间不开工）。**

调查阶段已实证的三个 P0（不再重复验证，直接修）：

1. `get_template('L0A')` 返回 None → `resolve_program_template_code('函证程序表F0A','L0')` 回退 `F0A` → L0 程序表实际加载「采购存货循环函证程序表」12 条，`ref_index` 全为 `F0-1`/`F0-2`
2. L0 预设块 `sheet='审定表L0-1'`（源 xlsx 无此 tab）+ `account_codes=['2001','2501']`（短期借款/长期借款，正是源模板 L0A 程序 1 明确排除的银行借款）+ 病态区间 `TB_SUM('2001~2501')`
3. `GtConfirmationSummary.vue` 无 `isL0` 分支 → L0-1 下区四块完全缺失

## Tasks

- [x] 1. 建后端源模板事实守卫 `backend/tests/test_l0_source_template_facts.py`
  - openpyxl 直读 `backend/wp_templates/L/L0 债务循环函证.xlsx`
  - 固化：9 visible + 1 hidden 的 `sheet_state`；底稿目录 8 行索引（`D3:F11`）；L0-1 五段合并表头（`C5:F5`/`G5:K5`/`L5:R5`/`S5:W5`/`X5:AA5`/`AB5:AB7`）；28 列字面（第 5/6 行）；8 指标公式（`E31~E37`/`F31~F37`）；2 品种字面（`E29`/`F29`）；L0A 12 条程序 + 分类 + 索引号；四处真实 DV（`L0-1!C8:C27`、`L0-1!L/N/X`、`L0-2!C7:C24`、`L0-2!P7:P26`）；三处索引号笔误
  - **反向自检**：断言镜像残留 sqref（`JK8:JL27` / `JN8:JP27`）确实存在于文件中，但不落在 `L0-1` 的真实数据列（A..AB）上
  - _Requirements: 8.1, 8.2_

- [x] 2. 建 `tables.L0A` 条目 + 幂等脚本 `backend/scripts/fix/fix_l0a_program_template.py`
  - 按源模板 `函证程序表F0A!A7:G18` 重建 12 items（`description` / `program_category` / `ref_index` / `hint`）
  - seq=1 的 `hint` 取源 `G7` 原文（银行借款排除声明）；seq=8 的 `hint` 取源 `G14`（第三方平台技术提示3号链接）
  - 加法式：只增 `tables.L0A`，不动既有 121 条；根级既有 `L0A`（10 items）保持不动，留待平台级收敛 spec
  - 带 round-trip 自检 + `--dry-run` / `--check` / `--apply`
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [x] 3. 建守卫 `backend/tests/test_l0a_program_template.py`
  - Property 1 / 3 / 4
  - Property 2 含反向自检：临时移除 `tables.L0A` 复现 `resolve_program_template_code` 返回 `F0A`，**移除操作放 `finally` 无条件写回原文**
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 10.3_

- [x] 4. 纠正 L0 公式预设 + 幂等脚本 `backend/scripts/fix/fix_l0_prefill_presets.py`
  - `sheet`：`审定表L0-1` → `函证结果汇总表L0-1`
  - `account_codes`：`['2001','2501']` → `['2701','2502']`
  - cells：删病态区间 `TB_SUM('2001~2501', ...)`，改为分品种离散 `TB('2701', ...)` / `TB('2502', ...)`
  - `description` 如实写明被纠正的反例（校验器只扫语义字段，见 Task 5）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 5. 建守卫 `backend/tests/test_l0_prefill_presets.py`
  - Property 5 / 6
  - Property 7 双向：`description` 塞被禁字样 → `--check` 仍 0；`formula` 塞同一字样 → `--check` 必打红
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 6. 建 `backend/app/services/four_table/l0_book_amounts.py`
  - `L0_CATEGORY_SPECS` 复用 `l_cycle_specs.L5_SPEC`（长期应付款）/ `L4_SPEC`（应付债券），**不新写科目定位**
  - `fetch_l0_book_amounts` 走 `semantic_account_resolver` + `resolve_leaf_totals(absolute=True)`（负债类整族统一取向，禁逐行 `abs()`）
  - `2702` 作为 `2701` 子科目族已在父族聚合内净掉 → 跳过二次减并记 `net_of_skipped`
  - `found=False` → `amount=None`（不返 0）
  - _Requirements: 3.3, 3.4, 10.4_

- [x] 7. 接 `_inject_l0_book_amounts`（`wp_render_config_helpers.py`）
  - 加法式注入，仿 `_inject_h0_book_amounts`；**不注册 `RENDERER_DISPATCH`**（`confirmation-summary` 是七枢纽共享）
  - `wp_code` 前缀门控**早于**取数调用
  - 写入 `html_data.project_context.l0_book_amounts`
  - _Requirements: 3.3, 3.4, 10.1, 10.2_

- [x] 8. 建守卫 `backend/tests/four_table/test_l0_book_amounts.py` + 真实库直跑脚本
  - Property 11（源码级断言无四位科目码字面量）/ Property 12（三态可区分）
  - `backend/scripts/diagnose/verify_l0_book_amounts_live.py`（只读）：逐项目逐品种打印 `resolved_from` / `codes` / `amount` / `parent_check.diff` / `net_of_skipped`
  - 断言其余六枢纽载荷注入前后深比较逐字节不变
  - _Requirements: 3.3, 3.4, 8.1, 10.1_

- [x] 9. 建 `confirmation/l0-confirmation/l0SummaryMatrix.ts`
  - 2 品种 × 8 指标；`metric` 稳定 key + `label` 独立字段（不用 label-as-key）
  - 8 指标口径按源模板 `E31~E37` 公式；比例列 `ISERROR` 兜底返 0
  - 导出 `CONVERGENCE_TARGET = 'confirmation-summary-matrix-convergence'`
  - _Requirements: 3.1, 3.2_

- [x] 10. 建 `confirmation/l0-confirmation/l0MatrixDataSources.ts`
  - `matrixOverrideItemId(categoryKey, metric)` 用**指标 key** 构键（禁中文 label）
  - 取数用 `import { api } from '@/services/apiProxy'`（禁 `@/utils/http` default export）；并行请求不对同一 URL 发多次
  - `diagnostics.errors` 必须有渲染出口（不只收集）
  - 读 `project_context.l0_book_amounts` 时区分 `undefined`/`null`/`0` 三态，禁 `?? {}` 兜底
  - _Requirements: 3.4, 3.5_

- [x] 11. 建 `confirmation/l0-confirmation/l0SummaryLowerZone.ts`
  - `L0_SAMPLE_SELECTION_DEFS` 6 项（源 `J29/J30/J31/J32/J34/J35`；`J33` 括注作提示文本）
  - `L0_AUDIT_NOTE_DEFS` 5 段（源 `S29/W29/S33/S34/S36`）；`W30`+`W31` 与 `S34`+`S35` 各合并为一段完整文字
  - `L0_SECTION_TITLES` 含审计说明序号笔误更正（源 `S28` 字面「二、」→ 展示「三、」+ 笔误说明）
  - `L0_REFERENCE_CONCLUSIONS`（源 `A65:B68` 三条）+ 后附证据说明（源 `A69`），只读
  - 导出 `CONVERGENCE_TARGET = 'confirmation-summary-lower-zone-convergence'`
  - _Requirements: 3.6, 3.7, 3.8, 3.9_

- [x] 12. 建 `confirmation/l0-confirmation/L0SummaryLowerZone.vue`
  - 四块渲染：矩阵（可编辑账面金额 + 溯源面板 + 三态文案）/ 样本选择 6 项 / 审计说明 5 段（每段带 AI 辅助 + 复核）/ 审计结论
  - 下区录入**直接 `PUT /api/workpapers/{id}/checklist-responses`**，禁 `emit('save', {itemId, value})`
  - 金额只读格走 `displayPrefs.fmtAmount`（setup 顶层 inject，禁模块级 import）
  - _Requirements: 3.1, 3.4, 3.5, 3.6, 3.7, 3.9, 3.10_

- [x] 13. 建前端守卫（L0 专属，零碰共享件）
  - `l0SummaryMatrix.spec.ts`：Property 8 / 9 / 10 / 13 + PBT（比例列不产生 NaN/Infinity）
  - `l0LowerZone.spec.ts`：Property 14 / 15 / 16
  - 跨前后端交叉锁死：读后端 `l_cycle_specs.py` 比对 `row_code` 与兜底码；`REPO_ROOT` 用双哨兵具体文件向上查找
  - _Requirements: 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 14. `confirmationColumnSpec.ts` — 只增/改 L0 键
  - `CYCLE_VARIANT_COLUMNS.L0`：撤 `send_memo`（伪列），`row_conclusion` → 新注册 key `l0_row_conclusion`（group `row_summary` + source 指向 `L0-1·AB列`），新增 `send_channel`
  - `CYCLE_EXCLUDED_COLUMNS.L0`：`['contact_person','contact_phone','currency']`
  - `CYCLE_COLUMN_LABEL_OVERRIDES.L0`：13 处 label 逐条取自源模板第 5/6 行；`confirmation_method` → 「函证类型（积极式/消极式）」；`diff_ref_index` → 指向 `L0-4`（源字面 `F0-4` 是笔误）
  - 同步 `CONFIRMATION_SOURCE_MANIFEST.L0` 出处登记；复查 `NO_EXCLUSION_CYCLES` 白名单移出 L0
  - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 9.1, 9.2, 9.6_

- [x] 15. `send_memo` 既有值只读呈现
  - 行详情面板加只读分支 + 「源模板此处为段头，本值为历史录入」提示
  - 断言字段未从 `ConfirmationRow` 类型删除、无数据删除动作
  - _Requirements: 4.2, 10.6_

- [x] 16. `GtConfirmationSummary.vue` + `ConfirmationSampling.vue` 接入 L0
  - `isL0` computed + `<L0SummaryLowerZone v-if="isL0">`（与 K0 spec Task 10 协调为同一次刀）
  - `ConfirmationSampling.vue` 加 `isL0` 门控（6 项，与 `isG0` 同构）
  - _Requirements: 3.11, 9.1, 9.3, 9.4_

- [x] 17. 隐藏 sheet 复合键 skip（`wp_render_config.py`）
  - 加 `{wp_code}-{sheet_name}` skip 判定，接在既有三条（全名 / 尾码 / 前缀码）**之后**
  - `wp_code_overrides.json` 加 `L0-函证差异检查表（示例）` → `skip`，并**移除**裸键 `函证差异检查表（示例）` → `confirmation-diff-checklist` 的误配（改为只在 D0/F0 生效的复合键或保留裸键作 componentType 用）
  - 复核 `cycleConfirmationMeta.L0.diffChecklistCode` 保持 `null` 与不渲染结论一致
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 18. 三处索引号笔误登记 + L0-5 区块标题对齐
  - `cycleConfirmationMeta.L0` 用 `ConfirmationSheetRef` 的 `indexTypoNote` 登记三处笔误（程序表 tab / `L0-1!V6` / `L0-2!AA6`），`*Code` 字段一个不删
  - `alternativeBlockManifest.L05` + `GtConfirmationAlternativeL05.vue` 三处 title 对齐源模板 `A13`/`A20`/`A28`；block2 去「银行对账单」「借款合同」；block3 借贷副标题对应 `A29`/`A37`；block4 保持 `sourceExtra`
  - 不改 `block` key / 列 key / `SUM_FIELDS`
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 19. 建共享件守卫 + CI job
  - `l0ColumnAlignment.spec.ts`：Property 18 ~ 24 / 36
  - `l0SheetMeta.spec.ts`：Property 28 / 29 / 30 / 31 / 32
  - `l0LowerZoneWiring.spec.ts`：Property 17（带边界的标签存在性断言 `<L0SummaryLowerZone(?=[\s/>])`）
  - `backend/tests/test_l0_render_sheets.py`：Property 25 / 26 / 27（含 characterization 快照）
  - CI job `l0-confirmation-alignment`（后端守卫 + 幂等脚本 `--check`）+ `l0-confirmation-frontend`
  - **逐条变异检验**（八项，见 design Testing Strategy）并记录结果
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

- [x] 20. 回归 + 浏览器实测 + 收口
  - 回归：`four_table` 全量 / `confirmation` 域前端全量 / 六枢纽 resolve 输出与 render-config sheets 零回归断言
  - 实测三件套（缺一不算实测）：**入口用 `wp_code=L0` 整册（9 sheet）**；录 2 行不同品种 → 下区矩阵 16 格逐格核对 → postgres 查 4 类下区键 + 上区载荷；程序表页签核实 12 条债务循环程序且 `ref_index` 为 `L0-*`
  - 实测后按快照逐字节复原；清理本会话 `tmp_*` 产物
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端数据层纠偏（零碰共享件）",
      "tasks": ["1", "2", "3", "4", "5"],
      "rationale": "源模板事实守卫先落地作为后续裁决基准；程序表模板与公式预设是两个独立 P0，互不依赖，可并行。Task 3/5 分别是 2/4 的守卫。"
    },
    {
      "wave": 2,
      "name": "后端取数 + L0 专属前端声明（零碰共享件）",
      "tasks": ["6", "7", "8", "9", "10", "11", "12", "13"],
      "rationale": "Task 6→7→8 是取数链路；9/10/11 是三个 L0 专属声明文件（矩阵/取数源/下区文案），12 消费它们，13 是守卫。全部为新建文件，与并发 spec 零交集。Task 10 依赖 7 下发的载荷契约。"
    },
    {
      "wave": 3,
      "name": "共享件接入（须与 K0 spec 协调，F0 spec 有中断标记时不开工）",
      "tasks": ["14", "15", "16", "17", "18"],
      "rationale": "五个任务全碰七枢纽共享件。Task 16 的 GtConfirmationSummary.vue 与 K0 spec Task 10 是同一刀口，必须协调为一次编辑。Task 14 与 K0 spec Task 9 改同一文件但键互不重叠。Task 17 改平台分发层 wp_render_config.py。"
    },
    {
      "wave": 4,
      "name": "守卫收口 + 回归实测",
      "tasks": ["19", "20"],
      "rationale": "共享件守卫必须在 Wave 3 落地后才能断言最终状态；实测与回归最后做。"
    }
  ],
  "blocking": {
    "wave_3": {
      "condition": "f0-confirmation-linkage-and-structural-enhancement 的 tasks.md 不再含 [-] / [~] 标记，且 k0-confirmation-source-alignment 的 Task 9/10 已协调开工顺序",
      "reason": "K0 spec R11.5：Wave 3 全碰共享件，F0 spec 仍有中断标记期间不得开工，避免三个 spec 在同一批文件上互相回退"
    }
  }
}
```

## Notes

### 立项调查已核实无需改动的部分（勿重复立项）

逐 sheet 精读后确认，以下已由 `e0/g0/h0/k0` 系列 spec 在共享组件内收口，L0 直接受益：

| sheet | 已有能力 | 承载文件 |
|---|---|---|
| L0-2 | 三区列集（核实信息 15 列 / 回函信息 12 列 / 第一次+第二次发函结果）、6 项核实方式 DV、送抵/退回枚举 | `entityVerify/` |
| L0-3 | 三个控制核对点（了解流程 / 确认身份权限 / 按正常流程处理）、工号字段、签名区、备忘录话术 | `followup/followupEnums.ts`、`memoTemplates.ts` |
| L0-5 | 抽样参数 6 项、四区块（block3 拆借贷）、期初余额一致性核对、审计说明 + 结论 + AI 辅助、导入导出 | `alternativeL05/`、`l0-confirmation/composables/` |
| L0-6 | 可靠性列集（含发函/回函邮箱、传真信息、可靠性考虑）、注1~注3 tooltip、邮箱域名实时判定、结论自动推导（只建议不写入） | `reliability/` |
| L0-7 | 19 条舞弊迹象三态 + 应对措施 + 推送 B50 | `fraudRisk/` |

### 三处被调查推翻的初始假设（勿再「纠正」）

1. **`函证程序表F0A` 的 tab 名不能改** —— `resolve_program_template_code` 已针对「F0A vs L0」写好兜底（注释原文即举此例），缺的只是 `tables.L0A` 条目。改 tab 名会打断 `workpaper_sheet_classification` 与既有数据。
2. **`函证差异检查表（示例）` 不能按裸 sheet 名标 skip** —— 该 sheet 在 D0/F0 是 **visible**（openpyxl 三处模板实证），裸名 skip 会杀掉 D0/F0 的真实页签。必须走 `{wp_code}-{sheet_name}` 复合键。
3. **`L0-1` 的四处 DV 不含「函证方式」** —— `JK8:JL27` 那条 `跟函,邮寄,电邮,其他` 是**列重复产生的镜像残留 sqref**，不落在真实列上。L0-1!G 的渠道值由 `VLOOKUP` 自 `L0-2!C` 带入（DV 为 `邮寄,跟函,电子函证,其他`，四项与镜像残留的四项**用词不同**）。凡判 DV 一律 `coord in dv.sqref` 逐格测试。

### 源模板自身缺陷登记（按意图实现，不照抄）

| 位置 | 源模板字面 | 正确值 | 依据 |
|---|---|---|---|
| 程序表 tab 名 | `函证程序表F0A` | L0A | `底稿目录!F4` 是索引号唯一裁决者 |
| `L0-1!V6` | `调节索引（F0-4）` | L0-4 | `底稿目录!F8=L0-4` |
| `L0-2!AA6` | `跟函函证控制过程（F0-3）` | L0-3 | `底稿目录!F7=L0-3` |
| `L0-1!S28` | `二、审计说明` | 三、审计说明 | `C28`=一、/ `J28`=二、/ `C39`=四、|
| `L0-5!A28` 编号 | `4、测试本期发生额` 前有 `3、检查期初余额`，但 block 编号与区块序不完全对应 | 按源模板原编号 | 不重排 |

### 跨 spec 接缝

- **与 `k0-confirmation-source-alignment`**：K0 剩余 Task 8~18 与本 spec Wave 2/3 结构同构（矩阵 / 列 spec / 下区 / 取数 / 笔误 / 守卫 / 实测）。`confirmationColumnSpec.ts` 双方键互不重叠可并行；`GtConfirmationSummary.vue` 是同一刀口须协调。K0 与 L0 的品种矩阵**各自实现**（裁决 D-2），两份副本都导出 `CONVERGENCE_TARGET` 供收敛 spec 一次性 grep。
- **与 `f0-confirmation-linkage-and-structural-enhancement`**：本 spec Wave 3 受其中断标记阻塞（见 `blocking`）。F0 剩余 4 项全是浏览器实测且用户已中止该轮，**编排器不得接管**。
- **平台级议题（本 spec 不解）**：`procedure_table_templates.json` 双层结构 —— 根级 69 条与 `tables` 121 条并存，其中 57 条重复且内容分叉、9 条根级独有导致 `get_template` 返回 None（`L0A` 是其中之一，本 spec 只补 L0A 一条）。收敛需平台级 spec。

### 待用户裁决

1. **L0-1 下区矩阵是否预留可扩展品种** —— 源模板恰 2 个品种（长期应付款 / 应付债券）且无「……」可扩位，与 G0（8 品种 + 可扩 + 「有就显示没有隐藏」）不同。倾向：固定 2 品种不做动态列，因源模板无可扩位依据；若客户把专项应付款（`2711`）也挂在债务循环函证，需另行裁决。
2. **`函证差异检查表（示例）` 的 componentType 裸键处置** —— 当前裸键 `函证差异检查表（示例）` → `confirmation-diff-checklist` 同时服务 D0/F0/L0 三处。Task 17 有两种落法：(a) 保留裸键作 componentType 用 + 新增 L0 复合键作 skip 用；(b) 裸键改复合键 `D0-…` / `F0-…` 两条。倾向 (a)，半径最小。

## Progress Log

### Wave 1 已交付（Task 1~5，2026-08-05）

| Task | 产物 | 验证 |
|---|---|---|
| 1 | `backend/tests/test_l0_source_template_facts.py`（792 行 / 9 类 / 59 test 函数 / 178 例） | 178 passed；**11 项变异全红**（品种名 / 指标 label / 分类计数 / 可见 sheet / hidden sheet / VLOOKUP col_index / SUMIF sum_range / 真实 DV 枚举 / 镜像 DV 用词 / L0-5 段标题 / 笔误登记条数） |
| 2 | `backend/scripts/fix/fix_l0a_program_template.py` + `tables.L0A`（12 items） | `--check` exit 0；幂等（连跑两次 md5 不变）；`tables` 121→122，`F0A`/根级 `L0A` 逐字未动；round-trip 稳定 |
| 3 | `backend/tests/test_l0a_program_template.py`（55 例） | 55 passed；**9 项变异全红**（删 tables.L0A / 改 content / 改 category / ref 换 F0-1 / content→description / 加 hint / 丢排除声明 / 删根级 L0A / 改 F0A name） |
| 4 | `backend/scripts/fix/fix_l0_prefill_presets.py` + L0 块纠正 | `--check` 14 项欠账 → 0；幂等；`mappings` 258 条不变；round-trip 稳定 |
| 5 | 守卫合并进 Task 3 与 Task 1（`test_l0_prefill_presets.py` 的断言已由 `fix_l0_prefill_presets.diff_block` + `test_l0a_program_template.TestFixScript` 覆盖） | 见 Task 3 |

**P0-1 已消除（实证）**：`get_template('L0A')` 由 `None` → `('长期应付款/应付债券函证程序', 12)`；`resolve_program_template_code('函证程序表F0A','L0')` 由 **`F0A`** → **`L0A`**。改造前 L0 程序表实际加载「采购存货循环函证程序表」12 条、`ref_index` 全为 `F0-1`/`F0-2`。

**P0-2 已消除（实证）**：L0 预设块 `sheet` 由源 xlsx 不存在的 `审定表L0-1` → `函证结果汇总表L0-1`；`account_codes` 由 `['2001','2501']`（短期借款/长期借款 = 源模板 L0A 程序 1 明确排除的银行借款）→ `['2701','2702','2502']`；病态区间 `TB_SUM('2001~2501',…)` 删除，改矩阵手工覆盖键 + `PLACEHOLDER`。

### 三处立项判断被实证推翻（勿再「纠正」）

1. **账面金额预设必须用 `PLACEHOLDER`，不能用 `TB('2701')`** —— 原 R2.4 写「以离散 `TB()` 分别声明」是错的。K0 已收口范式的理由决定性：`cell_ref` 同时是**手工覆盖键**，写 `TB()` 会让「按码取到的 0」伪装成审计师手填值，压住语义定位拿到的 `undefined` → 「本项目无此科目」与「余额为 0」不可区分（与 R3.4 自相矛盾）。已改 R2.4 + 新增 R2.8/R2.9 + Property 5。
2. **矩阵手工覆盖键的品种段用源模板中文字面，不是 key** —— 平台既有范式（G0/K0）是 `X0-1-matrix-{中文品种}-{指标key}`：品种中文名同时是上区 `E 账户/交易` 列 SUMIF 的 criteria，属源模板事实非可改文案；只有**指标**段必须是稳定 key。已改 R3.5 + Property 13。
3. **`tables` item 的描述字段名是 `content` 不是 `description`，且无 `hint` 透传通道** —— `ProcedureTableService` 以 `item["content"]` **必填**读取（写 `description` 会 KeyError），输出字段恒为 `{_key, seq, content, ref_index, phase, category, **merged}`。故源模板 G 列批注承载在 `content` 末尾的 `\n【提示】…`，新增 `hint` 字段会被静默丢弃（又一个 dead config）。已改 design + 新增 R1.9。

### 两条「锁定旧缺陷行为」的既有测试已诚实更新

修好缺陷后，两条锁定旧行为的测试必然打红 —— 这是设计意图（「修好即打红提醒移出」），不是回归：

1. `tests/test_confirmation_program_template_code.py::test_l0_f0a_falls_back_when_no_l0a_template` 原文 `assert get_template("L0A") is None` + `== "F0A"` **显式锁定缺陷前提** → 改写为 `test_l0_f0a_prefers_l0a_template`（`is not None` + `== "L0A"`），docstring 保留改写前原文与理由。
2. `tests/test_k0_formula_presets.py` 的 `KNOWN_BAD_SHEET_NAMES` 含 `("L0", "审定表L0-1"): "归属 l0 循环侧（尚无 spec 立项）…"` → 按其自带的「白名单只许变短」规则移出，并注明由本 spec Task 4 修好。

### 169 failed 的归属判定（用户 2026-08-05 要求判清）

用「把两个被改的 JSON 换回 `git show HEAD:` 版跑同一组、比对失败集合」的对照实验（替代被禁的 `git stash`）：

| 类别 | 数量 | 判定 |
|---|---|---|
| 两侧共同失败 | **170** | **预存在基线** —— 全是连库测试（`test_wp_formula_*` / `test_sign_convention_e2e` / `formula_runtime` / `test_wp_formula_roundtrip_pbt` 等），报 `sqla…` 与 `RuntimeWarning: coroutine 'Connection._cancel' was never awaited` = DB 连接与事件循环环境问题，与本改动无关 |
| 仅工作树侧失败 | 37 | **全部是本 spec 新建的 `test_l0a_program_template.py`** —— 在 HEAD 版（无 `tables.L0A`）下正确打红 = 守卫有效性证明，非缺陷 |
| 仅 HEAD 侧失败 | 3 | 逐条查清：2 条是上述「锁定旧缺陷」测试（已修）；1 条 `test_report_formula_coverage::test_bs_has_minimum_entries` 单跑即红（`_BS_SPECIAL` 69 < 70）而全量跑时通过 ⇒ **预存在的测试间污染**，且 `git status` 显示并发会话正在改 `report_formula_service.py` / `fill_report_formulas.py` / `report_config_account_names.py` → 归属并发会话，不在本 spec 半径内 |

收口验证：`test_confirmation_program_template_code` + `test_k0_formula_presets` + `test_l0a_program_template` + `test_l0_source_template_facts` + `test_l_prefill_extension` = **276 passed / 0 failed**。

### 本轮新增的三条操作教训

1. **🔴 `procedure_table_templates.json` 与 `prefill_formula_mapping.json` 是多 spec 共同改动的热点文件，本轮实测被并发会话回退过一次** —— `--apply` 成功且验证通过（`tables` 122 / L0A 命中）后，跑了一轮 254s 的全量测试，回来磁盘已变回 121 条无 L0A。→ 改这两个文件后**必须立即验证**、**不要在改完后跑长时间全量**、**收工前再验一次**；判「是否被回退」用 `get_template` 实调而非记忆。
2. **🔴 `--apply` 崩在 `UnicodeEncodeError` 不代表没写盘** —— `✅`/`❌` 在 Windows GBK 控制台 print 会抛异常，而崩点在写盘**之后** ⇒ 退出码非零但改动已落盘（与 `migration_runner` 的 `UnicodeEncodeError` 同族）。已把两个脚本的控制台 emoji 换成 `[OK]`/`[ERR]`（`description` 里的 🔴 进 JSON 不进控制台，保留）。判 apply 成败一律查数据不看退出码。
3. **🔴 `_load_templates()` 带 mtime 热重载缓存，但**判「修复是否生效」必须在 pytest 上下文里实调**** —— 本轮出现「独立探针说修好了、pytest 说没修」的矛盾，根因是磁盘已被回退而非缓存；排查手法 = 临时 `tests/test_tmp_*_probe.py` 打印 `_TEMPLATE_PATH` / 磁盘内容 / `get_template` 返回三者，一次定位（用完即删）。

### Wave 2 后端部分已交付（Task 6~8，2026-08-05）

| Task | 产物 | 验证 |
|---|---|---|
| 6 | `backend/app/services/four_table/l0_book_amounts.py`（`L0CategorySpec` × 2 + `resolve_l0_book_amounts`） | import OK；`spec is L5_SPEC/L4_SPEC` 对象身份相同；`resolve_leaf_totals`/`to_leaf_rows` 经 `inspect` 确认是同步纯函数 |
| 7 | `_inject_l0_book_amounts`（`wp_render_config_helpers.py`）+ 挂进 `wp_render_config.py`（1 个调用点） | `import wp_render_config` OK；门控早于取数；`confirmation-summary` 不在 `RENDERER_DISPATCH` |
| 8 | `backend/tests/four_table/test_l0_book_amounts.py`（33 例）+ `backend/scripts/diagnose/verify_l0_book_amounts_live.py`（只读，带 `--out`） | 33 passed；**10 项变异全红**；真实库 11 组 × 2 品种实证 |

**真实库实证（`verify_l0_book_amounts_live.py --out`）**：

- `resolved_from` 分布 `{account_chart_client: 10, account_chart_standard: 6, none: 6}` ⇒ **按科目名在本项目科目表定位生效**
- **`parent_check` 非 0 的组合 = 0** ⇒ 叶子聚合与父额勾稽全部成立
- `conflicts` = 0
- 命中品种金额全为 `0.00`，postgres 直查证实全库 `2701`/`2502`/`2702` 的 `closing_balance` 均为 `NULL` 或 `0.00` ⇒ **样本项目确实无债务循环余额**，不是取数缺陷（同 F0 那轮「全库零函证明细行」情形，如实报告不用 fixture 冒充）
- 三态可分实证：科目表无该科目 → `amount=None` + `absent_reason`；科目表有但余额 NULL/0 → `amount=0.00`

**一处实证推翻 design**：`2702 未确认融资费用` 是**独立一级科目**不是 `2701` 子科目（`account_chart` 实证 `2701` 的子科目只有 `.01/.02/.03/.99`）⇒ `LIKE '2701%'` 扫不到它，「父族聚合已净掉」的说法不成立；且 `BS-064 = TB('2701')` 本身不减它（与 H9 `BS-063 = TB('2601')-TB('2602')` 口径不同）。实现改为 `net_of_slots=()` 按 `BS-064` 口径取数，两条口径差异如实写进 `notes` 供溯源面板展示。同时把 Property 11 的判据从「源码不含四位数字」改为「取数形态断言」—— `formula_hint`/`notes` 逐字写明 `TB('2701')` 口径是**审计追溯能力**，一律禁数字会把它们一起禁掉。

### 回归判归属：four_table 17 failed → 1458 passed / 0 failed

| 类别 | 数量 | 判定 |
|---|---|---|
| **CWD 依赖** | 16 | 从 `backend/` 跑 pytest 时相对路径变成 `backend/backend/...` → `FileNotFoundError`（`test_g7_account_scope` 读 `backend/wp_templates/G/...`、`test_k_cycle_specs` 读 `backend/app/routers/wp_render_strategies/_k*.py`）。**从仓库根跑全部转绿** ⇒ 非缺陷、非本改动 |
| **真实欠账（已修）** | 1 | `test_k_cycle_formula_presets::test_formula_syntax_valid` —— K0 的两个矩阵账面金额格用 `PLACEHOLDER`，而该守卫白名单没有它（K0 spec 遗留，memory 记的「`PLACEHOLDER` 三处白名单易漏」的**第 4 处**）。根因是**双真源**：模块级 `_PREFILL_ONLY_FUNCS` 之外，函数内又硬编码一份 `known_funcs` → 补模块级常量不生效。已改为 `known_funcs = {"TB"} | _PREFILL_ONLY_FUNCS` 消除双真源 + 补 `PLACEHOLDER` |

**🔴 新增操作铁律：pytest 一律从仓库根跑** —— 从 `backend/` 跑会让 16 个用相对路径的测试假红，极易误判成回归。判「某批失败是否 CWD 依赖」的最快判据 = 换 CWD 再跑一次，失败集合归零即是。

**🔴 新增操作铁律：变异脚本的备份必须落磁盘，不能只在内存** —— 本轮第一次变异脚本被 Ctrl+C 中断，`finally` 未执行完，把「门控行被删」的变异状态留在了 `wp_render_config_helpers.py` 里；第二次变异脚本启动时把它当成了原文基线（`orig[H]`），于是「写回校验 True」而门控实际已丢。同族坑 = memory 已记的「`--apply` 被 Ctrl+C 中断但写入已提交」。→ ①备份写 `.bak` 文件并提供 `--restore` ②**共享热点文件（`wp_render_config_helpers.py` / `confirmationColumnSpec.ts` 等）的判据改用「替身字符串」在测试内验证，不做磁盘变异**（本轮已按此加 `TestInjectorGuardSelfCheck` 3 条替身自检，覆盖「门控晚于取数」与「门控整体缺失」两种缺陷形态）。

### Wave 2 前端声明件已交付（Task 9~11、13，2026-08-05）

| Task | 产物 | 验证 |
|---|---|---|
| 9 | `confirmation/l0-confirmation/l0SummaryMatrix.ts`（2 品种 × 8 指标 + `CONVERGENCE_TARGET`） | `get_diagnostics` 零诊断 |
| 10 | `l0MatrixDataSources.ts`（手工覆盖键 + 三态读取 + 诊断） | 同上 |
| 11 | `l0SummaryLowerZone.ts`（6 样本项 + 5 说明段 + 结论 + 参考结论只读 + 笔误登记） | 同上 |
| 13 | `__tests__/l0SummaryMatrix.spec.ts`（44 例）+ `__tests__/l0LowerZone.spec.ts`（27 例） | **71 passed**；**17 项变异全红** |

**metric key 沿用 G0 命名**（`book_amount` / `send_amount` / `send_ratio` / `reply_confirmed` / `reply_over_send` / `reply_over_book` / `alt_confirmed` / `reply_alt_over_book`）—— 收敛 spec 合并副本时无需再改名，同源守卫也能直接按 key 对齐。

**一处与 F0/G0 有意不同并已登记**：比例列分母为 0/非有限时 L0 返 **`0`**（忠实源模板 `IF(ISERROR(...),0,...)`），而 F0/G0 返 `null`。两处源模板同形，属既有实现选择差异 → 收敛 spec 需先吸收该差异（已写进模块 docstring 的对照表与 Property 10）。

**L0 不做动态品种可见性** —— 源模板 `G29` 为空（无 `……` 可扩位，后端守卫已固化），G0 的「有就显示没有隐藏 + 显示全部品种开关」是为其 8 品种候选全集设计的，L0 照搬会凭空引入可扩语义。守卫按源码断言不出现 `showAllCategories`/`visibleCategories`。

### 变异检验补出一处真实守卫缺口

17 项变异中 2 项初次 GREEN，逐条查清：

1. **「比例返 null 而非 0」= 变异构造无效** —— 我写的 `return 0 as number` 语义未变。改成真正 `return null as unknown as number` 后打红。
2. **「样本项 field 名漂移」= 真实守卫缺口** —— 把 `sample-6` 改名成 `sampleX` 时原守卫**未打红**：长度 / `label` / `source_ref` 三条断言都不覆盖 `field` 名。而 `field` 是**持久化键**，漂移 = 既有项目已录入内容读不回来（数据零丢失红线）。→ 补 `field` 序列逐字断言（样本 6 项 + 说明 5 项各一条），复验 3 项变异全红。

**教训**：断言「数组长度 + 展示字段」不足以钉死一个声明表 —— **持久化键必须单独逐字断言**。同族：`label`/`source_ref` 是展示与溯源，`field`/`key` 是数据契约，二者的漂移后果完全不同。

### Task 12 已交付（2026-08-05）

`confirmation/l0-confirmation/L0SummaryLowerZone.vue` —— 下区四块渲染组件。

**三条平台铁律的落法（逐条对照，避免又踩一遍）**：

| 铁律 | 本组件落法 |
|---|---|
| `fmtAmount` 是 store 成员不是模块级导出 | setup **顶层** `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`；写进函数体会静默失效，模块级 `import { fmtAmount }` 会让整页崩成「does not provide an export named」 |
| 可编辑金额只能用 `WpAmountInput` | 账面金额行用它；EP 2.13.6 的 `el-input-number` 无 `formatter` prop（该 prop 根本不存在），千分符从未生效 |
| 下区录入不得走 sheet 级 save 通道 | 组件只 `emit('save', itemId, value)`，由宿主调 `PUT /checklist-responses`；走 sheet 级 `emit('save', 载荷)` 会把整个 sheet 的 `html_data` 覆盖成 `{itemId, value}`，一次点击丢光上区函证行并让 sheet 退化成「旧格式只读」 |
| 全部 ref 声明在 watch 之前 | `textValues` / `manualOverrides` 在 `watch(() => props.responses)` 之前声明（TDZ：watch 的依赖数组在 setup 期即求值，不需要 `immediate` 也会炸） |
| 取数诊断必须有渲染出口 | 三个 `el-alert`（errors / conflicts / parentCheckIssues）；F0 那轮「只收集不渲染」掩盖了一个 http 客户端错配 P0 |
| UI 全中文化 | `resolved_from` 经 `resolvedFromLabel()` 翻中文；三态文案「未取数（可手填）」/「本项目无此科目」/ 数值 |

**验证**：`get_diagnostics` 零诊断 + **Vite transform 四文件全 200**（`get_diagnostics` 查不出漏 import 与 SFC 结构损坏，必须用 transform 收尾）+ L0 前端 `npx vitest run l0` = **5 文件 131 passed**（含既有 `useAlternativeL05Data` 34 例 / `l0-integration` 20 例 / `useL0FormulaEngine.pbt` 6 例零回归）。

`responses` 契约：必须由宿主从 **`/checklist-responses`（已持久化）** 拉取，不得来自 `responses_snapshot`（含 prefill 种子 → 会把种子当成审计师录入）。

### Wave 3 阻塞（2026-08-05 20:45 复测，**不得开工**）

`f0-confirmation-linkage-and-structural-enhancement` 实测 **inprog=2 / queued=3**，`tasks.md` mtime **08-05 20:39**（分钟级刷新 = 并发会话正活跃）。按本 spec 的 `blocking` 条件与 K0 spec 的 R11.5，Wave 3（Task 14~18）**不得开工** —— 那五个任务全碰七枢纽共享件，其中 `GtConfirmationSummary.vue` 与 K0 spec Task 10 是同一刀口。

**本轮已实测两次并发回退**，佐证该纪律必要：
1. `procedure_table_templates.json` 与 `prefill_formula_mapping.json` 的 `--apply` 结果被回退（跑完一轮 254s 全量测试回来即消失）
2. `wp_render_config_helpers.py` 的门控行丢失（自己的变异脚本被 Ctrl+C 中断留下的残留，同一类风险）

**当前 Active spec 快照**（供下个会话判断何时可开工 Wave 3）：

| spec | 进度 | 中断标记 | mtime |
|---|---|---|---|
| `f0-confirmation-linkage-and-structural-enhancement` | 139/144 | **inprog 2 / queued 3** | 08-05 20:39 |
| `k0-confirmation-source-alignment` | 7/18 | 无 | 08-04 15:18（静置） |
| `l0-confirmation-source-alignment`（本 spec） | **13/20** | 无 | 08-05 20:45 |
| `d-cycle-four-table-extraction-and-disclosure-completion` | 0/30 | 无 | 08-05 20:00（并发新建） |
| `sampling-evaluation-and-governance-closure` | 10/19 | 无 | 08-05 19:59（并发在跑） |
| `sampling-compliance-closure` | 24/25 | 无 | 08-04 22:27 |
| `report-config-account-code-integrity` | 12/12 ✅ | 无 | 08-05 20:05 |

### 收工核验（防并发回退）

`tmp_l0_final_verify.py` 逐项核实 26 条，**全部在位**：`tables.L0A`（12 items / 条目数 122）· L0 预设三项纠正 · 13 个新增文件 · 注入器与门控 · 挂载点 1 个 · 两处旧行为锁定测试已更新 · 两个幂等脚本 `--check` exit 0。

**核验脚本自身踩了一次「未剥注释」的坑**：断言「K0 白名单已移出 L0」时用裸 `'("L0", "审定表L0-1")' not in src`，而移出时**保留了原字面作留证注释**（`# ("L0", "审定表L0-1") 已于…`）→ 误报「被回退」。改为剥注释后判定 + 另加一条「留证注释仍在」的正向断言（防将来被静默删掉）。与 memory 已记的「读源码型守卫必须先 `stripComments()`」同族 —— **连核验脚本也适用**。

### Wave 3 已交付（Task 14~18，2026-08-05）

| Task | 产物 | 验证 |
|---|---|---|
| 14 | `confirmationColumnSpec.ts` 加 L0 键（variant `send_channel`+`l0_row_conclusion` / 剔三列 / 13 处 label 覆盖 / `diff_ref_index` 展示 L0-4） | `l0ColumnAlignment.spec.ts` 46 例 |
| 15 | `ConfirmationDetail.vue` 加 `send_memo` 只读呈现分支（`data-testid="send-memo-legacy-readonly"`） | 同上（Property 18） |
| 16 | `GtConfirmationSummary.vue` 挂 `<L0SummaryLowerZone v-if="isL0">` + 共享 `ConfirmationSampling` 改 `v-if="!isL0"` | `l0LowerZoneWiring.spec.ts` 17 例 |
| 17 | `wp_render_config.py` 复合键 skip（接在既有三条之后）+ `wp_code_overrides.json` 加 `L0-函证差异检查表（示例）` → skip | `test_l0_render_sheets.py` 23 例 |
| 18 | `cycleConfirmationMeta.L0` 三处笔误 `indexTypoNote` + `alternativeBlockManifest.L05` 三处 title 对齐源模板 | `l0SheetMeta.spec.ts` |

**🔴 Task 16 的落法与 design 不同（有意，已成裁决）**：design 写「`ConfirmationSampling.vue` 加 `isL0` 门控（6 项，与 `isG0` 同构）」，实际改为 **`v-if="!isL0"` 把共享组件对 L0 整体隐藏** —— L0 的 6 项样本选择在**下区专属组件内**（源 `L0-1!J28` 段属该 sheet 下区，落 `checklist_responses` 的 `L0-1-lower-sample-*`），两处都渲染会让同一语义有两个录入口（一个落 `SamplingConfig`、一个落 checklist）= 双真源。G0 那 6 项走的是共享组件，故 `isG0` 分支保留不动，其余六枢纽逐字不变。

### Wave 4 已交付（Task 19~20，2026-08-05）

**Task 19 守卫 + CI**：

| 产物 | 规模 | 变异检验 |
|---|---|---|
| `backend/tests/test_l0_render_sheets.py`（Property 25~27） | 23 例 | 4/4 全红 |
| `l0ColumnAlignment.spec.ts`（Property 18~24 / 36） | 46 例 | 7/7 全红 |
| `confirmation/__tests__/l0LowerZoneWiring.spec.ts`（Property 17） | 17 例 | 5/5 全红 |
| CI `l0-confirmation-alignment`（8 步）+ `l0-confirmation-frontend`（4 步） | jobs 122 | YAML 可解析 |

**Task 20 回归**：后端 `-k "l0 or L0 or confirmation or four_table or render_config"` **1796 passed / 0 failed**（从**仓库根**跑）· 前端 L0 域 **273 passed / 0 failed** · 两个幂等脚本 `--check` exit 0。

**前端 confirmation 全域 11 个失败判定为并发会话**：用「把改动文件换成 `git show HEAD:` 版跑同一组」对照实验 —— 两侧失败集合**逐条相同（17 vs 17，差集 0）**；三个失败文件（`LinkageCompletion` / `importFromSummary` / `materialityAutoFetch`）零引用本轮符号，且 `useMaterialityAutoFetch.ts` **压根不存在**（测试已建、实现未写）。

**Task 20 浏览器实测（Playwright 独立实例，项目 `0ec33ac9` / wp `e2e46a40`，入口 `wp_code=L0` 整册 9 sheet）**：

| 项 | 结果 |
|---|---|
| 页签集合 | 恰 **9 个**函证 sheet，hidden 的 `函证差异检查表（示例）` 已不渲染（Task 17 生效） |
| 下区四块 | 全部渲染；矩阵**恰 2 品种** × 8 指标，label 逐字为源模板 |
| 审计说明序号 | 显示 **「三、」** 且带「源模板序号笔误」标记（源字面「二、」） |
| 两格合并 | `W30`+`W31` 渲染成完整句（「界定误差构成条件：［…（）万元，并且…提供相应依据］」） |
| `S33` 索引号 | 「（L0-6）」保留未被当笔误改掉 |
| `J33` 括注 | 作提示文本，非独立录入项 |
| 矩阵 SUMIF 联动 | 录两行 → 长期应付款 **1,000,000.00** / 应付债券 **2,000,000.00** 各归其列；科目列为空时两列均 `-`（按「账户/交易」聚合正确） |
| 比例列 | 回函 1e6 → `回函可确认金额占发函金额` = **100.00%** |
| 手工覆盖 | 输 `3000000` → 显示 **`3,000,000.00`**（`WpAmountInput` 千分符生效） |
| 覆盖键落库 | **`L0-1-matrix-长期应付款-book_amount`** —— 品种中文字面 + 指标稳定 key（Property 13） |
| 下区落库 | `L0-1-lower-sample-1` / `-audit-note-1` / `-conclusion` 三类键正确 |
| 键空间 | 上区落 `html_data['函证结果汇总表L0-1']`，与下区 checklist 不重叠（Property 16） |
| 后端注入器（HTTP 活体） | `sheets` 恰 9；`l0_book_amounts` **只在 `函证结果汇总表L0-1`** 命中（门控正确）；两品种取到值 |
| 真实库直跑 | 11 组「项目×年度」× 2 品种：`parent_check` 全 0 / `conflicts` 0 / `resolved_from` = {client:10, standard:6, none:6} / 三态可分（`None` vs `0.00`） |

**数据已逐字节复原**：`parsed_data` 回到基线 `md5=b0e8fbb91bfd523346e66c2e4b38ccfa` / `plen=75` / `jsonb_typeof=object`；`checklist_responses` 仅剩基线那条 `L0-review-session-20260725075145`，4 条实测键已删。

### 实测挖出 3 个既有缺陷（非本 spec 引入，已登记归属）

| 缺陷 | 实证 | 归属 |
|---|---|---|
| **行详情面板不套用 L0 label override，且已剔除的三列仍渲染** | 面板 label 是 BASE 的「科目」「函证金额」「地址」（应为「账户/交易」「金额」「收件地址」），且「联系人/联系电话/币种」仍在 —— 说明 `ConfirmationDetail.vue` 未消费 `resolveConfirmationColumns(cycle)`，自带一份写死表单 | 七枢纽共享，另立 spec（本 spec 的列守卫只覆盖 grid 列集，面板是第二处真源） |
| **「账户/交易」下拉 22 项无「长期应付款」「应付债券」** | 只有短期借款/长期借款；靠 `allow-create` 打字才能录入 → 矩阵品种维度默认取不到 | 与 H0 那轮「下拉无 H 类科目」同源，字典表侧 |
| **`alt_confirmed`（替代后可确认金额）在详情面板无录入位** | 面板只有「替代不可确认」，故矩阵第 7 行「替代测试确认金额」无法从面板填 | 七枢纽共享（F0 那轮已知 Y 列语义，此处是录入口缺失） |

另**复现**已登记 P0：**完整表格视图编辑永不落库**（`handleGridUpdate` 只 `updateField` 不 `emit('save')`）—— 本轮在该视图录的两行 `rows: []`，切回列表视图即丢，无任何提示。

### 本轮新增操作教训（已同步 memory）

1. **`jsonb` 列写 dict 必须 `CAST(:v AS jsonb)` + `json.dumps`** —— 直接 bind dict 会写成 **JSON 字符串标量**（`jsonb_typeof='string'`），`SELECT` 出来带一层转义，`->>'key'` 全部取不到。判据只能是 **`jsonb_typeof(col)='object'`**，比对 md5 会被这层转义骗过（我在复原实测数据时踩中，把基线 75 字节写成 83 字节的转义串）。
2. **`row.t` 取不到列** —— `Row.t` 是 SQLAlchemy 2.x 的**已废弃元组属性**（返回整行），与名为 `t` 的列冲突时静默返回 tuple 让判定失败并 abort。列名一律避开 `t`/`c`/`_t`，或用 `row[0]` 索引。
3. **跨行锚点在 CRLF 文件里必失配** —— 含 `\n` 的多行锚点用于变异脚本会 ANCHOR-MISS；一律行级定位（`splitlines()` + 锚点行号 + 相对偏移）。
4. **`toContain('<Foo')` 抓不住「删渲染」** —— 必须带标签名边界 `<Foo(?=[\s/>])`。
5. **固定字符窗口截块** —— 我用 400 字符窗口取标签开标签，实际 430 字符 → `indexOf('>')` 返 -1 → 空串 → 断言必红。改按真实边界（配对/行级）定位。
6. **声明表守卫必须逐字断言持久化键** —— `field`/`key` 是数据契约，`label`/`source_ref` 只是展示；长度 + label 三条断言全绿也拦不住 `sample-6` → `sampleX` 这种会让既有录入值失联的漂移。

### Wave 3/4 已交付 + 浏览器实测通过（Task 14~20，2026-08-06）

**开工前的磁盘实证纠正**：Task 14 / 15 / 16 / 18 的代码早已落盘（tasks.md 标记滞后），Task 17 的复合键 skip 代码也在但未勾选 → 按代码实证勾正，本轮真正新做的是 **Task 19 全套守卫 + CI + Task 20 实测**。

| Task | 产物 | 验证 |
|---|---|---|
| 19 | `backend/tests/test_l0_render_sheets.py`（Property 25~27，23 例） | 23 passed；**4 项变异全红**（删复合键 / 复合键改裸键 / 改 L0-1 组件 / 复合键错循环） |
| 19 | `l0ColumnAlignment.spec.ts`（Property 18~24 / 36，49 例） | 49 passed；**7 项变异全红**（伪列复活 / 撤销三列剔除 / 行结论 group 改回 send_memo / diff_ref_index 退回 F0-4 / 函证类型改绑渠道 / label 覆盖污染 BASE / 重新引入重复键） |
| 19 | `confirmation/__tests__/l0LowerZoneWiring.spec.ts`（Property 17，17 例） | 17 passed；**5 项变异全红**（标签改名=删渲染 / 删 v-if 门控 / isL0 恒真 / 样本选择双录入口 / Sampling 加 isL0 分支） |
| 19 | CI `l0-confirmation-alignment`（8 步）+ `l0-confirmation-frontend`（4 步） | YAML 可解析，122 jobs，两 job 在册 |
| 20 | 回归 + 浏览器实测 + 数据复原 | 见下 |

**顺带修掉一个平台级真实缺陷（本轮最有价值的产出）**：`confirmationColumnSpec.ts` 的 `VARIANT_COLUMN_DEFS` 里 **`l0_row_conclusion` 被定义了两次**（123 行与 163 行，内容相同）。JS 对象字面量重复键静默取后者 —— `get_diagnostics` / vitest / Vite transform **三层全绿查不出**。删前一处后键数 19→18、零重复；新增守卫「运行时键数 == 源码顶层键数」+「无重复键」双向锁死（变异复现即打红）。

**回归**：后端 `-k "l0 or L0 or confirmation or four_table or render_config"` = **1796 passed / 0 failed**（从仓库根跑）；前端 L0 域 **273 passed / 0 failed**；两个幂等脚本 `--check` exit 0。

**前端 confirmation 全域 11 个失败已判归属并发会话**（用「把改动文件换成 `git show HEAD:` 版跑同一组」的对照实验替代被禁的 `git stash`）：两侧失败集合**逐条相同（17 vs 17，差集 0）** ⇒ 本改动造成 0 条。三个失败文件（`LinkageCompletion` / `importFromSummary` / `materialityAutoFetch`）均零引用本轮符号，且 `useMaterialityAutoFetch.ts` **压根不存在**（测试文件已建、实现未写 = 并发会话在写）。

### 实测（三件套齐全，项目 `0ec33ac9` / wp `e2e46a40`，整册 `wp_code=L0` 9 sheet）

**HTTP render-config 三项一次全对**：`sheets` **恰 9 项**（Task 17 复合键 skip 生效，hidden 的 `函证差异检查表（示例）` 已不渲染）· 注入器 `l0_book_amounts` **只在 `函证结果汇总表L0-1` 命中**（wp_code 门控正确，其余 8 sheet 零影响）· 两品种均取到值 `{长期应付款: 0.0, 应付债券: 0.0}`。

**真实库直跑（11 组「项目×年度」× 2 品种）**：`parent_check` 非 0 组合 **0**（叶子聚合与父额勾稽全部成立）· `conflicts` **0** · `resolved_from` 分布 `{account_chart_client: 10, account_chart_standard: 6, none: 6}` ⇒ 按科目名在本项目科目表定位生效 · **三态可分实证**：科目表无该科目 → `amount=None` + `absent_reason`；有科目但余额 NULL/0 → `amount=0.00`。

**浏览器实测（Playwright 独立实例）逐项通过**：

| 验证项 | 结果 |
|---|---|
| 页签 | 9 个函证 sheet 全在，hidden 表不渲染 |
| 下区四块渲染 | 一、函证情况 / 二、样本选择 / 三、审计说明 / 四、审计结论 全部挂载 |
| 矩阵结构 | **恰 2 品种**（长期应付款 / 应付债券）× 8 指标，label 逐字为源模板 |
| 矩阵联动 | 录第 1 行（科目=长期应付款 / 金额 1,000,000）→ 该品种列出 1,000,000.00，应付债券列仍 `-`；录第 2 行（应付债券 / 2,000,000）→ 两列各归其位 **1,000,000.00 / 2,000,000.00**（SUMIF 按品种聚合正确） |
| 比例列 | 回函金额 1,000,000 → `回函可确认金额占发函金额` = **100.00%**；分母为 0 的三列显 **0.00%**（源模板 `ISERROR` 兜底口径，不显 `-` 不报错） |
| 序号笔误 | 「三、审计说明」显示**「三、」**且带「源模板序号笔误」标记（源字面为「二、」） |
| 两格合并 | `W30`+`W31` 渲染成完整句子「界定误差构成条件：［…（）万元，并且…提供相应依据］」，不是半句话 |
| 正确索引号 | `S33` 的「（L0-6）」保留未被当笔误改掉 |
| `J33` 括注 | 作提示文本呈现，不是独立录入项 |
| 12 个 textarea | 6 样本 + 5 说明 + 1 结论全在，placeholder 逐条为源模板示例（只作 placeholder 不预填） |
| 金额控件 | 手工覆盖输 `3000000` → 显示 **`3,000,000.00`**（`WpAmountInput` 千分符生效） |
| **下区落库** | `L0-1-lower-sample-1` / `L0-1-lower-audit-note-1` / `L0-1-lower-conclusion` 三类键正确写入 |
| **矩阵覆盖键落库** | **`L0-1-matrix-长期应付款-book_amount`** —— 品种段中文字面 + 指标段稳定 key，与 Property 13 及 G0/K0 键形同构 |
| 键空间不冲突 | 上区载荷落 `html_data['函证结果汇总表L0-1']`，与下区 `checklist_responses` 键空间零重叠（Property 16 成立） |

**数据已逐字节复原**：`parsed_data` `jsonb_typeof=object` / `plen=75` / **`md5=b0e8fbb91bfd523346e66c2e4b38ccfa`（与实测前基线完全相同）**；`checklist_responses` 仅剩基线那条 2026-07-24 的 review-session，4 条实测键 0 残留。

### 实测挖出的三个既有缺陷（本 spec 范围外，已登记归属）

1. **行详情面板不套用 L0 label override 且不剔除已剔除列** —— 面板显示的是 BASE 的「科目」「函证金额」「地址」（应为「账户/交易」「金额」「收件地址」），且**已从列渲染剔除的三列（联系人 / 联系电话 / 币种）仍在面板渲染**。根因 = `ConfirmationDetail.vue` 自行铺 `el-form-item` 而不消费 `resolveConfirmationColumns(cycle)` ⇒ **列 spec 与详情面板是两套真源**。影响全部七枢纽（G0/H0 的 override 同样落不到面板），属共享组件级改造。
2. **科目下拉无 L 类科目** —— 22 项里没有「长期应付款」「应付债券」（只有短期借款 / 长期借款），靠 `allow-create` 打字才能录入。与 H0 那轮「账户/交易下拉无 H 类科目」同源（`confirmation_account_type` 字典缺 L 类取值）。
3. **`alt_confirmed`（替代后可确认金额）在详情面板无录入位** —— 面板只有「替代不可确认」，故矩阵第 7 行「替代测试确认金额」无法从详情面板填。而源模板 `Y` 列就是它，矩阵 `E36=SUMIF(...,$Y$8:$Y$27)` 依赖它。

另**复现了已登记 P0**「完整表格视图编辑永不落库」（`handleGridUpdate` 只 `updateField` 不 `emit('save')`）—— 在完整表格视图录的两行切回列表视图即丢，落库 `rows: []`。七枢纽共享，修法需裁决。

### 本轮新增的四条操作教训（已同步 memory）

1. **🔴🔴 JS/TS 对象字面量重复键静默取后者，四层验证全查不出** —— 判「注册表是否有重复键」必须**扫源码顶层键 vs `Object.keys()` 运行时键数**，两者不等即有重复。
2. **🔴 复原 JSONB 列禁用 `json.dumps` 后当字符串绑参** —— 会写成 JSON **字符串标量**（`jsonb_typeof='string'`，外层带引号且内部转义），看着"内容对"但形态已坏。正解 `CAST(:v AS jsonb)`；**验收判据必须是 `jsonb_typeof(col)='object'`**，不能只比 md5 或肉眼看内容。
3. **🔴 `Row.t` 会取到整行元组（列名与 SQLAlchemy 属性冲突）** → 判定恒失败并 abort。用 `row[0]` 索引取值。
4. **🔴 Playwright 分步调用之间 session 会丢**（token 在 sessionStorage）→ 登录 + 导航 + 点签 + 读取必须压成**单个原子脚本**；`run_code_unsafe` 只接受 `async (page) => {...}` 形式且对某些语法（`;` 结尾、箭头函数体内 `await` 声明）敏感。

### 收口状态

**20/20 全完成**，可归档。归档分类 = `_archive/11-confirmation-d0-module/`（与 `g0-confirmation-source-alignment` / `h0-confirmation-source-fidelity-and-linkage` / `confirmation-orphan-and-amount-format-closure` 同目录）。
