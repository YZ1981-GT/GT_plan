# Implementation Plan: confirmation-fraud-risk-d0-8

## Overview

�?D0-8 函证程序舞弊风险评价表创建专用组�?`GtConfirmationFraudRisk`（预置检查清单~19条舞弊风险迹�?+ 逐条评估 + 举例tooltip精确就近 + 编制说明4条落�?+ 条件高亮 + 汇总→B50联动）。形态为 d-form-qa 类检查表，非宽表非备忘录�? Sprint：类�?预置常量+提示 �?检查清�?汇�?看板+结论 �?注册回归实测�?

依赖：复�?useCellSelection/CellContextMenu/useDictStore/wp_html_save�?

## Tasks

### Sprint 1：类�?+ 预置常量 + 枚举 + 提示（地基）

- [x] 1.1 新增 `fraudRiskTypes.ts`：FraudRiskItem(seq/description/is_exist/source_ref/countermeasure/_preset) / FraudRiskSummary / Metrics / Payload
  - _需�?1.1, 1.2_
- [x] 1.2 新增 `PRESET_FRAUD_ITEMS` 常量：预�?19 条舞弊风险迹象完整描述文本（�?tooltip 标记�?
  - _需�?1.1; 属�?P1_
- [x] 1.3 新增 `ITEM_TOOLTIPS_D08` 常量：第14/18/19条等的举�?场景描述文本
  - _需�?2.1, 2.2, 2.3_
- [x] 1.4 新增 `fraudRiskEnums.ts`：复�?yes_no_na
  - _需�?7.1_
- [x] 1.5 编制指引 `wp_guidance/D0-8.json`（编制说�?条完�?+ 准则引用 + 举例场景�?
  - _需�?2.5, 3.1_

### Sprint 2：useFraudRiskData + 检查清�?+ 汇�?+ 看板 + 结论

- [x] 2.1 新增 `useFraudRiskData.ts`：从 htmlData 解析 items（合并预�?已有不覆盖）+ summary + dirty
  - _属�?P4_
- [x] 2.2 items CRUD：addItem/deleteItem/updateItem + 保留预置标记
  - _需�?1.3, 8.1_
- [x] 2.3 metrics computed（total/exist_count/with_measure/without_measure�?
  - _需�?4.4; 属�?P3_
- [x] 2.4 buildPayload（_format: fraud-risk-d08-v1�?
  - _需�?8.3_
- [x] 2.5 新增 `FraudRiskChecklist.vue`：预置条目渲�?+ 是否存在枚举 + 索引�?可跳�? + 应对措施�?+ 条件高亮(是→行高�?应对空→橙警�? + 工具�?含导�?导出) + 右键 + useCellSelection(选区/复制/粘贴) + 举例tooltip(ITEM_TOOLTIPS_D08) + 增删自定义行
  - _需�?1, 2, 3, 4.1, 4.2, 8.1, 8.2, 8.4, 8.5_
- [x] 2.6 编制说明4条精确落位：①→顶部说明 / ②→应对措施placeholder / ③→索引列tooltip / ④→应对列tooltip+�?是条件提�?
  - _需�?3.1, 3.2, 3.3, 3.4_
- [x] 2.7 新增 `FraudRiskDashboard.vue`：总条�?存在迹象/已填应对/未填应对 + 折叠
  - _需�?4.4_
- [x] 2.8 新增 `FraudRiskSummary.vue`：财务报表层�?认定层次/初步应对 + B50跳转
  - _需�?4.3, 5.1_
- [x] 2.9 新增 `FraudRiskConclusion.vue`：审计说�?结论+未决提示
  - _需�?5.2, 5.3_
- [x] 2.10 Checklist+汇�?看板+结论 spec：预置完�?可编辑可�?条件高亮/提示落位/只读守卫
  - _需�?1, 2, 3, 4, 5; 属�?P1/P2/P3/P5_

### Sprint 3：组�?+ 注册 + 回归实测

- [x] 3.1 新增 `GtConfirmationFraudRisk.vue`：组�?Dashboard+Checklist+Summary+Conclusion+接入 composable
  - _需�?1_
- [x] 3.2 `htmlRendererRegistry.ts` 注册 confirmation-fraud-risk；后�?dispatch D0-8 sheet �?componentType（跨循环：D0-8/E0-8/F0-8/K0-8 等）
  - _需�?6.3_
- [x] 3.3 旧格式兼容降�?GtGridSheet 只读
  - _需�?9.2; 属�?P4_
- [x] 3.4 保存端到�?+ 回归（render-config 冒烟 + 枚举测试�? 只读回归
  - _需�?8.3, 9.1, 9.3_
- [x] 3.5 Playwright D0-8 端到�?0 error：打开预置清单→第3条标�?填应对→�?4条查看tooltip举例→新增自定义条目→汇总填风险→结论→保存→重开持久化→跳B50
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "wave": 2, "tasks": ["2.1", "2.2", "2.3", "2.4"] },
    { "wave": 3, "tasks": ["2.5", "2.6", "2.7", "2.8", "2.9"] },
    { "wave": 4, "tasks": ["2.10", "3.1", "3.2"] },
    { "wave": 5, "tasks": ["3.3", "3.4", "3.5"] }
  ]
}
```

## Notes

- D0-8 形态为**检查清�?*（d-form-qa 类），与 D0-1~D0-7 的网�?备忘录不同：固定预置条目 + 每条评估 3 个字段（是否存在/索引/应对�? 自由扩展�?
- **红框内容（提�?举例）的落位是本 spec 重心**：第14条举�?"银行函证未回�?回函率异常偏�?债权人回函率�?) �?tooltip 就近；编制说�?条按"影响哪个字段"分别落到顶部/placeholder/tooltip/条件提示�?
- 预置条目源自《审计准则问题解答第2号——函证》，首次加载含全�?9条；用户可编辑描述（适配实际情况�? 可新增自定义条目�?
- 跨循环复用（D0-8/E0-8/F0-8/K0-8/L0-7 等）：相�?componentType，条目内容完全一致（准则通用）�?
- 汇总行最后固定索�?B50（风险评估模块）�?可跳转�?
- 铁律：组�?props 不可变；只读路径无编辑控件；改动�?Playwright 实测�?
