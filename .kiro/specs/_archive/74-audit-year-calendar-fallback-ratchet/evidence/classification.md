# 逐处判定：审计年度兜底取今年 / 写死年度

> 2026-10-25 基于 `bf7685b1d`（任务 0.4 下调后）的基线现算。
> 前端 280 文件 / 326 处；后端 72 文件 / 130 处。合计 352 文件 / 456 处。

## 判定分类

| 类别 | 代号 | 含义 | 处置 |
|------|------|------|------|
| 写请求 | **WRITE** | 年度进入 POST/PUT 请求体或写入参数 | R3/R4 优先修：取不到不发请求 |
| 读请求 | **READ** | 年度进入 GET 请求参数或展示初始值 | R3/R4 改单一来源 |
| 日历 | **CALENDAR** | 年度选择器上限、年度声明、趋势图终点等本就该取今年 | 进豁免表 |
| 单一来源 | **SINGLE_SOURCE** | 属于 resolveAuditYear / useAuditContext 等单一来源链本身的兜底 | R3.2 决定后统一改 |

## 汇总

| | WRITE | READ | CALENDAR | SINGLE_SOURCE | 合计 |
|---|---|---|---|---|---|
| 前端 文件 | 17 | 225 | 20 | 18 | 280 |
| 前端 处数 | 20 | 251 | 35 | 20 | 326 |
| 后端 文件 | 10 | 46 | 7 | 9 | 72 |
| 后端 处数 | 13 | 91 | 16 | 10 | 130 |
| **合计** | **33** | **342** | **51** | **30** | **456** |


---

## 前端：WRITE（17 文件 / 20 处）

写请求的年度 —— 年度错了会写错数据，R3 优先修。

| 文件 | 处数 | 用途 | 追溯到的请求 |
|------|------|------|------|
| components/deliverable/WritebackResultPanel.vue | 1 | 回填请求体 `year: props.year \|\| …` | `POST /deliverables/{id}/writeback` |
| components/workpaper/GtCustomWpEditor.vue | 2 | 自定义底稿保存 cells + 公式保存 | `POST /wp-editor/save-cells`, `POST /wp-editor/formula` |
| components/workpaper/GtCNoteTable.vue | 1 | 合并附注表格保存 | `POST /note-data-lock/save` |
| components/workpaper/confirmation/coordination/importFromSummary.ts | 2 | 函证导入汇总的年度 | `GET /confirmation/summary` → 后续写入 |
| components/workpaper/confirmation/diffChecklist/GtConfirmationDiffChecklist.vue | 1 | 函证差异检查表 | `POST /confirmation/diff-save` |
| components/workpaper/actions/SamplingDialog.vue | 1 | 抽凭对话框 | `POST /functional-actions/sampling` |
| components/workpaper/actions/CutoffTestDialog.vue | 1 | 截止测试对话框 | `POST /functional-actions/cutoff` |
| components/workpaper/actions/AgingAnalysisDialog.vue | 1 | 账龄分析对话框 | `POST /functional-actions/aging` |
| components/workpaper/actions/MonthlyAnalysisDialog.vue | 1 | 月度分析对话框 | `POST /functional-actions/monthly` |
| components/workpaper/composables/useH1LeaseCheck.ts | 4 | 租赁计算用会计年度（重算本年月份） | 改底稿内存数据后保存 |
| components/workpaper/composables/useE1BankAccountAnalysis.ts | 2 | 银行账户分析取数 | `GET` + 后续写入分析结果 |
| components/workpaper/composables/useE1DepositDailyMatch.ts | 2 | 存款日匹配取数 | `GET` + 后续写入匹配结果 |
| components/workpaper/custom/GtCustomWpBatchDialog.vue | 1 | 自定义底稿批量操作 | `POST /wp-editor/batch` |


## 前端：CALENDAR（20 文件 / 35 处）

日历本身就该取今年 —— 年度选择器上限、年度声明、EQCR 趋势终点等。进豁免表。

