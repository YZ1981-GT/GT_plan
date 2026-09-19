# Implementation Plan: 现金流量表核查模块

## Overview

CF 核查服务（5 个子核查）+ 逆算公式配置 + 结果缓存表 + 前端多 Tab 视图 + A5 程序表联动。

## Tasks

- [x] 1. 逆算公式配置
  - [x] 1.1 创建 `backend/data/cf_verification_formulas.json`（经营/投资/筹资各项逆算公式+组件数据源）
    - _Requirements: 3.1, 3.2_

- [x] 2. 结果存储
  - [x] 2.1 V078/R078 迁移：`cf_verification_results` 表（缓存核查结果+用户差异说明）
    - _Requirements: 3.4, 4.x_

- [x] 3. CF 核查服务
  - [x] 3.1 新建 `cash_flow_verification_service.py` 骨架
    - _Requirements: 1.x_
  - [x] 3.2 `get_cash_equivalents`：现金等价物列示 + BS 货币资金勾稽
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 3.3 `reconcile_bs_cf`：BS 期末-期初=CF净增加 验证
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 3.4 `verify_main_table`：主表逆算（销售收到/购买支付/职工/税费等）
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 3.5 `verify_supplementary`：附表间接法（净利润+调整项=经营CF）
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [x]* 3.6 逆算公式单元测试（已知数据验证）
    - _Requirements: 3.2_
  - [x]* 3.7 勾稽恒等 PBT（随机 TB → 期末-期初=净增加）
    - _Requirements: 2.1_

- [x] 4. CF 调整
  - [x] 4.1 CF 调整分录录入（adjustment_type='CF'，复用 adjustments 表）
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 5. API 端点
  - [x] 5.1 CF 核查各项端点（cash-equivalents/reconcile/main-table/supplementary）
    - _Requirements: 1.x, 2.x, 3.x, 4.x_

- [x] 6. 前端
  - [x] 6.1 新建 `CashFlowVerification.vue` 多 Tab 主视图
    - _Requirements: 1.x, 2.x, 3.x, 4.x_
  - [x] 6.2 差异高亮 + 用户填写原因说明
    - _Requirements: 3.3, 4.3_
  - [x] 6.3 导出 A5-1 格式 Excel
    - _Requirements: 6.x_
  - [x]* 6.4 前端单测

- [x] 7. A5 程序表联动
  - [x] 7.1 A5/A1 程序表"现金流量表审计"步骤跳转 CF 核查 + 状态反映
    - _Requirements: 6.1, 6.2_

- [x] 8. Checkpoint
  - pytest + vitest 全绿 + imports OK + 6 相关测试通过

## Notes
- 依赖 trial_balance + financial_report 数据完整
- 迁移号顺延
