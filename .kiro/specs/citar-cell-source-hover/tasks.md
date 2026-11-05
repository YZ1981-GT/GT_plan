# 任务

## 批 1：通用卡片 + 税审底稿 / 汇算申报表
- [x] 1. 后端统一结构 `cell_source/schema.py` + 路由 `routers/cell_sources.py`（`tax-sheet/{code}`，readonly）+ `router_registry/system.py` 注册
- [x] 2. 后端 `cell_source/tax_sheet.py`：`Evaluation.book`、`AccountBook.fallback_top`、取数格逐节点金额、公式格引用展开与线性系数、手工值 / 参数、调整未计入（design §4，偏离见执行记录）
- [x] 3. 后端测试 `test_cell_source_tax_sheet.py`：Σ 节点金额 = 格值（5 种 op）、回退、取不到、线性 / 非线性公式、跨表链接、手工值、调整未计入、鉴权三态
- [x] 4. 前端 `CitarSourceCard.vue` + `useCellSourceHover.ts` + `apiPaths.cellSources` + `sourceLink` 扩展（`SourcePage`、workpaper / tax_return 的 pendingCellLocate）（design §9）
- [x] 5. 前端接线：`TaxWorkpaperGrid` 加 `data-src` / `tw-cell--located`、去原生 title 并入卡片；`TaxWorkpaperSheetPanel` / `TaxReturnSheetPanel` 接卡片与格级定位、保存后 `invalidate`
- [x] 6. 前端测试（卡片渲染、悬停时序、缓存作废、sourceLink、格级定位只消费一次）+ ESLint + 单区域 vue-tsc
- [x] 6b. 批 1 浏览器实测（ABC餐饮：2-01 D8 / L8、A100000 D3 跳到 A101010 C3；辽宁：取数格「未计入本格」）

## 批 2：试算平衡表
- [x] 7. 后端：`standard_balance_view_service` 抽 `leaf_balance_rows` / `approved_adjustment_lines`（原两函数改为对其求和）+ `cell_source/trial_balance.py` + 端点 `trial-balance`（design §5）
- [x] 8. 后端测试：各列构成之和 = `standard-view` 同列（含底稿发布调整）、审定数不等 diff、未批准不计入、受限成员过滤、`standard-view` 回归不变
- [x] 9. 前端：`CitarTrialBalance` 两个页签接卡片、去 title、页脚文字改（R4.6）；`CitarAdjustment` 读 `?locate=` 定位分录组；测试

## 批 3：审定报表 / 报表分析 / 单体财务报表
- [x] 10. 后端：`ReportFormulaParser` recorder + `_row_amount` 抽取、`PriorPeriodResolver.last_source`、`cell_source/report.py`（AST 逐项、内存重算、过期判定）+ 端点 `report/{type}`（design §6）
- [x] 11. 后端：`financial_statements.compute_columns` / `fs_rows.account_terms` 抽取 + `cell_source/fs.py` + 端点 `financial-statements`（design §7）
- [x] 12. 后端测试：线性逐项之和 = 重算值、SUM_ROW、PL_UNCLOSED、上期四来源、过期、手工值、非线性；`recorder=None` 生成逐行不变；`build` 输出逐字节不变
  - 如实说明：上期来源只测了「本年试算表期初」一路；「本项目上年 / 上年项目报表 / 上年项目试算表」三路代码已写但未测（夹具与三个真实项目都没有上年数据），`_prior_kind` 读 `PriorPeriodResolver` 私有字段，它改判定顺序时会跟着错
- [x] 13. 前端：`CitarAmountCell` / `CitarReportTable` / `CitarStatementView` / `CitarFinancialStatements` 接卡片、去 title；`CitarAuditedReports` 读 `?tab=` + `?locate=`；测试