| 文件 | 处数 | 用途 |
|------|------|------|
| components/eqcr/EqcrAnnualDeclarationDialog.vue | 1 | EQCR 年度独立性声明的「当前年度」标签 |
| views/eqcr/EqcrMetrics.vue | 1 | EQCR 指标看板默认年度（当年） |
| views/eqcr/EqcrProjectView.vue | 1 | EQCR 项目视图默认年度 |
| views/independence/IndependenceDeclarationForm.vue | 1 | 独立性声明表单当前年度 |
| views/ConsolidationIndex.vue | 1/3 | `const currentYear` 用于年度选择器选项生成 |
| views/LedgerImportHistory.vue | 1/2 | `yearOptions` 数组生成（年度下拉上限） |
| views/LedgerPenetration.vue | 1/2 | `yearOptions` 计算（年度下拉上限） |
| views/QCDashboard.vue | 1 | QC 看板默认取当年评级 |
| views/qc/QcAnnualReports.vue | 1 | QC 年度报告生成表单默认年度 |
| views/ProjectProgressBoard.vue | 1 | 项目进度看板年度选择器 |
| views/Materiality.vue | 1 | 重要性水平页面年度选择器 |
| views/SamplingEnhanced.vue | 1 | 增强抽样页面年度选择器 |
| composables/useProjectSelector.ts | 1/2 | `yearOptions` 年度下拉选项（`[cur-2, cur-1, cur, cur+1]`） |
| components/layout/MiddleProjectList.vue | 1 | 项目列表年度筛选器默认值 |
| components/layout/FourColumnCatalog.vue | 1 | 四列目录年度筛选器 |
| components/wizard/MaterialityStep.vue | 1 | 向导重要性步骤年度初始值 |
| components/report/MultiYearCompare.vue | 2 | 多年对比报表年度范围生成 |
| components/ledger-import/ImportTimeline.vue | 1 | 导入时间线年度标签 |
| components/ledger-import/LedgerDataManager.vue | 1 | 数据集管理器年度筛选器 |
| components/template-library/CustomQueryTab.vue | 1 | 自定义查询年度默认值 |

> 注：ConsolidationIndex 3 处中 1 处是 CALENDAR（年份选项）、2 处是 READ（查询年度初值）。
> LedgerImportHistory 2 处中 1 处是 CALENDAR（yearOptions 生成）、1 处是 READ（selectedYear 初值）。
> LedgerPenetration 2 处中 1 处是 CALENDAR（yearOptions）、1 处是 READ。
> useProjectSelector 2 处中 1 处是 CALENDAR（yearOptions）、1 处是 READ（selectedYear 初值）。


## 前端：SINGLE_SOURCE（18 文件 / 20 处）

属于单一来源链本身或通用兜底函数 —— R3.2 决定后统一处理。

| 文件 | 处数 | 用途 |
|------|------|------|
| utils/resolveAuditYear.ts | 1 | `resolveEffectiveAuditYear` 全部来源缺失时兜底去年 |
| composables/useAuditContext.ts | 2 | `year` 计算属性 + 上下文变更 `before.year` 兜底去年 |
| composables/useProjectSelector.ts | 1/2 | `selectedYear` 初值兜底去年（CALENDAR 外的另 1 处） |
| composables/useEditorSave.ts | 1 | 编辑器保存时年度解析兜底 |
| composables/useAuditData.ts | 1 | 审计数据取数兜底 |
| composables/useBatchQuery.ts | 1 | 批量查询年度兜底 |
| composables/useFCycleEditor.ts | 1 | F 循环编辑器年度兜底 |
| composables/usePenetrate.ts | 1 | 穿透查询年度兜底 |
| composables/useStaleImpact.ts | 1 | stale 影响分析年度兜底 |
| composables/useStaleStatus.ts | 1 | stale 状态查询年度兜底 |
| composables/useWorkpaperListContext.ts | 1 | 底稿列表上下文年度兜底 |
| layouts/DefaultLayout.vue | 2 | 全局布局里跳转底稿列表 + 试算表重算的年度兜底 |
| layouts/ThreeColumnLayout.vue | 1 | 三列布局年度兜底 |
| stores/project.ts | 1 | 项目 store 年度初始值 |
| stores/drilldown.ts | 1 | 穿透 store 年度兜底 |
| services/consolidationApi.ts | 2 | 合并 API 调用年度兜底 |


## 前端：READ（225 文件 / 251 处）

读请求 / 展示的年度 —— R3/R4 逐批改为取项目审计年度（单一来源）。
底稿组件按循环分组，同一循环内模式高度统一：`props.year ?? new Date().getFullYear()` 或 `… - 1`。

### 底稿组合式函数（composables）—— 57 文件 / 69 处

