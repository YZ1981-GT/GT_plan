# Implementation Plan: E1 货币资金各 sheet 内容完整性补全

## Overview

对照源模板 `基础数据/致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md/E货币资金循环/E货币资金底稿模板库.md`，逐个核对 E1 的 18 个前端 tab 组件，补全缺失的标准内容。

**每个 sheet 的"应有内容"标准清单**（对照源模板）：
1. **审计目标** el-alert（源模板"一、审计目标"）— 蓝色 info alert
2. **编制提示** details 折叠（源模板"提示/编制说明"）— CAS依据+填写要点
3. **主表格**字段完整（对照源模板"三、XX表"的列，不能少列）
4. **审计说明** el-card + autosize textarea + 🤖AI辅助（源模板"四、审计说明"）
5. **审计结论** el-card + autosize textarea + 🤖AI辅助（源模板"五、审计结论"）
6. **tab-toolbar**（GtIndexChip canonical value="wp:E1-X" + 共N行tag）

**标准修复模式**（参照 E1TabAdjudication 已补的审计说明/结论）：
- item_id 命名：`E1-{sheet}-audit-note` / `E1-{sheet}-audit-conclusion`
- onMounted 从 props.allResponses 恢复
- save 走 props.saveImmediate
- AI 走 aiGenerateNote（如组件已有 composable AI）或跳过 AI 按钮（组件无 AI composable 时不臆造）

**边界**：
- 只补内容，不改数据流/composable 逻辑
- 组件已有的审计说明/结论不重复加
- 无 AI composable 的 tab 只加纯 textarea（不臆造 AI 按钮）
- get_diagnostics 每个改动文件必须零错误

## Tasks

- [x] 1. 核心明细组（E1-2/E1-3/E1-4）
  - [x] 1.1 E1TabCashDetail(E1-2现金明细) 对照源模板补全：审计目标alert/编制提示details/审计说明+结论textarea/币种表字段(期初/本期增减/期末原币/汇率/折算/调整/审定/备注)/存放境外行
  - [x] 1.2 E1TabBankDetail(E1-3银行明细) 补全：审计目标/编制提示/审计说明+结论/银行存款明细表(开户行/账号/币种/账面/对账单/调节后/是否受限)+其他货币资金明细表(7类:汇票/本票/信用卡/信用证保证金/存出投资款/外埠/其他)
  - [x] 1.3 E1TabDigitalCurrency(E1-4数字货币) 补全：审计目标/编制提示/审计说明+结论/数字货币表(币种/数量/单价/公允价值/期末)
  - _对照源模板 E1-2/E1-3/E1-4 章节_

- [x] 2. 调整调节盘点组（E1-5/E1-6/E1-7/E1-8）
  - [x] 2.1 E1TabAdjustment(E1-5调整分录) 补全：审计目标/编制提示/审计说明+结论
  - [x] 2.2 E1TabReconciliation(E1-6余额调节) 补全：审计目标/编制提示/审计说明+结论(已有差异计算保留)
  - [x] 2.3 E1TabCashCount(E1-7/E1-8盘点rmb/fx) 补全：审计目标/编制提示/审计说明+结论(盘点差异保留)
  - _对照源模板 E1-5/E1-6/E1-7/E1-8 章节_

- [x] 3. 账户核对组（E1-9/E1-10/E1-11）
  - [x] 3.1 E1TabCertificateCount(E1-9存单盘点) 补全：审计目标/编制提示/审计说明+结论/存单表(存单号/银行/存款人/账号/存款类型/存入日/到期日/金额/利率/是否质押/质押事项/结果已见未见/备注)
  - [x] 3.2 E1TabAccountList(E1-10账户核对) 补全：审计目标/编制提示/审计说明+结论
  - [x] 3.3 E1TabAccountCommitment(E1-11承诺书) 补全：审计目标/编制提示/审计说明+结论
  - _对照源模板 E1-9/E1-10/E1-11 章节_

- [x] 4. 分析检查组（E1-14/E1-15/E1-18/E1-19）
  - [x] 4.1 E1TabAnalysis(E1-14分析表) 补全：审计目标/编制提示/审计说明+结论
  - [x] 4.2 E1TabInterestAnalysis(E1-15利息月度分析) 补全：审计目标/编制提示/审计说明+结论(利息差异保留)
  - [x] 4.3 E1TabCreditReport(E1-18/E1-19信用报告query/check) 补全：审计目标/编制提示/审计说明+结论
  - _对照源模板 E1-14/E1-15/E1-18/E1-19 章节_

- [x] 5. 利息截止检查组（E1-20/E1-21/E1-22/E1-23）
  - [x] 5.1 E1TabAccruedInterest(E1-20应计利息测算) 补全：审计目标/编制提示/审计说明+结论
  - [x] 5.2 E1TabCutoffTest(E1-21/E1-22截止测试bank/other) 补全：审计目标/编制提示/审计说明+结论(跨期标注保留)
  - [x] 5.3 E1TabLargeCheck(E1-23收支检查) 补全：审计目标/编制提示/审计说明+结论
  - _对照源模板 E1-20/E1-21/E1-22/E1-23 章节_

- [x] 6. 舞弊附注组（E1-26~32/附注）
  - [x] 6.1 E1TabIpoSpecial(E1-26~32舞弊应对) 补全：审计目标/编制提示/审计说明+结论(各sheetCode) — 新增 SHEET_META 按 sheetCode 动态审计目标+审计说明/结论 textarea(item_id E1-ipo-audit-note-{code}/E1-ipo-audit-conclusion-{code})
  - [x] 6.2 E1TabDisclosure(附注上市/国企) 对照源模板附注披露信息模板核对字段完整性 — 补审计目标alert(按版本)+审计说明/结论card(item_id E1-disclosure-{variant}-audit-note/-audit-conclusion)+披露项目按版本区分(上市8项/国企现金/银行存款/其他货币资金/数字货币/合计)+列标签版本化(期末数/期初数 vs 期末余额/年初余额)+SOE受限明细预置源模板5项+watch(variant)重载
  - _对照源模板 E1-26~E1-32 + 附注披露 章节_

- [x] 7. 最终验证
  - [x] 7.1 全部改动文件 get_diagnostics 零错误（12 组件全清）+ Vite transform 全 200 + Playwright 实测 E1-21 截止测试/E1-26 现金交易分析渲染正常（编制提示/审计目标/审计说明/审计结论齐全，0 console error）

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "2.2"] },
    { "id": 1, "tasks": ["2.3", "3.1", "3.2", "3.3", "4.1"] },
    { "id": 2, "tasks": ["4.2", "4.3", "5.1", "5.2", "5.3"] },
    { "id": 3, "tasks": ["6.1", "6.2"] },
    { "id": 4, "tasks": ["7.1"] }
  ]
}
```

## Notes

- 源模板路径：`d:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）\BCD类底稿md\E货币资金循环\E货币资金底稿模板库.md`
- 前端组件路径：`audit-platform/frontend/src/components/workpaper/e1/`
- composable 路径：`audit-platform/frontend/src/components/workpaper/composables/useE1*.ts`
- 参照标杆：E1TabAdjudication.vue（已补审计说明/结论）、D4TabProductMargin.vue（gold标准）
- 不臆造 AI（无 aiGenerateNote composable 的 tab 只加纯 textarea）
- 只用 str_replace，禁止 PowerShell 破坏 UTF-8
