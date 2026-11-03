# 任务：CITAR「报表分析」菜单

- [x] 1. 行定位单一来源 `report_row_locator.py` + 四套模板（国企 / 上市 × 单体 / 合并）真实行名测试
- [x] 2. 财务比率按行名取数、mode 生效、分子分母溯源、周转率 / ROE 用平均余额；取不到写原因
- [x] 3. 变动分析 mode 生效（共用 `report_analysis_rows`）、上期为空或 0 不算变动率、过滤已删除
- [x] 4. 期初核对自动找上年项目（`prior_year_context.find_prior_project`），找不到写原因、不列假差异
- [x] 5. 试算全景平衡判断改为「无说不清来源的调整」，列出 `unexplained`
- [x] 6. 跨表核对按行名取数 + 传入权益变动表；结果带回 `inputs` / `refs`（参与比较的数）；P17 / truth 测试保持绿
- [x] 7. `wp_report_analysis.py` 6 端点改 `require_project_access("readonly")`，`mode` 限定两值；端点级测试（401 / 403 / 200 / 422）；鉴权基线 191 → 183
- [x] 8. 前端 `useCitarReportAnalysis.ts` + 单测 9 例；生成报表抽成 `useCitarReportGenerate.ts`（审定报表页同用）
- [x] 9. 前端页面与组件（报表 6 + 分析 4），路由由待开发页切到 `CitarReportAnalysis.vue`
- [x] 10. stylelint / eslint / 单区域 vue-tsc 通过（stylelint 注入字面量、vue-tsc 注入 TS2322 均能报出）；后端相关测试 208 passed；磁盘变异 6 条（临时 worktree）全部打红
- [x] 11. 浏览器实测（辽宁卫生服务有限公司_2025）：10 个标签逐个打开、审定 / 未审 / 对比切换、权益表对比禁用、控制台 0 错误 0 警告；审定报表页回归正常

## 验收记录
- 后端：`test_report_row_locator.py` + `test_report_analysis_endpoints.py` 与既有 `test_financial_ratio_service` / `test_audited_read_paths_unified` / `test_logic_check_truth` / `test_pbt_p17_crosscheck_equiv` / `test_formula_type_runtime_status` / `test_project_endpoint_authorization_baseline` 共 208 passed
- 变异（`C:\Users\baiji\_ra_wt` 分离头 worktree，每条逐字节恢复）：定位器失效、比率回到写死编码、净利润不要求顶层行（首轮存活，补用例 `test_net_profit_sub_item_alone_is_not_net_profit`）、端点摘鉴权、期初不找上年项目、平衡恢复倒挤自证 —— 6 条全红，恢复后 96 passed
- 真库（辽宁）：财务比率 9 项全部有值（流动比率 1.17、资产负债率 84.10% 标关注）；跨表核对 7 项 4 项不通过，均为数据本身：资产负债表不平（资产 819,743,726.02 vs 负债 + 权益 690,926,382.61，与 `citar-pages-data-wiring` R8 记录的导入数据问题同源）、权益变动表本年年末余额 0.00、有效税率 15%；期初核对显示「没有上年项目」；试算全景 174 科目无未解释调整

## 交付备注
- 「编制单位」「审核年度」在本页与审定报表页都为空：取自 CITAR 项目信息（`CITAR_PROJECT_KEY`），与本次改动无关，未改
- 范围外未改：`GET /api/reports/{pid}/{year}/{type}` 只校登录（`reports.py`，已在 consol-autotree 登记）；旧 `ReportView` 的前端降级勾稽 `computeCrossCheckResults` 仍按编码取数（新页面只用后端结果）；权益变动表多数行没有 `eq_matrix`（报表生成侧）
- 未提交
