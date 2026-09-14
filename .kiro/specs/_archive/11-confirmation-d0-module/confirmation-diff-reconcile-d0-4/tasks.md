# Implementation Plan: confirmation-diff-reconcile-d0-4

## Overview

�?D0-4 函证差异调节表创�?*共享专用组件** `GtConfirmationDiffReconcile`（科目列下拉+自定义使一张底稿跨科目通用 + 差异自动计算 + 合计可按科目分组 + �?D0-1 自动带入差异�?+ 差异原因分析表自动聚�?+ 是否调整下游联动 + 质量红线 + 看板）。与 D0-1/D0-2/D0-3 同构，大量复用其 composable/组件�? Sprint：类型枚�?�?数据�?差异/合计/聚合/D0-1带入) �?网格+科目�?分析�?�?看板+警示+结论+导入 �?组装注册联动回归�?

依赖：grid-sheet-inline-editing（D0-1）等 spec �?useCellSelection/CellContextMenu/useDictStore/useExcelIO/wp_html_save/跨底稿引用机�?先行就绪可复用�?

## Tasks

### Sprint 1：类�?+ 枚举（地基）

- [x] 1.1 新增 `diffReconcileTypes.ts`：DiffRow(�?subject/差异/差异类型/是否调整) / DiffAnalysisRow / DiffMetrics / 重要性配�?/ DiffReconcilePayload
  - _需�?1.1, 2.1, 5.1, 6.1_
- [x] 1.2 新增 `diffReconcileEnums.ts`：dictKey 映射（confirmation_subject / confirmation_diff_type / yes_no�?
  - _需�?9.1_
- [x] 1.3 后端 `system_dicts.py _DICTS` �?`confirmation_subject`（应收账�?合同负�?销售收�?应收票据/合同资产/预付账款/应付账款/预收账款/其他应收�?其他应付�?银行存款/短期借款/长期借款�? `confirmation_diff_type`（时间性差�?记账差异/未达账项/其他差异�?
  - _需�?9.1_
- [x] 1.4 后端枚举测试 + 编制指引 `wp_guidance/D0-4.json`（差异调查要�?错报与舞弊评�?替代程序触发条件�?
  - _需�?12.2, 9.1_

### Sprint 2：useDiffReconcileData + useDiffAnalysis + useD01DiffImport（数据核心）

- [x] 2.1 新增 `useDiffReconcileData.ts`：从 htmlData 解析 rows + watch 重建 + dirty
  - _需�?2.5; 属�?P8_
- [x] 2.2 rows CRUD：addRow/deleteRow/updateField/importRows
  - _需�?10.1, 10.4_
- [x] 2.3 computeDifference（发函−回函，精确小数，只读不可手填�? totals + subjectSubtotals（按科目分组小计�?
  - _需�?3.1, 3.2, 3.3, 3.5; 属�?P1/P2_
- [x] 2.4 metrics computed（总笔�?差异净额合�?差异绝对值合�?已分析率/需调整笔数金额/超重要性笔�?类型分布�?
  - _需�?7.5, 11.1, 11.2; 属�?P7_
- [x] 2.5 新增 `useDiffAnalysis.ts`：按 diff_type 聚合笔数+净额金�?合计 + 未分类计�?+ 明细变化重算；仅 note/action 持久�?analysis_notes)，笔�?金额重算不入�?
  - _需�?5.2, 5.3, 5.4, 5.5; 属�?P3_
- [x] 2.6 新增 `useD01DiffImport.ts`：拉 D0-1 已回函且不符(差异�?)�?+ 字段映射 + confirm_index 去重 + _source 标识 + 未回函不带入 + 降级
  - _需�?4.2, 4.3, 4.4, 4.5, 4.7; 属�?P5_
- [x] 2.7 buildPayload() 返回 DiffReconcilePayload（_format: diff-reconcile-v1，含 rows/analysis_notes/audit_note/conclusion/materiality_config�?
  - _需�?10.3_
