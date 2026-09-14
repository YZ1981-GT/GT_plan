# Implementation Plan: confirmation-alternative-d0-6

## Overview

�?D0-6 应收及销售替代程序创建专用组�?`GtConfirmationAlternativeD06`（与 D0-5 姊妹同构：多公司 master-detail + 4 区块检查宽�?+ 检查比例自�?+ D0-1/D0-4 联动）�?*最大化复用 D0-5 �?CheckBlock.vue + useAlternativeData + SamplingConfig/BalanceSummary/AuditConclusion**，核心新增仅�?BLOCK_COLUMN_CONFIGS_D06�? 区块列定义）+ componentType 注册 + guidance�? Sprint（因大量复用，比 D0-5 精简）：列配�?类型 �?UI 组装+提示 �?注册回归实测�?

依赖：confirmation-alternative-d0-5（D0-5）的 CheckBlock / useAlternativeData / SamplingConfig / BalanceSummary / AuditConclusion / AlternativeDashboard / AlternativeMaster 先行就绪�?

## Tasks

### Sprint 1：列配置 + 类型 + 枚举 + guidance（地基）

- [x] 1.1 新增 `BLOCK_COLUMN_CONFIGS_D06` 常量�? 区块列定义（block1 期末余额形成 25�?/ block2 期后回款 14�?/ block3 本期出库 20�?/ block4 本期收款 11列）
  - _需�?4.1_
- [x] 1.2 新增 `alternativeD06Types.ts`：复�?re-export AlternativeCompany+CheckRow，增 D06Payload（_format: alternative-d06-v1�?
  - _需�?10.3_
- [x] 1.3 新增 `alternativeD06Enums.ts`：复�?sampling_method / yes_no
  - _需�?9.1_
- [x] 1.4 编制指引 `wp_guidance/D0-6.json`（替代程序要�?检查原始凭�?回款/出库/余额重大同时执行 + 概述要求：测试情�?调整/未调�?范围受限�?
  - _需�?8.5_

### Sprint 2：UI 组装 + 提示落位 + 联动

- [x] 2.1 新增 `GtConfirmationAlternativeD06.vue`：组装（复用 Dashboard+Master+Detail+SamplingConfig+BalanceSummary+CheckBlock×4+AuditConclusion），传入 BLOCK_COLUMN_CONFIGS_D06 + format='alternative-d06-v1' + 函证项目='应收账款'
  - _需�?1, 2, 3, 4, 12_
- [x] 2.2 SamplingConfig placeholder 改为应收账款口径�?如应收账款借方发生额�?�? BalanceSummary 函证项目=应收账款
  - _需�?2.2, 3.1_
- [x] 2.3 编制说明/提示精确就近落位：①→区块②�?tooltip / ②→区块①③ tooltip+placeholder / ③→顶部+guidance / 概述→审计结论区结构化提�?
  - _需�?8.1, 8.2, 8.3, 8.4_
- [x] 2.4 D0-1/D0-4 带入接入：复�?D0-5 带入逻辑（改过滤条件�?未回函应收账�?�? 视觉标识 + 跳转链接
  - _需�?5.1, 5.2, 5.3, 5.4_
- [x] 2.5 质量红线+看板：复�?D0-5 �?Dashboard/红线逻辑（异�?区块无记�?比例低）
  - _需�?6.1, 6.2, 6.3, 6.4_
- [x] 2.6 审计说明+结论：复�?AuditConclusion + 概述要求提示
  - _需�?7.1, 7.2_

### Sprint 3：注�?+ 回归实测

- [x] 3.1 `htmlRendererRegistry.ts` 注册 confirmation-alternative-d06；后�?dispatch D0-6 sheet �?componentType
  - _需�?12.1_
- [x] 3.2 旧格式兼容降�?GtGridSheet 只读
  - _需�?11.2; 属�?P5_
- [x] 3.3 保存端到�?+ 回归（render-config 冒烟 + 枚举测试�? 只读回归
  - _需�?10.3, 11.1, 11.3_
- [x] 3.4 Playwright D0-6 端到�?0 error：新增公司→�?D0-1 带入→填抽样→余额→4区块各增行→合计→比例→标异常→结论→保存→重开→跳 D0-1/D0-4
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "wave": 2, "tasks": ["2.1", "2.2", "2.3"] },
    { "wave": 3, "tasks": ["2.4", "2.5", "2.6"] },
    { "wave": 4, "tasks": ["3.1", "3.2"] },
    { "wave": 5, "tasks": ["3.3", "3.4"] }
  ]
}
```

## Notes

- **D0-6 �?D0-5 是姊妹表**：结构完全同构，仅区块列配置/余额口径/编制说明/componentType 不同。D0-5 先实现基础组件，D0-6 复用仅新增列配置+注册�?
- **复用清单**：CheckBlock.vue / useAlternativeData.ts / AlternativeDashboard / AlternativeMaster / AlternativeDetail / SamplingConfig / BalanceSummary / AuditConclusion 全复�?D0-5 产物�?
- **核心新增仅为**：BLOCK_COLUMN_CONFIGS_D06�? 区块列定义，与源模板逐列吻合�? wp_guidance/D0-6.json + 主组�?GtConfirmationAlternativeD06.vue（传入不同配置的 wrapper�? componentType 注册�?
- **编制说明精确落位**�? �?+ 概述）：①检查收�?回款→区块②�?/ ②检查原始凭证→区块①③ / ③余额重大→顶部+guidance / 概述(测试情况/调整/未调�?范围受限)→审计结论区提示�?
- 因大量复用，�?spec �?5 Sprint 精简�?**3 Sprint / 14 任务 / 5 �?*，远�?D0-5 轻量�?
- 铁律：组�?props 不可变；只读路径无编辑控件；改动�?Playwright 实测�?