## 批 4：账务查询
- [x] 14. 后端 `cell_source/ledger.py` + 端点 `ledger/balance`、`ledger/journal-row/{row_id}`（design §8）+ 测试（有 / 无映射记录、舍弃映射、辅助汇总、人工修改）
- [x] 15. 前端：`CitarBalanceTab`（列级 + 行级 + 合成上级行本地算）、`CitarJournalTab`（列级 + 按行单取）接卡片；测试

## 批 5：补鉴权与收尾
- [x] 16. 补项目鉴权（design §10）：先写复现测试（generate 的非成员 / 审计员），再改 7 处；基线常量按现算值下调；端点三态测试
- [x] 17. 真库只读核对（ABC餐饮、北京激光、辽宁、宜宾抽格：构成之和 = 格值；宜宾舍弃映射；辽宁调整未计入）
  - 如实说明：宜宾两个项目与四川医药已删除，「宜宾舍弃映射」没有真实数据可核，由单测覆盖；其余三个项目在批 1~4 各自核过（构成之和与格值差 0）
- [x] 18. 浏览器实测（R8）+ 后端相关回归 + 前端 `src/citar`、`views/tax-workpapers`、`views/tax-return` 全部单测 + 行数门 + memory / INDEX 登记

## 批 6：账务查询来源项点开导入记录（R9，design §13）
- [x] 19. 后端：`ledger_import/job_mapping_view.py`（`locate_key`、详情组装）+ 端点 `jobs/{job_id}/mappings` + `cell_source/ledger.py` 映射项带链接；测试（链接键与详情行键一致、他项目 404、无映射记录、鉴权）
- [x] 20. 前端：`cellSourceLink` 的 `ledger_import` 分支、`CitarImportJobDetail.vue`、`CitarDataImport` 按 `?job=` 显示详情；测试
- [x] 21. 前端：科目余额表 / 序时账卡片接 `@open`（编辑中先提示）→ `CitarLedgerQuery` 跳转；测试
- [x] 22. 真库只读核对 + 浏览器实测（ABC：余额表「本期借方」点开 → 详情高亮该列；序时账同）+ 回归 + 行数门 + memory / INDEX

## 执行记录
### 2026-11-05 批 1 后端（任务 1~3）
- 与 design 的偏离：回退科目不改 `RuleResult`，改为 `AccountBook.fallback_top(path)`（只读判定，取数代码不动）；
  样表预置值、空的填写格不由后端返回（前端按 sheet 定义的 `role` 自己写）；只含文字 / 错误值结果的线性公式不做合计核对。
- 真库只读核对（ABC餐饮 / 北京激光 / 辽宁 2025，全部 141 张税审底稿与申报表）：每项目约 1 万个公式格、2,166 个取数格、
  约 9,500 个线性格，`diff` 全部为空；抽样：2-01 D8（序时账 1 月贷方，一个科目）、L8（「其他」余项 4 个科目合计 3,790,785.70）、
  A100000 D3（12 项跨表引用）、1-12 F4（引用 1-14 G14）。首轮发现申报表行名取成行次「1」，已改为跳过纯数字文字。
- 测试：`test_cell_source_tax_sheet.py` 18 passed；连同 `test_tax_workpaper_api.py`、`test_tax_workpaper_rule_runner.py` 共 54 passed。
- 未做：变异验证（批 5 统一做）；`apiPaths.cellSources` 随任务 4 加。

### 2026-11-05 批 1 前端（任务 4~6b）
- 新文件：`citar/cellSource.ts`（类型、标签、链接换算、格子定位 sessionStorage）、`citar/useCellSourceHover.ts`（事件委托单卡片、400 / 200 ms、单飞缓存、Esc / 滚动关闭）、
  `citar/components/CitarSourceCard.vue`、`views/tax-workpapers/taxCellHint.ts`（原 Grid 原生 title 文字）、`views/tax-workpapers/useTaxSheetSources.ts`（两个单表面板共用）。
