# Implementation Plan: confirmation-diff-checklist-d0-4b

## Overview

�?D0-4b 函证差异检查表（示例）创建专用组件 `GtConfirmationDiffChecklist`（多公司 master-detail + A-I 双向调节公式链全自动 + B/C/F/G 未达明细子表自动合计 + 科目列共�?+ �?D0-4 联动带入 + 经理复核红线）。D0-4b �?D0-4 差异汇总的"穿透深�?——对每家差异公司做结构化双向余额调节�? Sprint：类型枚�?�?数据�?公式�?子表合计) �?master+detail+子表 �?看板+联动+导入 �?组装注册回归�?

依赖：confirmation-diff-reconcile-d0-4（D0-4 差异调节汇总表）为上游数据源；复用 D0-1~D0-4 spec 的基础能力�?

## Tasks

### Sprint 1：类�?+ 枚举（地基）

- [x] 1.1 新增 `diffChecklistTypes.ts`：ChecklistCompany(�?a_reply/b_rows/c_rows/e_book/f_rows/g_rows) / SubTableRow / Metrics / DiffChecklistPayload
  - _需�?1.2, 2.1, 3.1_
- [x] 1.2 新增 `diffChecklistEnums.ts`：复�?confirmation_subject / yes_no
  - _需�?9.1_
- [x] 1.3 编制指引 `wp_guidance/D0-4b.json`（双向余额调节操作指�?A-I 公式含义/未达账项登记要求/是否调整判断标准�?
  - _需�?8_

### Sprint 2：useDiffChecklistData（数据核�?+ 公式�?+ 子表合计�?

- [x] 2.1 新增 `useDiffChecklistData.ts`：从 htmlData 解析 companies + watch 重建 + dirty
  - _属�?P5_
- [x] 2.2 companies CRUD：addCompany/deleteCompany/updateCompany/importCompanies
  - _需�?10.1_
- [x] 2.3 computeFormula：B_total=∑b_rows.amount / C同理 / D=A+B-C / F同理 / G同理 / H=E+F-G / I=H-D（精确小数，只读自动�?
  - _需�?2.2-2.10; 属�?P1/P2_
- [x] 2.4 companyStatus 派生（I=0→balanced / �?→diff / |I|≥materiality→over_materiality�? metrics（�?已平/有差�?超重要�?完成率）
  - _需�?2.9, 7.1, 7.2; 属�?P3_
- [x] 2.5 D0-4 带入：拉 D0-4 差异�? �?�?映射 entity_name/subject/A/E/confirm_index �?entity_name+subject 去重 �?_source 标识
  - _需�?5.2, 5.3, 5.4; 属�?P4_
- [x] 2.6 buildPayload（_format: diff-checklist-v1，含 companies + global_note + materiality_config�?
  - _需�?10.3_
- [x] 2.7 数据层单测：CRUD + 公式链正�?+ 子表增删→合计→公式联动 + 差异状�?+ D0-4 去重 + buildPayload
  - _属�?P1/P2/P3/P4_

### Sprint 3：ChecklistMaster + ChecklistDetail + DetailSubTable（核�?UI�?

- [x] 3.1 新增 `ChecklistMaster.vue`：el-table 关键�?+ 差异状态徽�?+ 科目下拉 + 工具�?+ 行展开 + 空�?
  - _需�?1.1, 1.5, 4.1_
- [x] 3.2 新增 `ChecklistDetail.vue`：A-I 结构化表单（A→B子表→C子表→D→E→F子表→G子表→H→I），D/H/I 只读自动
  - _需�?1.2, 2_
- [x] 3.3 新增 `DetailSubTable.vue`（复用性高）：通用未达明细子表（序�?日期1/日期2/凭证�?金额/索引/是否调整 + 合计�?+ 增删�?+ 右键 + useCellSelection 选区/复制/粘贴/求和�?
  - _需�?3.1, 3.2, 3.3_
- [x] 3.4 A-I 区块标题含义描述 + 金额右对齐千分位 + I�? 高亮 + 字段�?tooltip 提示
  - _需�?2, 7.3_
- [x] 3.5 右键菜单：master 行（复制/删除/跳转 D0-4/D0-1�? 子表行（复制/插入/删除�?
  - _需�?10.2_
- [x] 3.6 Master+Detail+子表 spec：展开/公式联动/子表增删合计/差异状�?只读守卫
  - _需�?1, 2, 3; 属�?P1/P2/P3/P6_

