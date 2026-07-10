# Implementation Plan: S 类计算型专项底稿专属组件（S3/S15/S20/S21）

## Overview

对齐 D4 标准为 4 个计算型底稿开发专属组件：componentType 注册 + sheetName v-if 分发 + 纯函数公式引擎 composable + 审定表回写 trial_balance（v2 正数、flush 不 commit）+ 附注 EventBus 联动 + GtIndexChip + 导入导出。PBT：前端 fast-check + 后端 hypothesis。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3"] },
    { "id": "wave3", "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2", "6.3"] },
    { "id": "wave7", "tasks": ["7.1", "7.2", "7.3"] },
    { "id": "wave8", "tasks": ["8.1", "8.2"] }
  ]
}
```

## Notes

- 铁律：任务标记不假绿；optional(*) 也要做完；改动后必 Playwright 实测。
- 专属组件不能有内部 el-tabs，接 sheetName prop 用 v-if 分发。
- 公式引擎必须是纯函数（可单测）；公式单元格只读不可手工覆盖。
- 审定表 service 层只 flush 不 commit；损益类取发生额从 tb_ledger。
- 完成后归档并更新 `.kiro/specs/INDEX.md`。

## Tasks

- [x] 1. Phase0 双源核对：4 底稿公式与 sheet 落定
  - 运行 `analyze_s_category.py` + `dump_s_special_content.py`，逐 sheet 确认 S3/S15/S20/S21 的公式链、审定表结构、子表清单
  - 交叉验证底稿模板库 md，产出各底稿 sheetName 分发表 + 公式引擎输入/输出规格
  - _Requirements: 2.1, 3.1, 4.1, 5.1, 6.1_

- [x] 2. 后端注册（4 componentType）
  - [x] 2.1 VALID_COMPONENT_TYPES + wp_code_overrides：S3/S15/S20/S21 → 对应专属类型
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 2.2 RENDERER_DISPATCH 注册 4 类；render schema yaml + guidance
    - _Requirements: 1.4_
  - [x] 2.3 validate_overrides + 注册契约测试
    - _Requirements: 1.1, 1.2_

- [x] 3. 公式引擎（纯函数 composable）
  - [x] 3.1 useS15FormulaEngine：加权平均股数 / 基本+稀释 EPS / 全面摊薄+加权平均 ROE
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.5_
  - [x] 3.2 useS20FormulaEngine：营收=主营+其他 / 扣除合计 / 占比 / 扣除后金额
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 3.3 useS21FormulaEngine：按月归集 / 类目合计 / 各类目占比 / 各月比例 / 研发阶段合计
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 3.4 useS3AdjustmentEngine：首执新准则调整 + 简化追溯调整法公式保留
    - _Requirements: 6.1_

- [x] 4. 4 个专属 Vue 组件（sheetName v-if 分发）
  - [x] 4.1 GtS15EpsRoe.vue：分发审定表/程序/S15-2/S15-3/S15-4；本年上年对比
    - _Requirements: 1.5, 2.5, 3.4, 3.5_
  - [x] 4.2 GtS21DataAsset.vue：分发数据资产/S21-1/S21-2/S21-3/S21-4；5 项资本化条件判断
    - _Requirements: 1.5, 5.4, 5.5, 5.6_
  - [x] 4.3 GtS20RevenueDeduction.vue：单 sheet 多区段；顶部方法论上下文（适用情形）
    - _Requirements: 1.5, 4.4, 4.5_
  - [x] 4.4 GtS3PolicyChange.vue：分发审定/S3-1/2/4/6/8/9/10；三类事项区分 + 非经常性损益标注
    - _Requirements: 1.5, 6.2, 6.3, 6.4_

- [x] 5. 审定表回写与附注联动
  - [x] 5.1 审定金额回写 trial_balance（audited_amount v2 正数，flush 不 commit）+ auto_data_source resolver + field_overrides
    - _Requirements: 7.1, 7.2, 7.4_
  - [x] 5.2 保存发布 WORKPAPER_SAVED；披露文本区 + AI 辅助 + disclosure:note-text-updated；订阅 substantive:adjudicated
    - _Requirements: 7.3, 8.1, 8.2, 8.3_

- [x] 6. 前端注册、引用、导入导出
  - [x] 6.1 htmlRendererRegistry 注册 4 类（defineAsyncComponent, contextProps standard）
    - _Requirements: 1.1_
  - [x] 6.2 取数溯源 GtIndexChip（prop `value`）+ 灰态兜底
    - _Requirements: 9.1, 9.2, 9.3_
  - [x] 6.3 动态明细表导入导出（useXImportExport + 三端点 + http/axios + RFC5987 + 多区块分 sheet）
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 7. UI 规范与只读
  - [x] 7.1 13px 字体 + 公式列虚线下划线+cursor:help+tooltip 来源；审计说明/结论 el-card；编制提示 details 折叠
    - _Requirements: 11.1, 11.2_
  - [x] 7.2 多步骤顶部蓝色渐变引导区（2 列 grid）；金额默认「元」经 fmt 出口
    - _Requirements: 11.3, 11.5_
  - [x] 7.3 readonly 禁编辑与明细增删，仅浏览与跳转
    - _Requirements: 11.4_

- [x] 8. PBT 与集成测试
  - [x] 8.1 PBT（fast-check 前端 + hypothesis 后端 ≥100 次）：P1 注册 / P2 加权股数 / P3 基本EPS / P4 ROE / P5 营收扣除 / P6 资本化归集 / P7 公式不可覆盖 / P8 回写方向 / P9 readonly
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.5, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.6, 7.1, 7.4, 11.1, 11.4_
  - [x] 8.2 集成 + Playwright：各 sheet 分发渲染 / 引擎实时重算 / 审定回写 / 导入导出往返 / 只读
    - _Requirements: 1.5, 2.5, 7.1, 10.1, 11.4_