- 改：`TaxWorkpaperGrid`（`data-src` / `tw-cell--located`，去原生 title）、税审底稿与汇算申报表的 View + SheetPanel（卡片、`locate` prop、同页定位事件 / 跨页 pendingCellLocate）、`apiPaths.cellSources`。
- 实测中修的缺陷：①申报表格子行名取成合并的类别列（「利润总额计算」）→ 前后端都改为取左侧最近的文字；
  ②监听在模板 ref 赋值后下一个微任务才挂，期间悬停丢失 → `flush: 'sync'`；③来源未到时填写格先显示「尚未填写」→ 只有样表预置值本地给，其余显示「正在读取」。
- 测试：前端 `src/citar` + `views/tax-workpapers` + `views/tax-return` 9 个文件 46 passed；单区域 vue-tsc（`tsconfig._cell-source.json`，注入 TS2322 变异确认会报）与 ESLint 0 报错。
- 浏览器实测（ABC餐饮_2025，独立无头脚本，只读）8 项全过：2-01 D8 卡片（序时账 1 月贷方、510103）、移开关闭、L8 四科目合计 ＝ 格值、Esc 关闭、
  点 510103 跳科目余额表该行高亮、A100000 D3 十二项引用 ＝ 格值且行名「一、营业收入」、点 A101010 C3 切表并高亮该格；控制台无错误。
- 🔴 实测须知：改后端 .py 会触发开发服重载（约 1 分钟），期间页面取值慢，卡片会先按本地信息显示，取值到达后被作废关闭 —— 实测前先确认接口已恢复。

### 2026-11-05 批 2 试算平衡表（任务 7~9）
- 后端：`standard_balance_view_service` 抽 `_leaf_select`（`_period_by_standard` 与新 `leaf_balance_rows` 共用同一条末级行 SQL）、
  `approved_adjustment_lines` + `_approved_adjustment_conditions`（`_adjustments_by_standard` 同条件）；`cell_source/trial_balance.py` 九列来源；
  端点 `GET /cell-sources/trial-balance`（readonly，受限成员按有效循环过滤）。审定数构成取 trial_balance（未审数 + AJE + RJE + 底稿发布调整），
  与现算调整后期末不等（损益类除外）时写「试算表需重算」。
- 顺带：税审来源的公式里系数为 0 的引用（2-05 G18 `=SUM(G8:G17)-G9` 的 G9）不再列为构成项，改写「加减相抵，不计入」。
- 真库只读核对：ABC餐饮 / 北京激光 / 辽宁 各 174 个标准科目 × 9 列 = 1,566 格，差额 0、需重算 0；辽宁 AJE-001 出现在 1001 借方调整。
  辽宁那笔分录是库存现金内部互转（1001 / 100101），税审底稿没有读现金的取数格 ⇒ 真库上「未计入本格」无实例，由单测覆盖。
- 测试：后端 `test_cell_source_trial_balance.py` 8 例 + 税审 19 例 + `test_standard_balance_view.py` / `test_tb_mapping_code_hierarchy.py` 回归，共 38 passed；
  前端 10 个文件 48 passed，单区域 vue-tsc / ESLint 0 报错。
- 浏览器实测 5 项全过：辽宁 1001 借方调整（AJE-001）、调整后期末构成、点 AJE-001 跳调整分录页该组高亮；ABC 6001 本期贷方四个客户科目合计 ＝ 格值、
  底稿取数余额表审定数构成。实测后补：卡片金额借正贷负与表格「方向 + 金额」不一致时加一句说明。

### 2026-11-05 批 3 报表（任务 10~13）
- 与 design 的偏离：不给 `ReportFormulaParser` 加 recorder 参数，改为来源模块里的子类 `RecordingParser`（`report_engine.py` 只抽了 `_row_amount` / `_sum_rows` / `_sum_tb_rows`，
  行数 2681 → 2662）；`PriorPeriodResolver` 不加 `last_source`，来源模块按它已缓存的判定结果复现同一顺序（`_prior_kind`，读私有字段，已注释）；
  `financial_statements` 不抽 `compute_columns`，来源模块直接用 `build` 的结果作格值、按行配置展开构成（`fs_rows.account_terms` 是 `account_total` 的唯一口径）。