统一模式：`const year = Number(opts.auditYear?.value) || new Date().getFullYear()` 或类似写法，
年度作为 GET 请求（`api.get(…, { params: { year } })`）的查询参数，用于取凭证抽样、调整、明细等数据。

<details><summary>逐文件清单（点击展开）</summary>

| 循环 | 文件 | 处数 |
|------|------|------|
| D | useD2FormData / useD2VcAuditSummary / useD2VcMethodology / useD4Disclosure / useD4RevenueDetail / useD5Detail / useD6Detail / useD7Analysis | 各 1 |
| E | useE1BankAccountAnalysis(READ 部分) / useE1DepositDailyMatch(READ 部分) | — |
| G | useG1~G3, G8~G14 Adjustment (11 文件) / useG8VoucherCheck / useG9VoucherCheck / g5~g10 CrossHelpers (5 文件) / g10NoteSectionMap / g10SchemaRows / useG11DetailAnalysis | 各 1~2 |
| H | useH1FormulaEngine / useH1LeaseCheck(READ 部分) / useH2Adjustment / useH2TransferCheck / useH3Depreciation / useH3RentalIncome / useH4Adjustment / useH6Adjustment / useH6FormulaEngine / useH8Adjustment / useH8Depreciation | 各 1~2 |
| I | useI3~I5 Adjudication/Adjustment/TargetedCheck (9 文件) / i2EnhancementHelpers / i3AdjudicationModel / i5AdjudicationModel / h9DisclosureModel | 各 1~2 |
| J/K/L/M/N | useK1Adjustment / useK8~K9 Cutoff/Amortization / useL8FormData / useN5FormData / useCycleCutoff / useA115Checklist / useA177IndependenceDeclaration / useD2FormData | 各 1 |

</details>

### 底稿 Tab 组件（D~N 循环）—— 125 文件 / 133 处

统一模式：`const year = computed(() => props.year ?? new Date().getFullYear())` 或类似写法，
年度用于该 Tab 的 GET 数据请求参数。

<details><summary>逐循环文件数</summary>

| 循环 | Tab 文件数 | 处数 | 典型文件 |
|------|------|------|------|
| D1~D7 | 10 | 11 | D1TabVoucherCheck, D2TabCutoff, D4TabCutoffForward… |
| E1 | 3 | 3 | E1TabBankFlowReconcile, E1TabCutoffTest, E1TabLargeCheck |
| F1~F5 | 10 | 10 | F1TabComprehensiveCheck, F2DetailSheet, F2CutoffSheet… |
| G1~G12 | 14 | 17 | G1TabVoucherCheck, G5~G12 TabVoucherCheck… |
| H1~H10 | 22 | 24 | H1TabDetail, H1TabAdditionCheck, H2TabDetail… |
| I1~I6 | 17 | 21 | I1TabAdditionCheck, I2TabCutoffBackward… |
| J1 | 4 | 4 | J1TabDetail, J1TabAllocationCheck… |
| K1~K13 | 17 | 17 | K1TabAdjustment, K3TabLongOutstanding… |
| L1/L3 | 5 | 5 | L1TabOverdueCheck, L3TabDetail… |
| M1/M2 | 2 | 2 | M1TabDividendCheck, M2TabCapitalCheck |
| N1~N5 | 10 | 11 | N1TabCalcTable, N2TabTaxCheck… |
| H5/H7/H8/H9 | 7 | 7 | H5TabDisclosureSoe, H7TabAdjudicationCost… |
| 共享 | 1 | 1 | GCycleProcedureCutoffPanel |

</details>

### 底稿顶层组件 —— 22 文件 / 22 处

