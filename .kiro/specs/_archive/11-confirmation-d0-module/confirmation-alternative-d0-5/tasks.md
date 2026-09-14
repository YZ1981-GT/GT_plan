# Implementation Plan: confirmation-alternative-d0-5

## Overview

�?D0-5 合同负债及销售替代程序创建专用组�?`GtConfirmationAlternativeD05`（多公司 master-detail + 4 区块检查宽表各含明�?合计自动 + 抽样配置 + 余额汇总检查比例自�?+ D0-1/D0-4 联动带入 + 经理复核红线 + 底部提示就近落位）。参�?D0-1/D0-2 大宽表精修思路�? Sprint：类型枚�?�?数据�?4区块/合计/比例/带入) �?master+detail+CheckBlock �?看板+红线+结论+导入 �?组装注册回归�?

依赖：D0-1/D0-4 spec 为上游数据源；复�?useCellSelection/CellContextMenu/useDictStore/useExcelIO/wp_html_save�?

## Tasks

### Sprint 1：类�?+ 枚举 + 区块列配置（地基�?

- [x] 1.1 新增 `alternativeTypes.ts`：AlternativeCompany(�?sampling/balance/4×block_rows) / CheckRow / Metrics / Payload
  - _需�?1.2, 4.1_
- [x] 1.2 新增 `alternativeEnums.ts`：dictKey 映射（sampling_method / yes_no�?
  - _需�?9.1_
- [x] 1.3 新增 `BLOCK_COLUMN_CONFIGS` 常量�? 区块各自列定义（block1 期后结转 14�?/ block2 期末余额 16�?/ block3 本期收款 14�?/ block4 本期出库 30列）
  - _需�?4.1_
- [x] 1.4 后端 `system_dicts.py _DICTS` �?`sampling_method`（随机选样/系统选样/货币单元抽样/随意选样�?
  - _需�?9.1_
- [x] 1.5 后端枚举测试 + 编制指引 `wp_guidance/D0-5.json`（替代程序适用条件/检查要�?检查原始凭�?余额重大同时执行要求�?
  - _需�?8.4, 9.1_

### Sprint 2：useAlternativeData（数据核心）

- [x] 2.1 新增 `useAlternativeData.ts`：从 htmlData 解析 companies + watch 重建 + dirty
  - _属�?P5_
- [x] 2.2 companies CRUD：addCompany/deleteCompany/updateCompany/importCompanies
  - _需�?10.1_
- [x] 2.3 blockTotal（各区块金额列合计，精确小数�? checkRatio（收�?出库检查比�?区块合计/销售额，销�?→N/A�?
  - _需�?3.2, 3.3, 4.2; 属�?P1/P2_
- [x] 2.4 completionStatus�?区块有记录占比）+ hasAbnormal（任一�?is_abnormal=是）+ metrics
  - _需�?1.1, 6.1; 属�?P3_
- [x] 2.5 D0-1/D0-4 带入：拉未回函公�?�?映射 entity_name/confirm_index/期末余额 �?去重 �?_source
  - _需�?5.2, 5.3; 属�?P4_
- [x] 2.6 buildPayload（_format: alternative-d05-v1�?
  - _需�?10.3_
- [x] 2.7 数据层单测：CRUD + 4区块合计 + 检查比�?+ completionStatus/hasAbnormal + 带入去重 + buildPayload
  - _属�?P1/P2/P3/P4_

### Sprint 3：Master + Detail + CheckBlock × 4（核�?UI�?

- [x] 3.1 新增 `AlternativeMaster.vue`：el-table 关键�?+ 完成�?异常/结论状�?+ 工具�?+ 行展开 + 空�?
  - _需�?1.1, 1.5, 10.1_
- [x] 3.2 新增 `AlternativeDetail.vue`：容器（SamplingConfig �?BalanceSummary �?4×CheckBlock �?AuditConclusion�?
  - _需�?1.2_
- [x] 3.3 新增 `SamplingConfig.vue`：抽样配置字�?+ 抽样方法枚举 + placeholder 模板示例灰字
  - _需�?2.1, 2.2_
- [x] 3.4 新增 `BalanceSummary.vue`：余额字�?+ 收款/出库检查比例只读自�?
  - _需�?3.1, 3.2, 3.3, 3.4; 属�?P2_
- [x] 3.5 新增 `CheckBlock.vue`（复用性高 × 4 实例）：�?blockType �?BLOCK_COLUMN_CONFIGS 渲染�?+ 合计�?+ 分组表头着�?冻结序号/斑马�?空值淡�?+ useCellSelection + 右键 + 折叠/展开
  - _需�?4.1, 4.2, 4.3, 4.4, 4.6; 属�?P1_