- 报表来源：内存按生成同一顺序重算资产负债表 + 利润表（共用 ROW 缓存、读手工值），不写库；TB 拆到各标准科目（金额为 0 的下级汇成一行）、
  ROW / SUM_ROW 拆到行（链接审定报表该行）、PL_UNCLOSED 一项；非线性公式只列引用；上期来源四种 + 无来源；库里值与重算不符写「报表已过期」。
- 单体财务报表：企业会计制度格式取数行 / 合计行 / 现金流量表行 / 跨表行四类；企业会计准则格式转调报表来源。
- 真库只读核对：ABC餐饮 / 北京激光 / 辽宁 × 资产负债表 / 利润表 × 审定 / 未审，258 + 156 格每组差额 0、过期 0（利润表 78 格上期无来源，三个项目都没有上年数据）；
  回滚事务里把北京激光 BS-002 改成 12345，只有该格报「已过期」。单体财务报表三项目差额 0（ABC 企业会计制度，北京 / 辽宁企业会计准则）。
- 测试：后端 `test_cell_source_report.py` 14 + `test_cell_source_fs.py` 6，连同报表引擎既有 73 例（`test_report_engine` 等 6 个文件）与单体报表既有用例共 97 + 73 passed；
  前端 11 个文件 50 passed，单区域 vue-tsc / ESLint 0 报错。
- 浏览器实测 8 项全过：审定报表 BS-002 拆科目、IS-001 五行合计并点 IS-002 本页定位；报表分析对比的调整影响（审定 − 未审）与未审口径拆科目；
  单体财务报表货币资金取数、资产总计合计并点「流动资产合计」本页定位第 20 行；控制台无错误。

### 2026-11-05 批 4 账务查询（任务 14~15）
- 后端 `cell_source/ledger.py`：列级来源取自当前生效数据集 → 导入作业 `custom_mapping.confirmed_mappings`（文件 / sheet / 表头 / 用户确认或自动识别）+ 推导说明（年初优先、分列、本年累计、单金额列拆分）；
  行级：舍弃的多列映射值（`_discarded_mappings`）、辅助明细汇总、人工修改（导入原值、修改人、时间、原因），方向按类别推断只在列上写一次（真库北京 85 行 / 辽宁 747 行逐行重复，实测后改）。
  端点 `ledger/balance`（整表）、`ledger/journal`（列级）、`ledger/journal-row/{id}`（行级单取，序时账行数大）。
- 前端：`useCellSourceHover` 加 `extra`（按格单取，序时账一行一取并缓存）；`cellSource.mergeLedgerSources` 合成列 + 行；`CitarBalanceTab` 页面补出的上级行按下级末级合计本地算；
  `CitarJournalTab` 去掉摘要 / 科目名称的原生 title，全文写进卡片。
- 实测抓到的缺陷：①`journal_row_source` 没按当前生效数据集过滤 —— ABC 序时账有两个版本，带舍弃映射的 14,107 行全在已被替代的旧版本里，
  按 id 能读到旧行 ⇒ 改走 `get_active_filter`，加回归用例（旧版本行返回 None）。②用户验收点「宜宾看到两列科目名称冲突」无法做：宜宾两个项目与四川医药都已删除，
  现存三个项目的当前数据集都没有映射冲突；冲突显示由单测覆盖（`test_cell_source_ledger.py`）。
- 测试：后端 7 passed；前端 12 个文件 54 passed（新增 `cellSourceLedger.spec.ts` 4 例），单区域 vue-tsc / ESLint 0 报错。
- 浏览器实测 3 项全过（ABC）：科目余额表期末余额（「未审期末数」+「借贷方向」）、序时账日期（「记账时间」，当前版本无冲突）、摘要写全文；控制台无错误。

