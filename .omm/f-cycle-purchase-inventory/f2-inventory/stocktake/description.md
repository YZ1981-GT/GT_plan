# F2 存货监盘（`f2-stocktake-bundle`）

主入口 `GtF2StocktakeBundle.vue`，后端 `_f2_stocktake.py`。
F 循环里唯一具备**计划 → 程序 → 问卷 → 抽盘 → 差异调节 → 倒轧 → 小结**完整闭环的子模块。

## 组件（`f2/stocktake/`）

| 组件 | 作用 |
|---|---|
| `F2TabStocktakePlan` | 监盘计划（时间/地点/人员/范围/抽盘比例），配 `f2StocktakePlanAiParse.ts` AI 解析客户盘点计划文本 |
| `F2TabStocktakeProcedure` | 监盘程序执行记录 |
| `F2TabStocktakeQuestionnaire` | 盘点内控问卷，题库 `f2StocktakeQuestionnaire.ts` + `F2StocktakeQuestionnaireDialog` 逐题作答 |
| `F2TabStocktakeSampleResult` | 抽盘结果（账面 vs 实盘、差异、原因） |
| `F2TabStocktakeReconcile` | 差异调节表 |
| `F2TabStocktakeRollforward` | 倒轧表（盘点日 → 资产负债表日），表体 `F2RollTable.vue` |
| `F2TabStocktakeSummary` | 监盘小结与结论 |
| `F2StocktakeSectionForm` | 段落型表单通用渲染（配置驱动） |
| `F2StocktakeSheetAttachments` | 各 sheet 附件（盘点表照片/客户盘点表扫描件） |

配置真源 `f2StocktakeConfigs.ts`（同一批组件按配置渲染多张源模板表）；`f2StocktakeSoftNav.css` 为软性内部导航样式。

## 审计逻辑要点

- **抽盘不是全盘**：抽盘比例与覆盖率是结论依据，比例过低要扩样（与抽样方法学同口径思路）
- **倒轧是关键**：盘点日 ≠ 资产负债表日时，必须由盘点日实盘数 ±期间收发 倒轧到期末账面，否则实盘证据无法支持期末余额
- **差异要落地**：抽盘差异 → 差异调节 → 需要调整的进 F2 调整分录（AJE），不能只记录不处理
- **AI 只解析不判断**：`f2StocktakePlanAiParse` 用于把客户盘点计划文本结构化成计划字段，识别结果需人工确认（Narrative_Only 口径）

## 与其他元素的关系

- 抽盘/倒轧结果支撑 F2 审定表期末数（存在性与完整性认定）
- 监盘发现的呆滞/毁损 → `valuation/` 的呆滞存货与跌价测试
- 附件（客户盘点表）走共享附件通道，可 OCR