- [x] 3.6 字段提示就近落位：提示①→区块① tooltip / 提示②→区块②④ tooltip+placeholder / 提示③→顶部说明+guidance
  - _需�?8.1, 8.2, 8.3, 8.5_
- [x] 3.7 右键菜单：master（复�?删除/跳转�? 子表行（复制/插入/删除/复制索引�?
  - _需�?10.2_
- [x] 3.8 Master+Detail+CheckBlock spec：展开/区块合计/比例自动/异常/只读守卫
  - _需�?1, 3, 4; 属�?P1/P2/P3/P6_

### Sprint 4：看�?+ 质量红线 + 联动 + 结论 + 导入

- [x] 4.1 新增 `AlternativeDashboard.vue`：总公�?完成�?异常�?检查比例分�?+ 折叠 + 异常高亮
  - _需�?6.4, 6.5_
- [x] 4.2 D0-1/D0-4 带入接入 + 自动取数视觉标识 + 跳转链接
  - _需�?5.1, 5.4, 5.6_
- [x] 4.3 质量红线：异常行高亮(�? / 区块无记�?�? / 检查比例低(�? / 异常未决(�?
  - _需�?6.1, 6.2, 6.3; 属�?P3_
- [x] 4.4 新增 `AuditConclusion.vue`：审计说�?+ 结论枚举+文本 + 异常未决提示
  - _需�?7.1, 7.2_
- [x] 4.5 批量导入：复�?useExcelIO；导出模�?
  - _需�?10.4, 10.5_
- [x] 4.6 看板+红线+联动+结论+导入 spec
  - _需�?5, 6, 7; 属�?P3/P4_

### Sprint 5：组�?+ 注册 + 回归实测

- [x] 5.1 新增 `GtConfirmationAlternativeD05.vue`：组�?Dashboard+Master+Detail+接入 composable
  - _需�?1, 4_
- [x] 5.2 `htmlRendererRegistry.ts` 注册 confirmation-alternative-d05；后�?dispatch D0-5 sheet �?componentType
  - _需�?1_
- [x] 5.3 旧格式兼容降�?GtGridSheet 只读
  - _需�?11.2; 属�?P5_
- [x] 5.4 保存端到�?+ 回归（render-config 冒烟 + 枚举测试�? 只读回归
  - _需�?10.3, 11.1, 11.3_
- [x] 5.5 Playwright D0-5 端到�?0 error：新增公司→�?D0-1 带入→填抽样→余额→4区块各增行→合计→比例→标异常→结论→保存→重开→跳 D0-1/D0-4
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "wave": 2, "tasks": ["1.5", "2.1"] },
    { "wave": 3, "tasks": ["2.2", "2.3", "2.5"] },
    { "wave": 4, "tasks": ["2.4", "2.6", "2.7"] },
    { "wave": 5, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "wave": 6, "tasks": ["3.5", "3.6", "4.1"] },
    { "wave": 7, "tasks": ["3.7", "3.8", "4.2", "4.3", "4.4", "4.5"] },
    { "wave": 8, "tasks": ["4.6", "5.1", "5.2"] },
    { "wave": 9, "tasks": ["5.3", "5.4"] },
    { "wave": 10, "tasks": ["5.5"] }
  ]
}
```

## Notes

- �?D0-1/D0-2 形态高度同构（超宽表→多公�?master-detail），�?detail 内部�?*4 个结构不同的检查区�?*（列结构各异 10-30 列），由通用 `CheckBlock.vue` 组件�?`blockType` 驱动列配置（BLOCK_COLUMN_CONFIGS）实现复用�?
- **底部提示精确落位**（非笼统堆底）：提示①→区块�?tooltip / 提示②→区块②④ / 提示③→顶部+guidance�?
- 4 区块的列结构/表头/着色参�?D0-1 �?GtGridSheet 网格美化（分组表�?5 色轮转着�?/ 冻结序号�?/ 斑马�?/ 空值淡化）�?
- 检查比例自动派生：收款比例=区块③合�?本期销�?/ 出库比例=区块④合�?本期销售，销售为 0 或空时显 N/A�?
- D0-5 �?D0-1"未回�?/ D0-4"未达账项/未回�?带入待检公司。D0-6（应收及销售替代程序）结构类似�?spec，后续可复用 CheckBlock + useAlternativeData（改列配置即可）�?
- 铁律：组�?props 不可变（composable 深拷贝）；只读路径无编辑控件；改动后 Playwright 实测�?
