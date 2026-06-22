# Implementation Plan: confirmation-entity-verify-d0-2

## Overview

�?D0-2 核实被函证单位信息创建专用组�?`GtConfirmationEntityVerify`�? 阶段生命周期 + 条件字段 + 企查查自动核�?+ 行内一致性自动比�?+ 跨行反舞弊红�?+ 质量红线 + 双视�?+ 说明1-5 落位）。定位为**反舞弊核对台**，与 D0-1（confirmation-summary）同构，大量复用�?composable/组件并共享单位主数据�? Sprint：类型枚�?�?数据�?�?明细编辑+提示 �?看板+自动核对+反舞弊检�?导入 �?组装注册回归�?

依赖：grid-sheet-inline-editing（D0-1）spec �?useCellSelection/CellContextMenu/useConfirmationAutoFetch/ConfirmationFullGrid/wp_html_save 基础先行就绪可复用�?

## Tasks

### Sprint 1：类�?+ 枚举 + 字段提示常量（地基）

- [x] 1.1 新增 `entityVerifyTypes.ts`：EntityVerifyRow(�?8字段) / ProgressMetrics / EntityVerifyPayload
  - _需�?1.2, 5.4_
- [x] 1.2 新增 `entityVerifyEnums.ts`：dictKey 映射（method/reply_method/yes_no/confirmation_send_result�?
  - _需�?6.1_
- [x] 1.3 新增 `FIELD_HINTS` 常量：说�?-5 按字段映射（qcc_address/return_reason/reason_reasonable/second_result/reply_method/method 电子函证�?
  - _需�?4.1-4.6_
- [x] 1.4 后端 `system_dicts.py _DICTS` �?`confirmation_send_result`（送抵/退回）；复�?D0-1 其余枚举
  - _需�?6.1_
- [x] 1.5 后端枚举测试 + 编制指引 `wp_guidance/D0-2.json`（准则程�?检查支持性文�?确认联系人身�?电子平台文本�?
  - _需�?4.7, 6.1_

### Sprint 2：useEntityVerifyData composable（数据核心）

- [x] 2.1 新增 `useEntityVerifyData.ts`：从 htmlData 解析 rows + watch 重建 + dirty
  - _需�?1.4; 属�?P4_
- [x] 2.2 rows CRUD：addRow/deleteRow/updateField/importRows
  - _需�?7.1, 7.4_
- [x] 2.3 progressMetrics computed（核实完成率/退回率/橙红警示数）
  - _需�?5.4; 属�?P3_
- [x] 2.4 buildPayload() 返回 EntityVerifyPayload（_format: entity-verify-v1�?
  - _需�?7.3_
- [x] 2.5 useEntityVerifyData 单测：CRUD + progressMetrics 实时 + buildPayload + 条件字段保留
  - _属�?P1/P3_

### Sprint 3：Master + Detail（核�?UI + 条件字段 + 提示�?

- [x] 3.1 新增 `EntityVerifyMaster.vue`：el-table 关键 7 �?+ 行状态徽章列(一�?存疑/舞弊红旗) + 多�?+ 工具栏（新增/删除/保存/导入/导出�? 行展开
  - _需�?1.1, 7.1, 12.1_
- [x] 3.2 新增 `EntityVerifyDetail.vue`�? 阶段 el-collapse + 枚举 el-select + 文本/数值控�?
  - _需�?1.2, 6.2_
- [x] 3.3 条件字段：is_second_send �?④⑤显隐 / first_result=送抵 �?折叠退回核�?/ address_match=一�?�?折叠核实字段 / 电子函证提示
  - _需�?2.1, 2.2, 2.3, 2.4, 2.5; 属�?P1_
- [x] 3.4 字段提示：FIELD_HINTS �?el-tooltip/问号图标注入对应字段（说�?-5 就近呈现�?
  - _需�?4.1-4.6_
- [x] 3.5 右键菜单：复�?useCellSelection + CellContextMenu slot（复制行/插入/删除/复制函证索引�?
  - _需�?7.2_
- [x] 3.6 Master+Detail spec：展开/条件字段保留/枚举/提示落位/只读守卫
  - _需�?1.3, 2, 4; 属�?P1/P5_

### Sprint 4：看�?+ 企查查自动核�?+ 反舞弊检�?+ 质量警示 + 导入 + 完整表格视图

- [x] 4.1 新增 `EntityVerifyDashboard.vue`：核实完成率/退回率 + 警示计数 + 舞弊红旗计数 + 折叠
  - _需�?5.4, 12.1, 14.1_