- [x] 2.8 数据层单测：CRUD + 差异自动�?+ 合计/分组小计 + metrics + 聚合 + D0-1 去重映射 + buildPayload
  - _属�?P1/P2/P3/P5/P7_

### Sprint 3：DiffGrid + 科目�?+ 差异原因分析表（核心 UI�?

- [x] 3.1 新增 `DiffGrid.vue`�?1 �?el-table + 合计�?+ 金额右对齐千分位 + 差异=0 行淡�?+ 多�?+ 工具栏（新增/删除/从D0-1带入/保存/导入/导出�?
  - _需�?2.1, 2.4, 3.4, 10.1_
- [x] 3.2 科目列：el-select 下拉 confirmation_subject + allow-create 自定义；自定义值参与分组合�?
  - _需�?1.1, 1.2, 1.3, 1.4; 属�?P4_
- [x] 3.3 差异列只读自�?+ 差异类型/是否调整 el-select + 金额输入校验
  - _需�?3.1, 5.1, 6.1_
- [x] 3.4 按科目分组视图：每科目小计行 + 全表合计（可切换分组开关）
  - _需�?3.3; 属�?P2_
- [x] 3.5 useCellSelection + CellContextMenu 右键（复制行/插入/删除/复制索引/跳转 D0-1�?
  - _需�?2.2, 10.2_
- [x] 3.6 新增 `DiffAnalysisTable.vue`�? 差异类型 + 合计；笔�?金额只读自动聚合，原因说�?应对措施可编�?
  - _需�?5.2, 5.3; 属�?P3_
- [x] 3.7 字段�?tooltip 提示就近落位（差异自动算/差异类型口径/证据索引/是否调整→AJE或替代程序）
  - _需�?12.1, 12.3_
- [x] 3.8 DiffGrid + 分析�?spec：科目下拉自定义/差异自动/合计分组/聚合/只读守卫
  - _需�?1, 3, 5; 属�?P1/P2/P3/P4/P9_

### Sprint 4：看�?+ 质量警示 + 下游联动 + 结论 + 导入

- [x] 4.1 新增 `DiffDashboard.vue`：总笔�?差异合计/已分析率/需调整/超重要�?+ 类型分布 + 异常高亮 + 折叠
  - _需�?11.1, 11.2, 11.3, 11.4_
- [x] 4.2 D0-1 带入接入：工具栏"�?D0-1 带入差异�? + 自动取数视觉标识 + 跳转 D0-1 链接
  - _需�?4.1, 4.4, 4.6_
