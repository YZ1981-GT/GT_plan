# Implementation Plan: confirmation-reliability-d0-7

## Overview

�?D0-7 邮件/传真回函可靠性验证创建专用组�?`GtConfirmationReliability`（中等宽度可编辑网格~14�?+ 条件�?寄回原件=否展开验证6�? + �?/�?/�? 精确就近tooltip + D0-1联动带入电子回函�?+ 质量红线）。形态类�?D0-4（单层网�?自动派生），无需 master-detail�? Sprint：类型枚�?提示常量 �?数据�?�?网格+条件�?tooltip �?看板+联动+结论+注册回归�?

依赖：D0-1 spec 为上游数据源（回函方�?传真/电子邮件行）；复�?useCellSelection/CellContextMenu/useDictStore/useExcelIO�?

## Tasks

### Sprint 1：类�?+ 枚举 + 提示常量 + guidance（地基）

- [x] 1.1 新增 `reliabilityTypes.ts`：ReliabilityRow(~14字段含条件列) / Metrics / ReliabilityPayload
  - _需�?1.1, 2_
- [x] 1.2 新增 `reliabilityEnums.ts`：dictKey（reply_reliability_conclusion / confirmation_reply_method / yes_no�?
  - _需�?7.1_
- [x] 1.3 新增 `FIELD_TOOLTIPS_D07` 常量：注1(身份确认4�?/�?(邮箱验证3�?电子签名+技术提示链�?/�?(信息可靠�?�? 完整文本
  - _需�?3.1, 3.2, 3.3_
- [x] 1.4 新增 `RELIABILITY_COLUMN_CONFIG` 列配置常量（14列定义含条件标记+tooltip映射�?
  - _需�?1.1_
- [x] 1.5 后端 `system_dicts.py _DICTS` �?`reply_reliability_conclusion`（可�?部分可靠需补充/不可靠）
  - _需�?7.1_
- [x] 1.6 后端枚举测试 + 编制指引 `wp_guidance/D0-7.json`（注1/�?/�? 原文 + 顶部提示全文 + 技术提�?号链�?+ 审计说明记录要求�?
  - _需�?3.6, 4.3_

### Sprint 2：useReliabilityData（数据核心）

- [x] 2.1 新增 `useReliabilityData.ts`：从 htmlData 解析 rows + watch 重建 + dirty
  - _属�?P4_
- [x] 2.2 rows CRUD：addRow/deleteRow/updateField/importRows
  - _需�?8.1_
- [x] 2.3 metrics computed（total/verified_rate=结论非空/total/unreliable_count=结论=不可靠）
  - _需�?6.4; 属�?P2_
- [x] 2.4 D0-1 带入：拉回函方式=传真/电子邮件�?�?映射 confirm_index/entity_name/reply_method �?�?confirm_index 去重 �?_source
  - _需�?5.2, 5.3; 属�?P3_
- [x] 2.5 buildPayload（_format: reliability-d07-v1�?
  - _需�?8.3_
- [x] 2.6 数据层单测：CRUD + 条件列值保�?+ metrics + D0-1 去重 + buildPayload
  - _属�?P1/P2/P3_

### Sprint 3：ReliabilityGrid + 条件�?+ tooltip + 看板 + 结论

- [x] 3.1 新增 `ReliabilityGrid.vue`�?4�?el-table + 分组表头(基本6�?验证7�?结论1列按区着�? + 条件�?is_original_returned控制7列灰/�? + useCellSelection + 右键 + 工具�?
  - _需�?1.1, 1.2, 1.4, 2.1, 2.2_
- [x] 3.2 �?/�?/�? tooltip：列标题问号图标 hover 展示 FIELD_TOOLTIPS_D07 完整文本
  - _需�?3.1, 3.2, 3.3, 3.4_
- [x] 3.3 组件顶部精简说明（电子回函风险概述一行）
  - _需�?3.5_
- [x] 3.4 新增 `ReliabilityDashboard.vue`：总行/已验证率/不可靠数 + 折叠
  - _需�?6.4_
- [x] 3.5 D0-1 带入接入：工具栏"�?D0-1 带入电子回函" + 视觉标识 + 跳转链接
  - _需�?5.1, 5.4, 5.5_
- [x] 3.6 质量红线：未验证(�?/结论�?�?/不可�?�?
  - _需�?6.1, 6.2, 6.3_
- [x] 3.7 新增 `ReliabilityConclusion.vue`：审计说�?文本+placeholder提示记录内容) + 审计结论(枚举+文本)
  - _需�?4.1, 4.2, 4.3_
- [x] 3.8 Grid+条件�?tooltip+看板+红线+结论 spec
  - _需�?1, 2, 3, 4, 6; 属�?P1/P2/P5_

### Sprint 4：组�?+ 注册 + 回归实测

- [x] 4.1 新增 `GtConfirmationReliability.vue`：组�?Dashboard+Grid+Conclusion+接入 composable
  - _需�?1_
- [x] 4.2 `htmlRendererRegistry.ts` 注册 confirmation-reliability；后�?dispatch D0-7 sheet �?componentType
  - _需�?1_
- [x] 4.3 旧格式兼容降�?GtGridSheet 只读
  - _需�?9.2; 属�?P4_
- [x] 4.4 保存端到�?+ 回归（render-config 冒烟 + 枚举测试�? 只读回归
  - _需�?8.3, 9.1, 9.3_
- [x] 4.5 Playwright D0-7 端到�?0 error：从 D0-1 带入电子回函→条件列展开(寄回=�?→填�?身份确认+�?邮箱验证+致电→结论→保存→重开持久化→�?D0-1
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "wave": 2, "tasks": ["1.6", "2.1", "2.2"] },
    { "wave": 3, "tasks": ["2.3", "2.4", "2.5"] },
    { "wave": 4, "tasks": ["2.6"] },
    { "wave": 5, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "wave": 6, "tasks": ["3.5", "3.6", "3.7"] },
    { "wave": 7, "tasks": ["3.8", "4.1", "4.2"] },
    { "wave": 8, "tasks": ["4.3", "4.4", "4.5"] }
  ]
}
```

## Notes

- D0-7 是中等宽度表（~14列），单层网格形态（�?D0-4 类似），无需 master-detail�?
- **�?/�?/�? 是本 spec 提示落位的核�?*—�? 块详细操作指引（各含多条具体方法），�?对应列标题问�?tooltip"精确就近呈现（不堆底），完整原文同步�?guidance 侧栏�?
- 条件列设计（寄回原件=是→灰掉验证6列）减少信息噪音：已收回原件的无需验证�?
- D0-7 �?D0-1 带入"回函方式=传真/电子邮件"的行（D0-1 有回函方式列），免手查哪些函证是电子回函�?
- 技术提�?号链接（https://www.gt-china.com/article_view.php?id=9691）在�? tooltip �?guidance 中展示，不内嵌外部页面�?
- 铁律：组�?props 不可变；只读路径无编辑控件；改动�?Playwright 实测�?
