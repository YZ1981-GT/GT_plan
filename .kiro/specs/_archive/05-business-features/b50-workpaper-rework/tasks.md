# Implementation Plan: B50 风险评估底稿改造

## Overview

按 6 波实施：Wave0 后端基座（render 策略防 grid shadow + 注册 + scope 余额）→ Wave1 P0 前端（程序表 Tab + Tab3 扩列）→ Wave2 P1 双模式 → Wave3 P1* 引导弹窗 → Wave4 P2* 美化 → Wave5 验证。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1", "2", "3"], "depends_on": [] },
    { "wave": 1, "tasks": ["4", "5"], "depends_on": [0] },
    { "wave": 2, "tasks": ["6"], "depends_on": [0] },
    { "wave": 3, "tasks": ["7"], "depends_on": [1] },
    { "wave": 4, "tasks": ["8"], "depends_on": [1] },
    { "wave": 5, "tasks": ["9", "10"], "depends_on": [0, 1, 2, 3, 4] }
  ]
}
```

## Tasks

- [x] 1. 新增 B50 render 策略（防 grid shadow + oo_sheet_map）
  - 新建 `backend/app/routers/wp_render_strategies/_b50_risk_assessment.py`：`render(ctx)` 返回 `{component_type:"b50-risk-assessment", project_context:{client_name,audit_year,program_available:True,oo_sheet_map:{program/tab1..tab4}}}`，**不含 cells/html_data**。
  - `_load_project_context` 查 projects 取 client_name/audit_year，DB 异常降级返回最小 dict（不 500）。
  - 注册 `wp_render_strategies/__init__.py` `RENDERER_DISPATCH["b50-risk-assessment"]`。
  - _需求：R1.1, R4.2, R6_ _属性：P1, P2_

- [x] 2. 注册表更新（WHOLE + OnlyOffice 白名单）
  - `dedicated_component_types.py` `DEDICATED_COMPONENT_TYPES` 加 `"b50-risk-assessment"`。
  - 按 `test_dedicated_component_registry_contract.py` 契约核对是否需加入 `_ONLYOFFICE_HTML_WHITELIST`，使契约测试通过。
  - _需求：R6_ _属性：—_

- [x] 3. 扩展 `/api/b50/scope-accounts` 返回科目余额（既有 `amount` 字段即余额，前端映射消费）
  - `backend/app/routers/b50_scope.py` `scope-accounts` 每项加 `balance`（trial_balance 报表项目聚合期末审定优先回退未审）。
  - balance 恒为 number 或缺省，不为 NaN/字符串。
  - _需求：R2.1_ _属性：P6_

- [x] 4. 程序表 Tab（GtAProgramConsole + 索引跳转）
  - `GtB50RiskAssessment.vue` el-tabs 首位加 `📋 汇总程序表` Tab，内嵌 `GtAProgramConsole`（自加载 /procedure-tables/B50）。
  - `onProgramIndexJump`：B50-1→tab1 … B50-4→tab4；程序表 Tab 状态纳入 overallProgress（不破坏现有 4-Tab 语义）。
  - 程序表加载失败降级提示，不阻断其余 Tab。
  - _需求：R1.1~R1.5_ _属性：P7_

- [x] 5. Tab3 认定矩阵扩列（余额/类别/会计估计 + 建议方案 + 列设置）
  - `useB50RiskMatrix.ts`：AccountRow 加 balance/category/isEstimate（item_id `B50-T3-balance/category/estimate-{acc}`）；`importAccounts` 接受 balance（空值才填，不覆盖）；`suggestedApproach` computed；`CATEGORY_OPTIONS` 常量。
  - 新建 `useB50DetailColumnPrefs.ts`（localStorage `b50-t3-column-prefs`，默认显余额/类别隐会计估计）。
  - Tab3 表补余额/类别下拉/会计估计下拉列 + ⚙ 列设置 popover + 建议方案提示；incompleteAccounts 判定不因新列放宽/收紧。
  - _需求：R2.1~R2.5_ _属性：P3, P5, P9_

- [x] 6. 双模式 HTML ↔ OnlyOffice（per-tab 源 sheet）
  - 新建 `useB50OoSheetMap.ts`：按 activeTab 从 oo_sheet_map 取 source_wp_code/oo_sheet_name，经 wp-id-by-code 解析 ooSourceWpId（缓存，失败/未实例化→null）。
  - `GtB50RiskAssessment.vue` 接 `useWorkpaperEntryDualMode`：el-segmented（结构化/在线编辑）+ ooAvailable gate + OO不可用 tag；renderMode='onlyoffice' 时渲 `GtOnlyOfficeSheet`（ooSourceWpId+ooSheetName+readonly），未实例化降级提示，@fallback 切回，切回 html reloadAll。
  - _需求：R4.1~R4.6_ _属性：P8, P10_

- [x]* 7. 引导式科目风险录入弹窗 B50AccountRiskDialog
  - 新建 `B50AccountRiskDialog.vue`：4 分组卡片（范围/认定/特别风险/应对）+ 右侧实时联动面板；save 一次性批量 saveImmediate。
  - Tab3 科目行"编辑"/工具栏"引导录入"打开；关闭后矩阵反映结果（同源无双写）。
  - _需求：R3.1~R3.4_ _属性：—_

- [x]* 8. 页面美化统一
  - 表格 13px；硬编码色值换 EP CSS 变量（风险色板保留语义）；每 Tab 顶部审计目标 el-alert + 编制提示 details（CAS 1211/1231）+ 方法论琥珀块（内嵌 B50-1 固有风险因素知识库要点，一键套用）；工具栏布局统一。
  - _需求：R5.1~R5.4_ _属性：—_

- [x] 9. PBT + 契约测试
  - 后端：`test_b50_render_strategy.py`（P1 无 cells / P2 oo_sheet_map / P6 balance number）+ 扩 `test_b50_risk_reader.py`（P4 新增 suffix 不影响解析）+ 注册表契约。
  - 前端：`useB50RiskMatrix` PBT（P3 suggestedApproach / P5 importAccounts 幂等 / P9 incomplete 一致）+ `useB50OoSheetMap`（P8 未实例化 null）+ 程序表索引映射（P7）+ switchMode（P10）。
  - _需求：R6.4_ _属性：P1-P10_

- [x] 10. 集成验证 + Playwright
  - get_diagnostics 全清 + 全改动文件 Vite transform 200 + 后端 AST OK + 既有 b50 vitest/pytest 全绿。
  - Playwright（需 B50 实例化项目）：程序表 Tab 渲染 43 行 + 索引跳转；Tab3 余额/类别列 + 建议方案 + 列设置；双模式切换（healthy→enable，未实例化→降级）；round-trip 落库 B50-T3-balance/category/estimate；0 console error。
  - _需求：R6.1~R6.4_ _属性：P1-P10_

## Notes

- 标 `*` 的任务（7、8）为 optional，按用户偏好一并做完。
- 每波完成后运行 get_diagnostics + Vite transform；Wave5 统一跑 PBT/契约/Playwright。
- 零回归铁律：现有 4-Tab 数据键、事件订阅、审批、版本链、复核对话不动。
