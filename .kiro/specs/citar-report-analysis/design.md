# 设计：CITAR「报表分析」菜单

## 1. 现状核对（2026-11-03 真库 + 源码）

| 旧标签页 | 前端 | 后端 | 实测问题 |
|---|---|---|---|
| 六张报表 | `ReportView` + `useReportData` | `GET /api/reports/{pid}/{year}/{type}`（`?unadjusted=true` 读时算） | 可用；减值表本期增减列前端写死 0 |
| 跨表核对 | `useReportCrossCheck` | `GET /api/projects/{pid}/formula/report-cross-check` | 取数键 `IS-017/018/019`、`BS-001` 在两版模板里是「▲赔付支出净额 / ▲提取保险责任准备金 / ▲保单红利支出」「流动资产：」；子串兜底「净利润」先命中「1.归属于母公司所有者的净利润」等；权益变动表从未传入 ⇒ #5 恒比 0 |
| 多年对比 | `MultiYearCompare` | `GET /api/projects/{pid}/reports/multi-year`（已挂 readonly） | 可用；真库每项目只有一年 |
| 试算全景 | `TrialBalanceFullView` | `/full-tb` + `/tb-balance-check` | 「其他调整」= 审定 − 各分量的倒挤数 ⇒ 平衡恒成立 |
| 期初核对 | `OpeningReconciliation` | `/opening-reconcile` | 前端从不传上年项目，上年审定恒 0，所有期初非 0 科目都被列成差异 |
| 财务比率 | `FinancialRatioPanel` | `/financial-ratios` | 行编码全错（`BS-019` 国企 = 其中：原材料、上市 = 非流动资产：；`PL-xxx` 不存在 ⇒ 收入恒 0）；mode 被忽略；年份不过滤已删除行 |
| （未接）变动分析 | — | `/bs-trend` `/pl-trend` | mode 被忽略；按 row_code 字典序；不过滤 is_deleted |

另：`wp_report_analysis.py` 6 个端点只挂 `get_current_user`（任意登录用户可读任意项目）。

模板关键行（`report_config`，两版单体）按**行名**定位稳定，编码不稳定：

| 语义 | 国企 soe | 上市 listed | 定位规则（去空白、去括号说明后） |
|---|---|---|---|
| 货币资金 | BS-002 | BS-002 | 名 == 货币资金 |
| 应收账款 | BS-008 | BS-006 | 名 == 应收账款 |
| 存货 | BS-018 | BS-012 | 名 == 存货 |
| 流动资产合计 | BS-027 | BS-018 | 名 == 流动资产合计 |
| 资产总计 | BS-053 | BS-042 | 名 == 资产总计 |
| 流动负债合计 | BS-082 | BS-059 | 名 == 流动负债合计 |
| 负债合计 | BS-100 | BS-073 | 名 == 负债合计 |
| 所有者权益合计 | BS-128 | BS-087 | 名 ∈ {所有者权益合计, 股东（或所有者）权益合计}（不认「归属于母公司…」） |
| 营业收入 | IS-002 | IS-001 | 去序号 / 「其中：」后 == 营业收入 |
| 营业成本 | IS-008 | IS-002 | 去「减：」「其中：」后 == 营业成本 |
| 利润总额 | IS-044 | IS-022 | 去序号后以「利润总额」开头 |
| 所得税费用 | IS-045 | IS-023 | 去「减：」后 == 所得税费用 |
| 净利润 | IS-046 | IS-024 | 去序号后以「净利润」开头（排除「其中」「1.」等子项：要求 indent_level == 0） |
| 权益变动表年末 | EQ-033 | EQ-029 | 去序号后 == 本年年末余额 |

## 2. 后端

### 2.1 行定位单一来源 `app/services/report_row_locator.py`（新）
- `normalize_row_name(name)`：去全 / 半角空白，去开头序号（`一、` `（一）` `1.`）与「减：」「加：」「其中：」，去括号说明（`(亏损以“-”号填列)` 等）
- `locate(rows, key) -> row | None`：`key` 取 §1 表里的语义键；规则写在一张表 `_RULES`（名集合 / 前缀、是否要求顶层），多个命中取 indent 最小、再取首个
- 财务比率、变动分析、跨表核对共用；不新增迁移

### 2.2 财务比率 `FinancialRatioService.calculate_ratios(pid, year, mode)`
- 行来源：`mode=audited` 读 `financial_report`（未删除）；`mode=unadjusted` 调 `ReportEngine.generate_unadjusted_report`（与未审报表同一路径）
- 比率与口径：流动比率、速动比率（流动资产 − 存货）/流动负债、资产负债率、毛利率、净利率、总资产周转率 / 应收账款周转率 / 存货周转率（分母用期初期末平均，期初缺失时用期末并在 note 写明）、ROE（权益同样取平均）
- 返回每项 `{name, value, unit, abnormal, note, numerator:{label,row_code,amount}, denominator:{…}}`；任一分量定位不到 ⇒ `value=None`，`note="取不到：xx"`
- 报表未生成（审定）⇒ 全部 `value=None`、note「审定报表未生成」