### 2026-11-05 批 5 补鉴权与收尾（任务 16~18）
- 鉴权（R7）：`get_report` / `drilldown` / `export-excel` / `related-workpapers` / 批量 `export-excel` 由仅登录改 `require_project_access("readonly")`；
  `POST /api/reports/generate` 保留 `require_operation("report:edit")`，函数体先按请求体 `project_id` 做 `assert_project_permission(..., "review")`（只管项目成员，谁能生成仍由权限矩阵定）；
  `opening-reconcile` 传了 `prior_project_id` 时对上年项目也校验只读。复现测试 `test_report_endpoint_project_authz.py`（非成员 403 / 成员 200 / 审计员生成按矩阵）8 passed。
  鉴权基线按现扫值下调：`_IDENTITY_ONLY_BASELINE` 183 → 179、`_PREFIXED_IDENTITY_ONLY_BASELINE` 270 → 259；`test_require_operation_integration` 的 admin 用例补 `set_rls_context` 替身（新加的项目校验会走到它）。
- 实测抓到并修的两个时序缺陷（与鉴权无关，旧代码就有）：
  ①报表分析「审定」未读完就点「对比」⇒ 页面停在「读取报表失败」：两次读取同 URL 同参数，GET 去重取消先发的那个，它的 catch 晚于新请求执行、把错误盖在已成功的对比表上
  ⇒ `CitarStatementView.load` 加读取序号，只有最新一次写回；同形的 `CitarTrendPanel` / `CitarIndicatorsPanel` 一并改。回归 `CitarStatementView.loadRace.spec.ts`，磁盘变异（去掉序号判断）打红在「读取报表失败」断言上，恢复后 sha256 一致。
  ②指针停在格子上时表格刷新（取值回来触发 `invalidate`）⇒ 卡片一直不出来，要挪一下鼠标：浏览器不会对静止的指针再发 mouseover
  ⇒ `useCellSourceHover` 记指针所在格，`invalidate` 后对它重新计时（格子重渲染则按键重新找）；Esc / 滚动主动关的、已离开格子的不再自动弹。`cellSourceHover.spec.ts` 加 1 例。
- 回归：后端鉴权组 7 文件 377 passed / 4 failed（`test_note_edit_gate_endpoints` 覆盖集合 4 例，`disclosure_notes.py` 的 formula-gray / refresh-from-disclosure 两个端点，HEAD 干净检出同红）；
  来源 + 报表 + 税审组 47 文件 831 passed / 2 failed（`test_report_equity_is_net_profit::test_apply_is_net_profit_writes_eq007`、`test_report_models::test_all_report_types`，HEAD 干净检出同红）。
  进程内变异：`fs.account_terms` 少列一项 ⇒ 对账测试报 diff −500 打红；`RecordingParser._record` 少记一行 ⇒ diff −450 打红。
- 前端：`src/citar` + `views/tax-workpapers` + `views/tax-return` 13 个文件 56 passed，单区域 vue-tsc / ESLint 0 报错。行数门对本 spec 52 个文件 exit 0。
  如实说明：收尾时并发会话正在改 `CitarJournalTab.vue`（序时账穿透改为凭证 / 科目两级视图），其 `journalDrilldown.spec.ts` 1 例红、
  `CitarJournalTab.vue` 9 条类型错误（`DrillFrame.view` 改型未改完）都出自那次改动，最后一轮检查把这两个文件排除在外；本 spec 在该文件里的接线（`data-src` + 卡片）16:46 那轮检查已过。