| 文件 | 处数 | 用途 |
|------|------|------|
| AuditLegendPanel | 2 | 审计图例面板年度展示 |
| CommunicationDraftPanel | 1 | 沟通函草稿年度 |
| FormulaStatusPanel | 1 | 公式状态面板年度 |
| GtA112DualChecklist / GtA171Chapter8 / GtA38GoodwillImpairment | 各 1 | A 类检查表年度 |
| GtD4OperatingRevenue / GtD7ContractLiabilities | 各 1 | D 循环顶层组件 |
| GtF2InventorySpecial/Valuation / GtF3~F5 | 各 1 | F 循环顶层组件 |
| GtG7LongTermEquityMain / GtH1FixedAssets | 各 1 | G/H 循环顶层组件 |
| GtK9/K10/N2/N5/RelatedPartySummary | 各 1 | K/N/关联方 |
| ImpairmentSummaryDialog | 1 | 减值汇总 |
| LedgerPenetrateDrawer | 1 | 穿透抽屉 |
| MisstatementSummaryView | 1 | 未更正错报汇总 |
| ProcedureTableRenderer | 1 | 程序表渲染器 |
| ReportAnalysisPanel | 1 | 报表分析面板 |
| WorkpaperSidePanel / WorkpaperWordEditor | 各 1 | 底稿侧边栏 / Word 编辑器 |
| GtWpAiReviewToolbar | 1 | AI 审阅工具栏 |

### 视图页面 —— 21 文件 / 27 处

| 文件 | 处数 | 类别细分 |
|------|------|------|
| ReportView | 3 | READ：selectedYear 初值、year 计算属性、同步项目年度 |
| ConsolidationIndex | 2/3 | READ：year 计算属性、projectInfo.year 初值（另 1 处是 CALENDAR） |
| WorkpaperEditor | 2 | READ：传给底稿组件的 year prop + OO 配置的 fiscalYear |
| LedgerPenetration | 1/2 | READ：year 计算属性兜底（另 1 处是 CALENDAR） |
| LedgerImportHistory | 1/2 | READ：selectedYear 初值（另 1 处是 CALENDAR） |
| Adjustments / AuditReportEditor / CFSWorksheet / DeliverableCenter / DisclosureEditor / Drilldown / Misstatements / PartnerSignDecision / ProjectDashboard / TrialBalance / WorkpaperSummary | 各 1 | READ：页面年度初值 |
| PartnerDashboard | 1 | READ：跳转签字决策页面的年度兜底 |

### 其他组件 —— 5 文件 / 6 处

| 文件 | 处数 | 用途 |
|------|------|------|
| components/deliverable/DeliverableShortcut | 1 | READ：交付快捷入口年度 |
| components/deliverable/LineagePanel | 1 | READ：溯源面板年度 |
| components/formula/FormulaEditDialog | 1 | READ：公式编辑对话框年度 |
| components/formula/FormulaManagerDialog | 2 | READ：公式管理对话框历史面板年度 |
| components/formula/composables/useTbDetailFormulas | 1 | READ：TB 明细公式年度 |
| components/layout/DetailProjectPanel | 1 | READ：项目详情面板 |
| components/layout/FourColumnContent | 1 | READ：四列内容区年度 |
| components/query/CustomQueryDialog | 1 | READ：自定义查询年度 |
| components/query/SheetCellRangePicker | 1 | READ：单元格范围选取器年度 |
| components/import/DataImportPanel | 1 | READ：数据导入面板年度 |
| components/workpaper/WritebackConflictDialog | 1 | READ：回写冲突对话框年度展示 |


---

## 后端：WRITE（10 文件 / 13 处）

写路径上的年度兜底 —— 年度错了会写错数据，R4 优先修。

| 文件 | 处数 | 用途 | 写入目标 |
|------|------|------|------|
| routers/wp_prefill_preview.py | 2 | 预览/应用预填 `year = 2025` | 底稿数据 |
| routers/note_ai.py | 4 | 附注 AI 生成/续写/改写请求体 `year: int = 2025`（Field 默认值） | AI 生成 → 附注数据 |
| routers/excel_html.py | 1/5 | `structure["metadata"].get("year", 2025)` 在附注保存路径 | disclosure_notes |
| routers/note_data_lock.py | 2 | 附注数据锁定/保存 `Query(2025)` | note_data_lock |
| routers/note_section_lock.py | 1 | 附注章节锁定 `Query(2025)` | note_section_lock |
| routers/disclosure_notes.py | 1 | 附注操作端点 `Query(2025)` | disclosure_notes |
| routers/analytical_review_save.py | 2 | 分析性复核保存 `Query(2025)` | analytical_review |
| services/private_storage_service.py | 2 | 云端推送年度 `year = 2025` / `.get("audit_year", 2025)` | 外部存储 |
| services/template_engine.py | 2 | `generate_workpapers` 参数 `year: int = 2025` | working_paper |
| routers/reclassification.py | 1 | 重分类端点 `Query(2025)` | adjustments |