### 2.3 变动分析 `ReportTrendAnalysisService`
- 同 2.2 的行来源与 mode（`report_analysis_rows.load_report_rows`）；按 row_code 排序（编码三位补零，与报表页顺序一致 —— `financial_report` 无 row_number 列，§1「字典序」一条经核对不是缺陷），过滤已删除
- 输出加 `indent_level` `is_total_row`；`change_rate` 在上期为空 / 0 时为 `None`；`significant` = |rate| ≥ 10

### 2.4 期初核对 `reconcile_opening_balance(pid, year, prior_project_id=None)`
- 未显式给上年项目 ⇒ `find_prior_project(db, pid, year)`；找不到 ⇒ `{has_prior:false, reason, differences:[]}`，不再拿 0 比
- 上年审定取上年项目 `year-1` 试算表 `audited_amount`；只比两边都有的科目 + 一边有一边无的列出（标「本年无」/「上年无」）

### 2.5 试算全景平衡
- `check_balance_formula`：`balanced` 改判「所有科目 `other_adjustment` == 0」，返回 `unexplained`（other 非 0 的科目编码与金额）；总额校验保留但不再作为平衡依据

### 2.6 跨表核对取数 `logic_check.build_report_row_cache`
- 保持 `row_cache` 的引用键（`assets_total` / `IS-017` …）与 7 条表达式不变（公式管理里的规则、`cross_check_results.rule_id` 不变）
- 取值改为：先用 `report_row_locator` 按语义定位（资产总计→`assets_total`，利润总额→`IS-017`，所得税→`IS-018`，净利润→`IS-019`，营业收入→`IS-001`，营业成本→`IS-002`，货币资金→`BS-001`，权益年末→`EQ-ENDING`）；定位不到才回退原「编码 / 名精确 + 子串」逻辑（保住 P17 / truth 两组测试用的合成行）
- 毛利 `IS-003`：两版模板都没有毛利行 ⇒ 只在旧逻辑能精确命中名「毛利」时取，不再取 `IS-003` 编码（国企 = △利息收入）
- `execute_report_cross_checks` 补读权益变动表并传 `eq_rows`
- logic_check 不通过时 Issue 不带左右值（实测全为 null）⇒ `CrossCheckOutcome.refs` + `CrossCheckResult.inputs`（均有默认值，既有构造方不受影响），端点响应加 `refs` / `inputs`，界面逐条显示参与比较的数

### 2.7 鉴权
- `wp_report_analysis.py` 6 个端点改 `require_project_access("readonly")`；`native_authz_audit.py` 登记条目不动（说明仍成立）；`test_project_endpoint_authorization_baseline._IDENTITY_ONLY_BASELINE` 按现算下调

## 3. 前端

```
citar/screens/CitarReportAnalysis.vue        页头 + 标签栏 + 面板分发（报表 6 / 分析 4）
citar/components/CitarStatementView.vue      六张报表：审定 / 未审 / 对比三态（资产负债表 / 利润表复用 CitarReportTable）
citar/components/CitarEquityMatrix.vue       权益变动表矩阵
citar/components/CitarCrossCheckPanel.vue    跨表核对
citar/components/CitarMultiYearPanel.vue     多年对比
citar/components/CitarTrendPanel.vue         变动分析
citar/components/CitarIndicatorsPanel.vue    财务比率 / 期初核对 / 试算全景
citar/useCitarReportAnalysis.ts              标签定义、请求与数据整形（单测覆盖）
citar/useCitarReportGenerate.ts              生成报表（审定报表页同用）
citar/styles/report-analysis.css             复用 unaudited.css / citar-data.css 之外的少量样式
```
- 标签：报表组（资产负债表 / 利润表 / 现金流量表 / 权益变动表 / 现金流附表 / 减值准备表）｜分析组（跨表核对 / 多年对比 / 变动分析 / 财务指标）。「财务指标」内三段：财务比率、期初核对、试算全景（对应旧「分析」标签的三个子页）
- 9 个旧标签全部有落点，「变动分析」是新增（后端已有、旧页没接）
- 报表三态用小号分段按钮；对比视图在前端按 row_code 合并审定与未审（与旧 `useReportData` 同口径）
- 请求带 `_silent`，错误在面板内中文提示
- 不复用旧 `ReportView` 的 el-table 组件（Element 样式与 CITAR 版式冲突），用 `sheet-table`

## 4. 测试
- 后端：`test_report_row_locator.py`（两版模板真实行名 + 合成行）、`test_report_analysis_endpoints.py`（401 / 403 / 200 + 比率数值 + 期初找上年 + 平衡）、跨表核对按模板行名的用例；既有 P17 / truth / full_view / financial_ratio 测试保持绿
- 前端：`useCitarReportAnalysis.spec.ts`（对比合并、变动率、空态文案）
- 变异：定位器改回编码取数、端点摘鉴权，测试须红
- 浏览器：辽宁项目逐标签实测