### Sprint 4：看�?+ D0-4 联动 + 是否调整 + 审计说明 + 导入

- [x] 4.1 新增 `ChecklistDashboard.vue`：总公�?已平/有差�?超重要�?完成�?+ 折叠 + 异常高亮
  - _需�?7.4, 7.5_
- [x] 4.2 D0-4 带入接入：工具栏"�?D0-4 带入" + 自动取数标识 + 跳转 D0-4/D0-1 链接
  - _需�?5.1, 5.4, 5.6_
- [x] 4.3 是否调整下游联动：明细行 need_adjust=是→提示�?ref_index；I�? + 未调整→橙；差异无法解释→红提示
  - _需�?6.1, 6.2, 6.3; 属�?P3_
- [x] 4.4 新增 `ChecklistAuditNote.vue`：每公司审计说明 + 全局审计结论
  - _需�?8.1, 8.2_
- [x] 4.5 批量导入：复�?useExcelIO，解析→预览→批量新增；导出
  - _需�?10.4, 10.5_
- [x] 4.6 重要性配置：默认取实际执行重要性可手填覆盖
  - _需�?7.2_
- [x] 4.7 看板+联动+调整+审计说明+导入 spec
  - _需�?5, 6, 7, 8; 属�?P3/P4_

### Sprint 5：组�?+ 注册 + 回归实测

- [x] 5.1 新增 `GtConfirmationDiffChecklist.vue`：组�?Dashboard+Master+Detail+AuditNote+接入 composable
  - _需�?1, 2, 3, 7_
- [x] 5.2 `htmlRendererRegistry.ts` 注册 confirmation-diff-checklist；后�?dispatch D0-4b sheet �?componentType（科目无关跨循环�?
  - _需�?4.3_
- [x] 5.3 旧格式兼容降�?GtGridSheet 只读
  - _需�?11.2; 属�?P5_
- [x] 5.4 保存端到�?+ 回归（render-config 冒烟 + 枚举测试�? 只读回归
  - _需�?10.3, 11.1, 11.3_
- [x] 5.5 Playwright D0-4b 端到�?0 error：新增公司→�?D0-4 带入→填 B/C 明细→D 自动→填 F/G→H/I 自动→差异状态红→标调整→保存→重开持久化→�?D0-4/D0-1
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3"] },
    { "wave": 2, "tasks": ["2.1", "2.2"] },
    { "wave": 3, "tasks": ["2.3", "2.4", "2.5"] },
    { "wave": 4, "tasks": ["2.6", "2.7"] },
    { "wave": 5, "tasks": ["3.1", "3.2", "3.3"] },
    { "wave": 6, "tasks": ["3.4", "3.5", "4.1"] },
    { "wave": 7, "tasks": ["3.6", "4.2", "4.3", "4.4", "4.5", "4.6"] },
    { "wave": 8, "tasks": ["4.7", "5.1", "5.2"] },
    { "wave": 9, "tasks": ["5.3", "5.4"] },
    { "wave": 10, "tasks": ["5.5"] }
  ]
}
```

## Notes

- **D0-4b �?D0-4 是穿透关�?*：D0-4 差异汇总表列出差异概况（哪些笔有差�?多少金额/什么类型），D0-4b 对具体公司做"双向余额调节深挖"（A-I 公式链逐笔分析差异来源）。D0-4 的一行（一笔差异）穿透到 D0-4b 的一家公司调节�?
- **A-I 公式链是�?spec 核心增�?*�? 步公式全自动（用户只�?A/E + B/C/F/G 明细行金额），D/H/I 只读自动。消灭了手算错误风险�?
- **多公�?master-detail 解决"每公司一�?sheet"问题**：现场经理复核时一览所有公司进�?差异状态（�?�?红），无需�?Excel 底部切换多个 tab�?
- **DetailSubTable 复用性高**：B/C/F/G 四区结构完全相同（日�?凭证�?金额/索引/是否调整），用一个通用子表组件 section prop 区分即可�?
- D0-4b 标题�?应收账款函证差异检查表-XX公司"�?应收账款"由科目列承载（复�?confirmation_subject），"XX公司"�?master 行的 entity_name 承载，实现一张底稿多科目多公司�?
- 铁律：组�?props 不可变（composable 深拷贝）；只读路径无编辑控件；改动后 Playwright 实测�?