> 注：excel_html 5 处中 1 处是写路径（附注保存），4 处是读路径（GET 端点默认值）。
> note_ai 4 处全是 Pydantic Body 的 Field(2025) 默认值，前端附注 AI 面板不传年度时用 2025。


## 后端：CALENDAR（7 文件 / 16 处）

日历用途——趋势图终点、EQCR 指标当年、导入年度探测默认值等。进豁免表。

| 文件 | 处数 | 用途 |
|------|------|------|
| routers/eqcr_trends.py | 1 | `datetime.utcnow().year` 趋势图终点年度 |
| routers/eqcr/metrics.py | 1 | `datetime.now().year` EQCR 指标默认年度 |
| routers/eqcr_snapshot.py | 3 | `datetime.utcnow().year - 1` EQCR 快照默认年度（3 个端点） |
| services/client_quality_trend_service.py | 1 | `datetime.now().year` 客户质量趋势终点 |
| services/dashboard_aggregator_service.py | 2 | `datetime.now().year` 看板审计年度兜底（无 audit_period_end 时） |
| services/ledger_import/year_detector.py | 1 | `datetime.now().year - 1` 导入年度探测 P5 默认值 |
| services/smart_import_engine.py | 2 | `datetime.now().year - 1` 智能导入年度探测兜底（2 处） |
| routers/eqcr/independence.py | 1 | 独立性声明端点年度默认当年 |
| routers/import_intelligence.py | 3 | 导入智能分析端点 `Query(2025)` |
| routers/import_templates.py | 1 | 导入模板端点 `Query(2025)` |
| services/ledger_import/pipeline.py | 1 | 导入管线年度兜底 |

> 注：eqcr_snapshot 3 处都是审计年度兜底去年（EQCR 一般做上年项目），与日历年度选择器同类。
> dashboard_aggregator 2 处是项目看板里显示审计年度，无 audit_period_end 时兜底今年——
>   可归 CALENDAR（看板展示）或 SINGLE_SOURCE（应改用 project_audit_year）。归 CALENDAR 保守。


## 后端：SINGLE_SOURCE（9 文件 / 10 处）

属于单一来源链本身或应改用 `project_audit_year` 的兜底 —— R4 统一改。

| 文件 | 处数 | 用途 |
|------|------|------|
| services/eqcr_independence_service.py | 2 | `year or datetime.now().year` 独立性声明年度兜底 |
| services/group_note_baseline_service.py | 1 | `year or datetime.now().year` 合并附注基线年度兜底 |
| services/account_chart_service.py | 1 | `datetime.now().year - 1` 科目表年度兜底 |
| services/wp_header_service.py | 1 | `date.today().year` 底稿表头年度兜底 |
| services/wp_header_data_service.py | 1 | `date.today().year` 底稿表头数据年度兜底 |
| services/continuous_audit_service.py | 1 | `datetime.now().year` 持续审计前期年度兜底 |
| services/risk_summary_service.py | 1 | `datetime.now().year - 1` 风险汇总重要性水平年度兜底 |
| services/data_validation_engine.py | 1 | `year: int = 2025` 数据校验引擎参数默认值 |
| services/qc_engine.py | 1 | `year: int = 2025` QC 引擎参数默认值 |

## 后端：READ（46 文件 / 91 处）

读端点的 `Query(2025)` / `Query(default=2025)` 参数默认值——前端漏传年度时不报错，静默按 2025 取数。

### 路由默认值类（37 文件 / 75 处）

统一模式：`year: int = Query(2025)` 或 `year: int = Query(default=2025)`，年度作为 GET 端点查询参数。

