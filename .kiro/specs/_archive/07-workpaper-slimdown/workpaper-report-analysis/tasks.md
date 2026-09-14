# Implementation Plan: 报表模块完善

## Overview

TB 完整视图服务 + 期初核对 + 趋势分析增强 + 比率分析 + 分析说明存储 + 前端组件。

**依赖**：workpaper-foundation-kit（`FieldOverrideService` 用于分析说明存储 + `useWorkpaperNavigation` 用于 A1 联动跳转）。迁移号实施时顺延。行业比率对比因无本地数据源暂不实现。

## Tasks

- [x] 1. 数据模型
  - [x] 1.1 分析说明使用基础设施 `FieldOverrideService`（scope='report_analysis:{type}'），不新建 report_analysis_explanations 表
    - _Requirements: 3.3, 4.x, 5.4, 2.3_

- [x] 2. TB 完整视图
  - [x] 2.1 新建 `trial_balance_full_view_service.py`：科目级调整分列聚合
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 2.2 平衡公式校验（原报+AJE+RJE+其他=审定）
    - _Requirements: 1.3, 1.4_
  - [x]* 2.3 平衡公式恒等 PBT
    - _Requirements: 1.3_

- [x] 3. 期初核对
  - [x] 3.1 `reconcile_opening_balance`：本年期初 vs 上年审定差异
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 3.2 期初核对状态联动 A1
    - _Requirements: 2.4_

- [x] 4. 趋势分析
  - [x] 4.1 新建 `report_trend_analysis_service.py`：BS 趋势（横向+纵向+显著标记）
    - _Requirements: 3.1, 3.2, 3.4_
  - [x] 4.2 PL 趋势（含毛利率变动）
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 4.3 未审/已审两版支持
    - _Requirements: 3.4, 4.x_

- [x] 5. 比率分析
  - [x] 5.1 新建 `financial_ratio_service.py`：9 个比率计算
    - _Requirements: 5.1, 5.2_
  - [x] 5.2 异常比率标记 + 未审/已审两版
    - _Requirements: 5.3, 5.5_
  - [x]* 5.3 比率计算单元测试
    - _Requirements: 5.1_

- [x] 6. API 端点
  - [x] 6.1 full-tb/opening-reconcile/bs-trend/pl-trend/ratio 端点（`wp_report_analysis` router 已在 `router_registry/workpaper.py` 数据组注册，2026-06-14 补注册修复 404）
    - _Requirements: 1.x~5.x_
  - [x] 6.2 分析说明读写端点
    - _Requirements: 3.3_

- [x] 7. 前端
  - [x] 7.1 `TrialBalanceFullView.vue`（简洁/完整切换）
    - _Requirements: 1.1, 1.5_
  - [x] 7.2 `OpeningReconciliation.vue`（差异列表+说明）
    - _Requirements: 2.2, 2.3_
  - [x] 7.3 增强 `MultiYearCompare` 满足趋势分析需求
    - _Requirements: 3.5_
  - [x] 7.4 `FinancialRatioPanel.vue`
    - _Requirements: 5.2, 5.4_
  - [x]* 7.5 前端单测

- [x] 8. 程序表联动 + 导出
  - [x] 8.1 A1 第9项链接分析结果 + 显著项待完成提示
    - _Requirements: 6.1, 6.2_
  - [x] 8.2 导出 A2-1 格式 Excel
    - _Requirements: 6.3_

- [x] 9. Checkpoint
  - pytest + vitest 全绿 + 真实项目数据验证

## Notes
- 趋势分析增强现有 MultiYearCompare 而非新建
- 迁移号顺延