- 浏览器实测（全部 4 个脚本，ABC / 北京 / 辽宁）：税审底稿 / 汇算申报表 8/8、试算平衡表 5/5、报表 8/8、账务查询 3/3，控制台无错误。
- 范围外（未改）：`report_line_mapping` / `report_trace` / `audit_report` / `report_mapping` 等其余报表类端点仍只校验登录；上期来源只测了「本年试算表期初」一路；税审取数仍是导入数口径（改审定口径需另立 spec）；导入允许多列映射到同一字段（舍弃的值只在卡片里提示）。

### 2026-11-05 批 6 来源项点开导入记录（任务 19~22，R9）
- 现状：原文件导入完成后即清理（三个项目的上传产物都是 consumed、目录不存在），行号导入时也没存 ⇒ 跳不到原文件某行，改为跳到「这次导入的记录」并高亮那一列的映射。
- 后端：定位键单一来源 `ledger_import/sheet_mapping.mapping_locate_key`（去存储前缀文件名 | sheet | 列序号；新旧导入的文件名一种带 `NN_` 前缀、一种不带）；
  `cell_source/ledger._dataset` 多取 `job_id`，列来源每个映射项 `link("ledger_import", code=作业, ref=定位键)`，行级「未采用」项不给链接；
  `ledger_import/job_mapping_view.py` + `GET /ledger-import/jobs/{job_id}/mappings`（readonly，他项目作业 404）。
  字段中文名补齐 `ledger.FIELD_LABELS`（真库「科目类别」原显示成 `category`；守卫：识别别名表里每个字段都要有中文名），
  `direction` 在序时账写「借贷方向」；入库行数认 v2 的 `balance_rows` / `ledger_rows` 与旧的 `tb_*` 两种键（模型注释写的是旧键，真库是新键）。
- 前端：`cellSourceLink` 的 `ledger_import` 带作业 ⇒ `?job=&locate=`；`CitarImportJobDetail.vue`（作业状态 / 导入人 / 生成的数据集与行数 / 文件 → sheet → 列字母、原表头、映射为，
  高亮复用 `useCitarRowLocate`）；`CitarDataImport` 有 `?job=` 时显示详情、向导隐藏（「返回账务查询」有上一页就后退、否则进账务查询；「开始新的导入」回向导）；
  科目余额表 / 序时账卡片原来没接 `@open`（链接点了没反应），现接上：有行正在修改先提示，否则 emit `open-source` 给 `CitarLedgerQuery` 跳转。
- 测试：后端 `test_cell_source_ledger.py` 14 passed（新增 7 例：链接键与详情行键逐一对上、详情内容、上传目录在 / 已消费、无映射记录、端点 200 / 403 / 404、字段中文名全覆盖）；
  进程内变异（链接键不剥前缀）打红在链接断言上。前端 14 个文件 68 passed（新增 5 例：点链接 emit、编辑中挡下、链接换算、详情高亮、404 文案）；ESLint 0 错误。
- 真库只读核对：ABC / 辽宁 / 北京当前数据集的账务查询列来源 15 / 19 / 24 项，全部带链接、链接键在详情里都找得到（0 缺失）。
- 浏览器实测（ABC）7 项全过：余额表 1001「本期借方」映射项可点 → 详情高亮 V「未审借方发生额 → 借方发生额」、写明原文件已清理与入库行数、向导不显示；返回回到科目余额表；
  序时账摘要 → 高亮 H「业务说明 → 摘要」；开始新的导入回到向导。控制台无错误。
- 归因：单区域类型检查加入 `CitarDataImport.vue` 后带出 `components/ledger-import/LedgerImportDialog.vue(40)` 1 条 TS2322（`ConfirmedMapping` 两处定义不一致，该文件 2026-06-07 后未改，本次未动）；
  `test_lazy_import_resolvability` 2 例红（`ai_content.py` 引 `consol_lock_service`、`consol_note_template_push_service.py` 引 `disclosure_note_models`，都不存在），HEAD 干净检出同红。
  ESLint 1 条警告是 `CitarDataImport.vue` 原有的人工修改行数相加（行号随插入下移）。
