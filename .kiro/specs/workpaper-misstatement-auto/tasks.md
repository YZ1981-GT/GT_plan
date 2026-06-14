# Implementation Plan: A13 错报自动生成与跨模块溯源

## Overview

错报汇总服务（从 adjustments passed 聚合）+ adjustments 表字段扩展 + 前端 HTML 视图 + A16 联动。

**依赖**：workpaper-foundation-kit（HTML 渲染框架 + FieldOverrideService 用于 A13-2 披露错报 + 索引跳转）。迁移号实施时顺延。

## Tasks

- [x] 1. 数据模型扩展
  - [x] 1.1 迁移（号顺延）：`adjustments` 表加 `passed_reason TEXT` + `passed_communication_date TIMESTAMPTZ`
    - 三层一致（迁移+ORM+service）
    - _Requirements: 1.2, 4.2_

- [x] 2. 错报汇总服务
  - [x] 2.1 新建 `misstatement_summary_service.py` 骨架
    - _Requirements: 1.1_
  - [x] 2.2 `get_uncorrected_misstatements`：A13-1 从 passed 聚合（按 prior/current 分组）
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 2.3 `evaluate_misstatements`：A13-3 汇总 vs 重要性比较
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 2.4 `get_for_representation_letter`：A16 用错报摘要文本
    - _Requirements: 4.1, 4.2_
  - [x] 2.5 试算表审定数一致性校验（汇总金额 vs aje/rje_adjustment）
    - _Requirements: 5.1, 5.2_
  - [x]* 2.6 汇总金额一致性 PBT（随机 N 条 passed → 验证合计）
    - _Requirements: 2.1, 5.1_

- [x] 3. 披露错报与沟通记录
  - [x] 3.1 A13-2 披露错报录入（FieldOverrideService scope='misstatement:disclosure'）
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 3.2 A13-5 沟通记录读写（关联 adjustment + passed_communication_date）
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 4. API 端点
  - [x] 4.1 misstatement-summary/evaluation/for-letter/communication 四端点
    - _Requirements: 1.x, 2.x, 3.x, 4.x_

- [x] 5. 前端视图
  - [x] 5.1 新建 `MisstatementSummaryView.vue`（A13 HTML 表格，索引跳转）
    - _Requirements: 1.1, 1.4_
  - [x] 5.2 评价区显示汇总 vs 重要性（超阈值高亮）
    - _Requirements: 2.3_
  - [x] 5.3 用户补充"管理层不予更正原因"回写
    - _Requirements: 1.2_
  - [x]* 5.4 前端单测

- [x] 6. A16 联动
  - [x] 6.1 A16 声明书"未更正错报"占位符自动填充 + 双向跳转
    - _Requirements: 4.1, 4.2, 4.3_

- [ ] 7. Checkpoint
  - pytest + vitest 全绿

## Notes
- 复用 adjustments + materiality 表，不新增主表
- 迁移号顺延
