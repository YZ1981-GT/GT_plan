# Implementation Plan: S 类交易/专家/检查型专项底稿专属组件

## Overview

对齐 D4 标准：为交易型底稿（S4/S5/S6/S12/S13/S14）开发 6 个专属组件（sheetName v-if 分发 + 公式引擎 + 判断逻辑 + 专家多分支 + 审定回写 + 附注联动），检查表型（S1/S2/S8/S9/S10/S11/S16/S17）走 a-program-console + 内部子 sheet 分发。S17 旧版 .xls 需 Phase0 转换。PBT：前端 fast-check + 后端 hypothesis。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3"] },
    { "id": "wave3", "tasks": ["3.1", "3.2", "3.3"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": "wave5", "tasks": ["5.1", "5.2", "5.3"] },
    { "id": "wave6", "tasks": ["6.1", "6.2"] },
    { "id": "wave7", "tasks": ["7.1", "7.2", "7.3"] },
    { "id": "wave8", "tasks": ["8.1", "8.2"] }
  ]
}
```

## Notes

- 铁律：任务标记不假绿；optional(*) 也要做完；改动后必 Playwright 实测。
- 专属组件不能有内部 el-tabs，接 sheetName prop 用 v-if 分发。
- S17 是旧版 `.xls`，Phase0 必须先转 `.xlsx` 或 xlrd 读取，失败不静默兜底空数据。
- 审定表 service 层只 flush 不 commit；非经常性损益必须在附注标注。
- 完成后归档并更新 `.kiro/specs/INDEX.md`。

## Tasks

- [x] 1. Phase0 双源核对 + S17 格式转换
  - 运行 `analyze_s_category.py` + `dump_s_special_content.py`，确认 14 底稿的 sheet 结构、审定表/内控调查表/判断子表/专家多分支
  - 将 S17 `.xls` 转 `.xlsx`（或 xlrd 读取），产出各底稿 sheetName 分发表 + 引擎输入/输出规格
  - _Requirements: 2.1, 3.1, 4.1, 5.1, 7.1, 8.1, 8.2_

- [x] 2. 后端注册（6 专属 + 检查表型映射）
  - [x] 2.1 VALID_COMPONENT_TYPES 新增 6 专属类型；wp_code_overrides：交易型→专属，检查表型→a-program-console
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 2.2 RENDERER_DISPATCH 注册 6 专属类型；render schema yaml + guidance
    - _Requirements: 1.4_
  - [x] 2.3 validate_overrides + 注册契约测试
    - _Requirements: 1.1, 1.3_

- [x] 3. 公式引擎与判断逻辑（纯函数）
  - [x] 3.1 useS4FormulaEngine：交换损益 + 换入成本；商业实质 judgeApplicable / judgeCommercialSubstance（IF 逻辑）
    - _Requirements: 2.2, 2.3, 2.4_
  - [x] 3.2 useS5FormulaEngine：债权人/债务人重组损益（源模板口径）
    - _Requirements: 3.2_
  - [x] 3.3 专家 domain 分支解析 resolveExpertSubSheet（general/股份支付/金融工具公允价值）
    - _Requirements: 4.3, 4.4_

- [x] 4. 交易型专属 Vue 组件（sheetName v-if 分发）
  - [x] 4.1 GtS4NonmonetaryExchange.vue（审计程序/审定表S4-1/商业实质S4-2）+ 非经常性损益标注
    - _Requirements: 1.5, 2.1, 2.5_
  - [x] 4.2 GtS5DebtRestructuring.vue（程序/审定表S5-1/损益时点S5-2）+ 提示不得提前确认 + 非经常性损益标注
    - _Requirements: 1.5, 3.1, 3.3, 3.4, 3.5_
  - [x] 4.3 GtS12CpaExpert.vue + GtS13MgmtExpert.vue（程序表 + S12/13-1~3 + 多分支子表）
    - _Requirements: 1.5, 4.1, 4.2, 4.5_
  - [x] 4.4 GtS14AccountingEstimate.vue（程序表 + S14-1~4）+ GtS6FundOccupation.vue（审定表S6-1 + 大程序表 + 监管风险提示第9号上下文区块）
    - _Requirements: 1.5, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3_

- [x] 5. 检查表型底稿（a-program-console + 内部子 sheet）
  - [x] 5.1 S9 分发（程序/审定表S9-1/内控调查表S9-2/程序说明/法律法规折叠）
    - _Requirements: 7.1, 7.3_
  - [x] 5.2 S10 分发（程序/审定表S10-1/内控调查表S10-2/环境法规折叠）
    - _Requirements: 7.2, 7.3_
  - [x] 5.3 S1/S2/S8/S11/S16/S17 程序表 + 审定表（如有）子 sheet 分发；S17 呈现非经常性损益明细 + 与 S15/S20 交叉勾稽
    - _Requirements: 8.2, 8.3_

- [x] 6. 审定表回写、附注联动、前端注册
  - [x] 6.1 S4/S5/S6/S8/S9/S10 审定金额回写 trial_balance（v2 正数，flush 不 commit）+ resolver + field_overrides；WORKPAPER_SAVED；披露区+AI+disclosure:note-text-updated
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - [x] 6.2 htmlRendererRegistry 注册 6 专属类型（defineAsyncComponent, contextProps standard）
    - _Requirements: 1.1_

- [x] 7. 引用、UI 规范与只读
  - [x] 7.1 索引列 GtIndexChip（prop `value`）+ 灰态兜底
    - _Requirements: 10.1, 10.2, 10.3_
  - [x] 7.2 13px 字体 + 判断/公式列虚线下划线+tooltip 准则依据；审计说明/结论 el-card + AI 按钮；编制提示 details；动态行导入导出（http/axios）
    - _Requirements: 11.1, 11.2, 11.3_
  - [x] 7.3 readonly 禁编辑与明细增删，仅浏览与跳转；金额默认「元」经 fmt 出口
    - _Requirements: 11.4, 11.5_

- [x] 8. PBT 与集成测试
  - [x] 8.1 PBT（fast-check 前端 + hypothesis 后端 ≥100 次）：P1 注册 / P2 S4损益 / P3 商业实质 / P4 S5损益 / P5 专家分支 / P6 回写方向 / P7 非经常性损益标注 / P8 readonly
    - _Requirements: 1.1, 1.2, 1.3, 2.2, 2.3, 2.4, 3.2, 4.3, 4.4, 9.1, 9.3, 2.5, 3.5, 9.4, 11.4_
  - [x] 8.2 集成 + Playwright：交易型 sheet 分发 / S4-2 商业实质判断 / S12 专家分支 / S9-S10 内控调查表 / S17 转换渲染 / 审定回写 / 只读
    - _Requirements: 1.5, 2.3, 4.3, 7.1, 8.2, 9.1, 11.4_