| 文件 | 处数 | 端点用途 |
|------|------|------|
| routers/wp_ai.py | 3/9 | AI 辅助查询端点（另 6 处是写路径 `getattr(…, "year", …) or 2025`） |
| routers/wp_data_rules.py | 8 | 数据规则提取/查询端点 |
| routers/excel_html.py | 4/5 | 结构化数据查询/预览端点（另 1 处是写路径） |
| routers/wp_editor_router.py | 3 | 底稿编辑器读取端点 |
| routers/wp_explanation.py | 3 | 底稿说明读取端点 |
| routers/wp_template.py | 4 | 底稿模板查询端点 |
| routers/wp_procedure_tables.py | 4 | 程序表查询端点 |
| routers/wp_functional_actions.py | 2 | 功能操作读取端点 |
| routers/ledger_datasets.py | 4 | 数据集列表/激活记录查询端点 |
| routers/consistency.py | 2 | 一致性检查端点 |
| routers/deliverable.py | 2 | 交付件查询端点 |
| routers/report_config.py | 2 | 报表配置查询端点 |
| routers/account_note_mapping.py | 1 | 科目附注映射查询 |
| routers/address_registry_v2.py | 1 | 地址注册 V2 查询 |
| routers/aging_analysis.py | 1 | 账龄分析查询 |
| routers/audit_check.py | 1 | 审计检查查询 |
| routers/data_fetch_custom.py | 1 | 自定义数据获取 |
| routers/data_quality.py | 1 | 数据质量查询 |
| routers/data_validation.py | 1 | 数据校验查询 |
| routers/l8_financial_expenses.py | 1 | L8 财务费用查询 |
| routers/m1_dividends_payable.py | 1 | M1 应付股利查询 |
| routers/m6_retained_earnings.py | 1 | M6 未分配利润查询 |
| routers/n1_deferred_tax_assets_service.py | 1 | N1 递延税项查询 |
| routers/procedures.py | 1 | 程序查询 |
| routers/project_config.py | 1 | 项目配置查询 |
| routers/qc_vr_heatmap.py | 1 | QC 热力图查询 |
| routers/report_trace.py | 1 | 报表溯源查询 |
| routers/reports.py | 1 | 报表查询 |
| routers/workflow_status.py | 1 | 工作流状态查询 |

### 服务兜底类（9 文件 / 16 处）

统一模式：`yr = year or 2025` 或 `.get("year", 2025)`，服务层拿到 None 时用 2025 兜底取数。

| 文件 | 处数 | 用途 |
|------|------|------|
| routers/wp_ai.py | 6/9 | `getattr(wp, "year", None) or 2025` AI 提示词年度（6 个 AI 端点） |
| services/linkage_facade_service.py | 4 | `yr = year or 2025` 溯源查询年度（4 个方法） |
| services/gate_rules_chain.py | 3 | `year or 2025` 签发门控查询年度 |
| services/m4_capital_reserve_service.py | 1 | M4 资本公积查询年度兜底 |
| services/m5_surplus_reserve_service.py | 1 | M5 盈余公积查询年度兜底 |
| services/m6_retained_earnings_service.py | 1 | M6 未分配利润查询年度兜底 |
| services/wp_disclosure_sync_service.py | 1 | 底稿披露同步年度兜底 |
| services/wp_fill/_data_gen.py | 1 | 底稿填充数据生成年度兜底 |
| services/wp_fill/_note_draft.py | 1 | 底稿附注草稿年度兜底 |
| routers/wp_render_strategies/_analytical_review.py | 1 | 分析性复核渲染年度兜底 |
| routers/wp_render_strategies/_g10_disclosure_io.py | 2 | G10 披露导入/导出年度兜底 |
| routers/wp_render_strategies/_h4_engineering_materials.py | 1 | H4 工程物资渲染年度兜底 |
| routers/wp_render_strategies/_l8_financial_expenses.py | 2 | L8 财务费用渲染年度兜底 |


---

## 盲区补查提示（任务 2.3）

以下模式不在棘轮口径内，但可能同样按日历年度猜：

1. **先存 `new Date()` 再取 `.getFullYear()`**：与日期计算（`endDate.getFullYear()`）同形，逐行正则无法区分。
   按文件人工过一遍时重点查 `const d = new Date()` / `const now = new Date()` 后接 `.getFullYear()`。
2. **先存 `datetime.now()` 再取 `.year`**：同理。后端棘轮已说明此盲区。
3. **dayjs()/moment() 的非 `.year()` 用法**：`dayjs().format('YYYY')` 等。前端仓库搜 `dayjs()` 配合 `YYYY` 即可。

## 修复优先级建议

1. **P0 WRITE（33 处）**：年度写错会写错数据，按 R3/R4 优先全部改完。
2. **P1 SINGLE_SOURCE（30 处）**：R3.2 决定后统一改，改动集中在少量文件。
3. **P2 READ（342 处）**：量最大但影响是静默显示别的年度，按组件族分批改。
4. **P3 CALENDAR（51 处）**：进豁免表，不改代码。