- [x] 4.2 扩展 useConfirmationAutoFetch：fetchQccAddress(企查查接�? + autoJudgeAddressMatch（一致性自动判定，可覆盖标 _overridden�?
  - _需�?3.1, 3.2; 属�?P2_
- [x] 4.3 自动取数带入：被审计单位提供信息→单位全�?地址/联系�?电话；函证索引关�?D0-1；来源标�?
  - _需�?3.3, 3.4, 3.5_
- [x] 4.4 质量红线警示：地址存疑(�?/退回原因不合理(�?/二次退�?�?
  - _需�?5.1, 5.2, 5.3_
- [x] 4.5 批量导入：复�?useExcelIO，解析→预览→批量新增；导出模板
  - _需�?7.4, 7.5_
- [x] 4.6 完整表格视图：复�?同构 ConfirmationFullGrid�?8列分5区块着�?冻结索引�?斑马�?空值淡�?+ useCellSelection 选区复制粘贴求和�?
  - _需�?8.1, 8.2_
- [x] 4.7 视图切换 + localStorage 记忆 + 两视图共享数�?
  - _需�?8.3, 8.4_
- [x] 4.8 新增 `useFraudFlagDetect.ts`：行内一致性自动比对（5 �?CONSISTENCY_RULES，规范化+相似度，依赖空留空，覆盖�?_overridden�?
  - _需�?13.1, 13.2, 13.3, 13.4; 属�?P7_
- [x] 4.9 useFraudFlagDetect 跨行检测：地址聚类/电话号段相邻/联系人撞员工名单(可取则查,不可取跳�?/同一回函寄件�?+ 阈值可�?+ runScreening 一键筛�?
  - _需�?14.1, 14.2, 14.3, 14.4, 14.5; 属�?P8_
- [x] 4.10 新增 `EntityVerifyFraudPanel.vue` + 行状态徽章：detail 顶部红旗清单逐条 + master 行状�?一�?存疑/舞弊红旗 �?�?�? + 命中单元格标�?
  - _需�?12.1, 12.2, 12.3, 13.3, 14.2; 属�?P9_
- [x] 4.11 反舞弊检测单测：5 规则初判/留空/覆盖(P7) + 跨行对称标注/重算/撞名跳过(P8) + 行状态派�?P9)
  - _属�?P7/P8/P9_
- [x] 4.12 看板+自动核对+警示+导入+完整表格 spec
  - _需�?3, 5, 7, 8; 属�?P2/P3_

### Sprint 5：组�?+ 注册 + D0-1 联动 + 回归实测

- [x] 5.1 新增 `GtConfirmationEntityVerify.vue`：组�?Dashboard+FraudPanel+[列表:Master+Detail / 完整表格]+视图切换+接入 useEntityVerifyData+useFraudFlagDetect
  - _需�?1, 8, 10, 12_
- [x] 5.2 `htmlRendererRegistry.ts` 注册 confirmation-entity-verify；后�?dispatch D0-2 sheet �?componentType
  - _需�?9.3_
- [x] 5.3 旧格式兼容降�?GtGridSheet 只读
  - _需�?11.2; 属�?P4_
- [x] 5.4 D0-1 联动 + 单位主数据共享：函证索引可跳�?D0-1 + 暴露核实通过单位信息�?D0-1 引用（数据源端）；同 confirm_index 单位字段单源共享(不存两份副本)，单侧缺失各自独立可�?
  - _需�?9.1, 9.2, 15.1, 15.2, 15.3, 15.4; 属�?P6/P10_
- [x] 5.5 默认布局聚焦：二次发函区默认折叠、列表视图默认、看板首屏可�?
  - _需�?10.1, 10.2, 10.3_
- [x] 5.6 保存端到�?+ 回归（render-config 冒烟 + system_dicts 测试�? 只读回归
  - _需�?7.3, 11.1, 11.3_
- [x] 5.7 Playwright D0-2 端到�?0 error：新增核实行→企查查比对→退回→二次发函条件展开→警示→保存→重开持久化→�?D0-1
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "wave": 2, "tasks": ["1.5", "2.1"] },
    { "wave": 3, "tasks": ["2.2", "2.3"] },
    { "wave": 4, "tasks": ["2.4", "2.5"] },
    { "wave": 5, "tasks": ["3.1", "3.2", "4.1"] },
    { "wave": 6, "tasks": ["3.3", "3.4", "3.5", "4.2", "4.6"] },
    { "wave": 7, "tasks": ["3.6", "4.3", "4.4", "4.5", "4.7", "4.8"] },
    { "wave": 8, "tasks": ["4.9", "4.10", "4.12", "5.1", "5.2"] },
    { "wave": 9, "tasks": ["4.11", "5.3", "5.4", "5.5", "5.6"] },
    { "wave": 10, "tasks": ["5.7"] }
  ]
}
```

## Notes

- �?D0-1（grid-sheet-inline-editing）同构：复用 useCellSelection / CellContextMenu / useDictStore / useConfirmationAutoFetch / ConfirmationFullGrid / wp_html_save 保存链路 / 编制指引侧栏机制。建�?D0-1 spec 先落地基础能力，D0-2 复用�?
- **D0-2 定位为反舞弊核对�?*：最大系统增�?�?+ "是否一�?字段自动比对初判（需�?13）②跨行红旗检测（地址聚类/号段相邻/撞员工名�?同一回函寄件人，需�?14）③D0-1/D0-2 单位主数据单源共享（需�?15）④行状态徽�?红旗清单（需�?12）�?
- 一致性比�?相似度不引新依赖：优先复用既有规范化工具，无则本�?levenshtein/包含判定。员工名单不可取时撞名检测跳过不报错�?
- 说明1-5 = 字段�?tooltip（就近呈现）+ 完整准则�?guidance 侧栏（双落位）�?
- D0-2 是发函前核实，D0-1 是发函后汇总，通过"函证索引"一一对应；D0-2 提供单位信息数据源，D0-1 消费（消费端�?D0-1 spec）�?
- 两轮发函生命周期：信息核对→第一次发函→回函核对→退回核实→（条件）第二次发函→二次结果�?
- 铁律：组�?props 不可变（composable 深拷贝）；只读路径无编辑控件；改动后 Playwright 实测�?
