# Implementation Plan: N2-6 增值税测算表源模板对齐（方案 B + per-tax 现算）

## Overview

把 N2-6 从自造「按月/季税率矩阵」改造为源模板四段式测算表，矩阵降级为附加分析区；
并把 `adjudicationVsCalcTables` 的 per-tax 键读取改为按 `taxType` 现算。

用户已确认口径（2026-07-31）：**方案 B**（四段为主 + 矩阵作附加分析区）、**per-tax 改现算**。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "纯函数引擎与常量",
      "tasks": ["1.1", "1.2"],
      "parallel": true
    },
    {
      "wave": 2,
      "name": "数据层 composable",
      "tasks": ["2.1", "2.2", "2.3", "2.4"],
      "depends_on": ["1.1", "1.2"]
    },
    {
      "wave": 3,
      "name": "组件四段 UI + 附加区降级",
      "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5"],
      "depends_on": ["2.1", "2.2", "2.3", "2.4"]
    },
    {
      "wave": 4,
      "name": "联动改造",
      "tasks": ["4.1", "4.2"],
      "depends_on": ["2.1"]
    },
    {
      "wave": 5,
      "name": "守卫",
      "tasks": ["5.1", "5.2", "5.3"],
      "depends_on": ["3.1", "3.2", "3.3", "3.4", "3.5", "4.1", "4.2"]
    },
    {
      "wave": 6,
      "name": "验证与实测",
      "tasks": ["6.1", "6.2", "6.3"],
      "depends_on": ["5.1", "5.2", "5.3"]
    }
  ]
}
```

## Tasks

## 1. 纯函数引擎与常量（wave 1）

- [x] 1.1 新建 `composables/useN2VatSourceEngine.ts`（零依赖 leaf）
  - 实现 `calcDeclarationDiff` / `calcTaxableRevenue` / `calcOutputTax` / `calcInputTax`
  - 实现跨段 `calcOutputVariance`（源模板 F30）/ `calcInputVariance`（源模板 F39）
  - 实现 `calcVatPayableFromDeclaration`（R6 口径 = C17 − C18）
  - `parseNum` 带 `Number.isFinite` 守卫（拒 `Infinity`/`1e400`，防整表 NaN）
  - 每个函数 JSDoc 写明源模板单元格与公式原文
  - _Requirements: 1.3, 2.3, 2.6, 3.3, 3.5, 6.2_

- [x] 1.2 新建固定项常量（放同文件或 `n2VatSourceConstants.ts`）
  - `N2_VAT_DECLARATION_ITEMS`（10 项，label 逐字取源模板 R12~R21，含序号前缀与全角标点）
  - `N2_VAT_SPECIAL_ITEMS`（4 项，逐字取 R42~R45）
  - 导出 `N2_VAT_BOOK_OUTPUT_KEY='output-tax'` / `N2_VAT_BOOK_INPUT_KEY='input-tax'`（供跨段引用，禁散落字面量）
  - _Requirements: 1.1, 1.5, 4.1, 4.2_

## 2. 数据层 composable（wave 2）

- [x] 2.1 新建 `composables/useN2VatSourceCalc.ts` 骨架 + （一）申报表核对
  - `declarationRows` computed（10 固定项 + 录入值 merge + `diff` 派生）
  - `bookOutputTax` / `bookInputTax` computed（供（二）（三）跨段引用）
  - `updateDeclaration(key, field, v)`；`_currentRaw` 只物化 `{key, book, declared, reason}`
  - item_id `N2-6-declaration-rows`
  - _Requirements: 1.1, 1.2, 1.3, 1.5_

- [x] 2.2 （二）销项测算数据层
  - `outputRows`（派生 `taxableRevenue`/`outputTax`）/ `outputTotal`（4 列，无税率合计）
  - `pendingOutputTax` + `setPendingOutputTax`
  - `outputVariance`（调 `calcOutputVariance`，带 `formula` 源模板原文）
  - `addOutputRow(variety)` / `removeOutputRow` / `updateOutputRow`
  - item_id `N2-6-output-rows` / `N2-6-output-pending`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 2.3 （三）进项测算数据层
  - `inputRows`（派生 `inputTax`）/ `inputTotal`（2 列）
  - `inputAdjust` + `setInputAdjust`（三调节项）
  - `inputVariance`（调 `calcInputVariance`）
  - 动态行增删改
  - item_id `N2-6-input-rows` / `N2-6-input-adjust`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 2.4 （四）特殊情况 + R6 联动写入
  - `specialRows`（4 固定项）/ `updateSpecialRow`
  - `syncVatPayable()` 写 `N2-6-vat-payable`，值取 `calcVatPayableFromDeclaration(bookOutputTax, bookInputTax)`；注释写明 R6 依据与「不回退附加区」
  - item_id `N2-6-special-rows`
  - _Requirements: 4.1, 4.2, 4.3, 6.1, 6.2, 6.3_

## 3. 组件四段 UI + 附加区降级（wave 3）

- [x] 3.1 `N2TabVatCalc.vue` 接入 `useN2VatSourceCalc` + 审计目标区
  - 保留既有 `useN2VatCalc` 接入（附加区仍用）
  - 审计目标 `el-alert`（源模板 R6~R8 三条原文）
  - 源模板方法论上下文块（琥珀色左边线）
  - _Requirements: 1.1_

- [x] 3.2 （一）申报表核对区 UI
  - 10 固定项表格；账面/申报表 金额列用 `WpAmountInput`（千分符，禁 `el-input-number :formatter`）
  - 差异列灰底 auto + 虚线下划线 tooltip 标注 `差异 = 账面 − 申报表`
  - 差异 ≠ 0 行异常色 + 原因列 `el-input` 用 `@input` 回写（`@change` 会抹键入）
  - 无增删行按钮
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 3.3 （二）销项测算区 UI + 差异结论
  - 动态行表格（新增走 `ElMessageBox.prompt` 输入品种）
  - 派生列灰底 auto；税率 `el-select` 6 档
  - 合计行 + 待转销项税额录入
  - 差异结论紧凑单行 bar（`isMatch` ✓/⚠ tag + 公式 tooltip 溯源 + `GtIndexChip` 指向（一））
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 3.4 （三）进项测算区 UI + 差异结论
  - 同 3.3 范式；三调节项独立录入块
  - 差异结论 bar（公式 tooltip 写 `F39` 原文）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3.5 （四）特殊情况检查区 + 附加分析区降级 + 说明结论
  - （四）4 固定项金额录入；非 0 时提示需在审计说明说明会计处理
  - 把既有按月/季矩阵整体下移到四段之后，标题显式写「审计分析（不在源模板）」+ 说明其不参与源模板勾稽
  - 审计说明 / 审计结论 `el-card`（各带 AI 辅助 + 复核按钮，AI 走 `/ai/generate-text`，`context` 值全字符串）
  - 编制提示 `details` 折叠置底
  - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 5.4_

## 4. 联动改造（wave 4）

- [x] 4.1 `useN2CrossSheet.adjudicationVsCalcTables` 改按 taxType 现算
  - 删 `adjudicationKeys` per-tax 映射
  - 读 `N2-1-adjudication-rows` → `_normalizeTaxNameForN4` 归一 → `_adjRowEndAudited` 现算
  - 与 `TAX_CALC_TABLE_MAP` 逐税种比对；注释写明「不补 per-tax 写入点以免双真源」
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 4.2 校验 `vatToSurtax` 链路端到端
  - 确认 `N2-6-vat-payable` 由 2.4 写入后 `vatToSurtax.base` 取到
  - 组件在（一）数据变化后调用 `syncVatPayable()`（watch 实际数据，不用 `_xxxMounted` 一次性防护）
  - _Requirements: 6.1, 6.2, 6.3_

## 5. 守卫（wave 5）

- [x] 5.1 新建 `__tests__/n2VatSourceEngine.spec.ts`
  - 逐公式定值断言 + 跨段 F30/F39 源模板算例
  - PBT 恒等式（生成器收敛金额域，禁无界 float）
  - _Requirements: 8.2_

- [x] 5.2 新建 `__tests__/n2VatSourceContract.spec.ts`
  - 固定项 label 逐字比对（测试内写死源模板字面量）
  - 源码断言 `_currentRaw` 不含派生键
  - 附加分析区三键未被改写
  - 解构键集 ⊆ 返回键集（含 `stripComments` 自检）
  - _Requirements: 8.1, 8.3, 8.5_

- [x] 5.3 扩展 `__tests__/n2CrossSheetContract.spec.ts`
  - 6 税种喂审定行后 `adjudicationVsCalcTables` 全部非 0（反假绿）
  - 源码无 `N2-1-{tax}-audited` 字面量 + 白名单清空
  - `N2-6-vat-payable` 口径断言
  - _Requirements: 8.4_

## 6. 验证与实测（wave 6）

- [x] 6.1 自动化验证
  - 新增 spec 全绿；`composables/__tests__` + `n2` 全量回归（基线：8087/8092，4 失败为 L4/F3/F5/H4 预存在）
  - 改动文件 `get_diagnostics` 零诊断 + Vite transform 200
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 6.2 浏览器实测四段与联动
  - 四段渲染、公式实时派生、两处差异结论正确
  - N2-6 → N2-8：录（一）数据 → `N2-6-vat-payable` 落库 → N2-8 计税依据取到
  - 附加分析区仍可用且不产生异常提示
  - _Requirements: 9.1, 9.2_

- [x] 6.3 实测交叉验证 6 项 + 数据复原
  - 录 N2-1 六税种审定行 → `adjudicationVsCalcTables` 6 项均取数（改造前恒 0）
  - postgres 只读比对落库键与值
  - 测试数据全部复原；更新 tasks/INDEX/memory（未验证项不得标绿）
  - _Requirements: 9.3, 9.4_

## Notes

- **源模板唯一权威** = `backend/wp_templates/N/N2 应交税费.xlsx` 的 `增值税测算表N2-6`（已核 `数据/致同通用…` 参考副本字节一致 159454）。禁按"常识"造列造行。
- **本 spec 与既有 staged 改动的关系**：N2 主体源对齐（24 文件 +5086/−2325）已在飞未提交，其 checklist「文件9 N2TabVatCalc 补(二)(三)」未执行且未规划(四) → 本 spec 是该缺口的正式收口，范围更完整（含(一)(四)与 per-tax）。
- **不要改 `useN2VatEngine.ts`**（`calcOutputVat`/`calcPayableVat`/`calcVatBurdenRate`）—— 附加分析区仍在用，改签名会波及既有测试。
- **金额控件**一律 `WpAmountInput`；`el-input-number :formatter` 在 EP 2.13.6 是空操作（千分符从不生效，已双证）。税率/比例**不得**套用金额控件。
- **派生列禁持久化**：D1 曾因存 `ratio` 导致「按组合计提坏账准备 162.50%」错值随同步进附注。
- **动态行新增须先命名**（`ElMessageBox.prompt`），否则会产出无名占位行。
- **保存失败必须提示**，禁纯 `catch {}`（否则界面有值、库里没有，无人察觉）。
- **改完必查解构键集**：本会话已实证 `N2TabDetail.vue` 解构 `useN2Detail16` 不存在的 `seedDefaultRows` + 调用未声明 `syncSummary()` → 运行时 TypeError，而 Volar/Vite/vitest 8092 例全绿都查不出。
- **实测手法**：Playwright MCP 断连时用 chrome-devtools MCP（`navigate_page`/`fill_form`/`evaluate_script`）+ postgres MCP 只读比对；底稿 URL `/projects/{pid}/workpapers/{wpId}/edit`；登录 `admin`/`admin123`；HMR 旧错误覆盖层会残留，判真实状态先 reload。
- **并发会话风险**：`useN2CrossSheet.ts` 本会话刚改过（#2 修复），wave 4 再改时先确认落盘真相（用 python 读文件，`read_file` 对刚改过的文件可能返回陈旧版本）。