- [x] 4.3 质量红线警示：差异未分析(�?/缺证�?�?/超重要�?�?/疑似错报(提示)
  - _需�?7.1, 7.2, 7.3, 7.4; 属�?P7_
- [x] 4.4 是否调整下游联动：need_adjust=是→提示 adjust_ref；未达账�?未回函→替代程序 D0-5/D0-6 跳转
  - _需�?6.2, 6.3, 6.5; 属�?P6_
- [x] 4.5 新增 `DiffConclusion.vue`：审计说�?+ 审计结论（枚�?文本�? 未决事项提示
  - _需�?8.1, 8.2, 8.3_
- [x] 4.6 批量导入：复�?useExcelIO，解析→预览→批量新增；导出模板
  - _需�?10.4, 10.5_
- [x] 4.7 重要性配置：默认取项�?*实际执行重要�?*(performance materiality，B15/Materiality)可手填覆盖，驱动超重要性警�?
  - _需�?7.3_
- [x] 4.8 看板+警示+联动+结论+导入 spec
  - _需�?6, 7, 8, 11; 属�?P6/P7_

### Sprint 5：组�?+ 注册 + 共享底稿 + 回归实测

- [x] 5.1 新增 `GtConfirmationDiffReconcile.vue`：组�?Dashboard+DiffGrid+DiffAnalysisTable+DiffConclusion+接入�?composable
  - _需�?1, 2, 8, 11_
- [x] 5.2 `htmlRendererRegistry.ts` 注册 confirmation-diff-reconcile；后�?dispatch D0-4 sheet �?componentType（共享底稿：科目无关跨循环映射）
  - _需�?1.6_
- [x] 5.3 旧格式兼容降�?GtGridSheet 只读
  - _需�?13.2; 属�?P8_
- [x] 5.4 共享底稿验证 + 跨底稿联动：科目列跨科目混合可用 + 标题科目集合汇�?+ 上游 D0-1 带入/下游 D0-5/D0-6 跳转数据源端
  - _需�?1.4, 1.5, 4.6, 6.3_
- [x] 5.5 保存端到�?+ 回归（render-config 冒烟 + system_dicts 测试�? 只读回归
  - _需�?10.3, 13.1, 13.3_
- [x] 5.6 Playwright D0-4 端到�?0 error：从 D0-1 带入差异行→选科�?含自定义)→差异自动算→分类→分析表自动聚合→超重要性警示→标是否调整跳转→按科目分组合计→保存→重开持久化→�?D0-1/D0-5/D0-6
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3"] },
    { "wave": 2, "tasks": ["1.4", "2.1"] },
    { "wave": 3, "tasks": ["2.2", "2.3"] },
    { "wave": 4, "tasks": ["2.4", "2.5", "2.6"] },
    { "wave": 5, "tasks": ["2.7", "2.8"] },
    { "wave": 6, "tasks": ["3.1", "3.2", "4.1"] },
    { "wave": 7, "tasks": ["3.3", "3.4", "3.5", "3.6", "3.7"] },
    { "wave": 8, "tasks": ["3.8", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7"] },
    { "wave": 9, "tasks": ["4.8", "5.1", "5.2", "5.3", "5.4"] },
    { "wave": 10, "tasks": ["5.5", "5.6"] }
  ]
}
```

## Notes

- �?D0-1/D0-2/D0-3 同构：复�?useCellSelection / CellContextMenu / useDictStore / useExcelIO / wp_html_save 保存链路 / 编制指引侧栏 / 跨底稿引用机制�?
- **共享底稿�?D0-4 的核心设�?*：componentType 科目无关，一张表�?科目"列（下拉 confirmation_subject + allow-create 自定义）承载多科目差异，按科目分组合计；跨循环复用（不绑�?D 循环）。这正是用户"增加科目列做共享底稿"的诉求�?
- **三层自动派生**（最大系统增值）：①差异=发函−回函自动算 ②合�?科目小计实时 ③差异原因分析表按差异类型自动聚合笔�?金额（不手数手加）�?
- **D0-1 联动**：从函证结果汇总表自动带入差异�? 行（�?confirm_index 去重），免誊抄；上游 D0-1、下�?D0-5/D0-6 + AJE 走既有跨底稿引用机制�?
- 金额用精确小数（避免浮点漂移）；金额单位默认"�?；差�?0 行淡化�?*差异/分析�?看板金额口径=净�?带符�?**，看板另给差异绝对值合计避免正负抵消误导；分析表只持久�?note/action，笔�?金额派生重算�?
- **D0-4 只调�?回函不符差异"**；未回函（无回函金额可比）不在此调节，归替代程序 D0-5/D0-6，D0-1 带入时不纳入�?
- 超重要性警示依赖重要性配置（默认�?*实际执行重要�?* performance materiality，B15/Materiality），无配置不误报�?
- D0-4 是中等宽度可计算明细表（�?11 列），主形�?单层可编辑网�?自动派生，无需 master-detail；编辑区+右键对齐报表模块习惯�?
- 铁律：组�?props 不可变（composable 深拷贝）；只读路径无编辑控件；service �?flush �?commit；改动后 Playwright 实测�?
