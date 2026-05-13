# 业务流程端到端联调 — 任务清单 v2.0

> 对应 requirements F1-F29 / design D1-D10
> 总工期：~7 天（4 Sprint）
> 原则：每个 Sprint 结束必须用真实数据验证，不能只靠单测

---

## Sprint 1：P0 报表引擎修复（1.5 天）

> 目标：陕西华氏报表生成成功，BS ≥20 行非零

- [x] 1. F1/D1: 修正 _test_report_generation.py 字段名（current_period_amount），重新验证陕西华氏报表生成——确认 BS 非零行数
- [x] 2. F1/D1: 如果仍全零，在 _resolve_tb 加 debug 日志逐步排查；如果已有非零行则跳过排查
- [x] 3. F1: 通过 HTTP 端点 POST /api/reports/generate 验证（前端实际调用路径），确认 applicable_standard resolve 正确
- [x] 4. F4/D4: start-dev.bat uvicorn 加 --reload-exclude "__pycache__" --reload-exclude "*.pyc"
- [x] 5. F3/D4: 为宜宾大药房先执行 auto-match（确认 account_mapping 存在），再执行 recalc，验证 trial_balance 从 0→非零
- [x] 6. F2: 用 4 个项目逐一调用 generate_all_reports 验证全部成功（每个项目 BS 非零行 ≥10）
- [x] 7. F26/D8: 新建 prerequisite_checker.py — 4 个操作的前置条件检查
- [x] 8. F26: 在 reports.py/trial_balance.py 的生成端点前集成 checker（不满足返回 400 + 明确错误）
- [x] 9. F5/D2: 将 fill_report_formulas.py 核心逻辑封装为 ReportFormulaService.fill_all_formulas()
- [x] 10. F5/D2: 新建 POST /api/report-config/fill-formulas 端点（幂等，admin 权限）
- [x] 11. F22: report-config/seed 端点加载后自动调用 fill_all_formulas（确保新部署自动就绪）
- [x] 12. F25/D7: 新建 scripts/e2e_business_flow_verify.py Layer 1+2 验证（trial_balance + 报表非零，4 项目分别断言）

**Sprint 1 验收门槛**：
- 陕西华氏 BS ≥20 行非零，IS ≥10 行非零
- 辽宁卫生、和平药房 BS ≥10 行非零
- 宜宾大药房 trial_balance > 0（auto-match + recalc 后）
- 前置条件校验：recalc 无映射时返回 400 + 明确错误
- e2e 脚本 Layer 1+2 通过（4 项目分别断言）

---

## Sprint 2：P0+P1 前端报表展示 + 数据质量（2 天）

> 目标：前端报表表样完美 + 数据质量检查能检出差异

- [x] 13. F9: ReportView.vue 确认 6 种报表 Tab 都存在（BS/IS/CFS/EQ/CFS附表/减值准备）
- [x] 14. F9: ReportView.vue 调用 generate 时确认走 HTTP 端点（applicable_standard 自动 resolve）
- [x] 15. F9: 验证前端切换 Tab 每张报表都有行数据（浏览器手动验证）
- [x] 16. F27/D9: ReportView 表格行加 getRowType 判定逻辑（header/data/total/zero/special/manual 6 种）
- [x] 17. F27/D9: 添加 6 种行类型 CSS 样式（标题行加粗灰底/合计行加粗上边框/零值灰显/特殊行业斜体/金额右对齐千分位）
- [x] 18. F27: 金额列格式化——千分位 + 负数红色括号 + Arial Narrow + tabular-nums
- [x] 19. F27: 缩进可视化——indent_level × 24px padding-left
- [x] 20. F28: 报表底部显示数据覆盖率摘要（"129 行，55 行有数据，20 行标题行，35 行待填列"）
- [x] 21. F10: 报表行次穿透——点击非零金额弹出科目明细对话框
- [x] 22. F23: generate_all_reports 返回值增加 summary（{total_rows, non_zero_rows, failed_rows}）
- [x] 23. F24: ReportView 生成完成后 toast 显示摘要
- [x] 24. F26: 前端 catch 400 前置条件错误时显示 message + "去完成"跳转按钮
- [x] 25. F7/D3+D10: 新建 data_quality_service.py — 套件模式（借贷平衡 + 余额vs序时账 + 映射完整性）
- [x] 26. F7/D3: 新建 GET /api/projects/{pid}/data-quality/check 端点（支持 checks 参数）
- [x] 27. F8: 新建 DataQualityDialog.vue（分组展示检查结果，红/黄/绿三色）
- [x] 28. F8: TrialBalance.vue 增加"数据质量检查"按钮，点击打开 DataQualityDialog
- [x] 29. F8: 用陕西华氏验证——应检出差异科目（明细账不完整导致）
- [x] 30. F25: e2e 脚本增加 Layer 3（数据质量检查能执行 + 报表表样验证）

**Sprint 2 验收门槛**：
- 前端 ReportView 报表表样完美（6 种行类型可视区分）
- 金额列千分位 + 负数红色 + 右对齐
- 数据质量检查检出陕西华氏 ≥1 个差异科目
- 前置条件不满足时前端显示明确错误 + 跳转按钮
- vue-tsc 0 错误

---

## Sprint 3：P1 底稿 + 附注 + 映射（1.5 天）

> 目标：底稿/附注生成成功 + 科目映射页面可用

- [x] 31. F12: 确认 template_sets seed 已加载；为陕西华氏选择模板集
- [x] 32. F12: 调用 POST /api/projects/{pid}/working-papers/generate-from-codes 生成底稿
- [x] 33. F13: 前端 WorkpaperList.vue 验证底稿列表展示
- [x] 34. F14: 验证 wp_mapping 关联建立
- [x] 35. F15: 调用 POST /api/disclosure-notes/generate 生成附注
- [x] 36. F16: 前端 DisclosureEditor.vue 验证目录树展示
- [x] 37. F17: 附注表格"本期金额"从试算表取数验证
- [x] 38. F20/D6: 新建 AccountMappingPage.vue（映射列表 + 完成率 + 手动调整）
- [x] 39. F20: router/index.ts 新增 /projects/:id/mapping 路由
- [x] 40. F21: 项目设置增加"报表标准"选择（soe/listed），前端下拉框

**Sprint 3 验收门槛**：
- 陕西华氏有 ≥20 个底稿
- 附注目录树有章节
- 映射页面能展示映射列表

---

## Sprint 4：P1 流程引导 + 最终验收（1.5 天）

> 目标：全流程有引导 + 4 项目 E2E 通过

- [x] 41. F18/D5: 新建 GET /api/projects/{pid}/workflow-status 端点（从数据层推导 6 步进度）
- [x] 42. F18/D5: 新建 WorkflowProgress.vue 组件（el-steps 6 步 + 下一步按钮）
- [x] 43. F19: WorkflowProgress 从 workflow-status 端点获取进度（含阻塞原因）
- [x] 44. F18: TrialBalance.vue 引入 WorkflowProgress + "生成报表"按钮
- [x] 45. F18: ReportView.vue 引入 WorkflowProgress + "生成底稿"/"生成附注"按钮
- [x] 46. F18: WorkpaperList.vue 引入 WorkflowProgress
- [x] 47. F18: DisclosureEditor.vue 引入 WorkflowProgress
- [x] 48. F29/D10: 报表生成后自动执行报表平衡检查（BS 资产=负债+权益），结果显示在 ReportView 顶部
- [x] 49. F25: e2e 脚本完整 Layer 1-4 验证 + 4 项目全量跑
- [x] 50. 全流程浏览器手动验证：陕西华氏从试算表→报表→底稿→附注

**Sprint 4 验收门槛**：
- e2e_business_flow_verify.py 4 项目全通过
- 浏览器全流程无白屏/500
- 流程进度条正确显示 + 下一步按钮可用
- 报表平衡检查结果可见
- vue-tsc 0 错误

---

## UAT 验收清单（手动浏览器验证）

- [ ] UAT-1: 陕西华氏试算表有 ≥100 行数据
- [ ] UAT-2: 点"数据质量检查"，能看到差异报告
- [ ] UAT-3: 进入报表页面，BS 有非零数据行（货币资金/应收账款等）
- [ ] UAT-4: 点击报表某行金额，穿透到科目明细
- [ ] UAT-5: 进入底稿列表，有 ≥20 个底稿
- [ ] UAT-6: 进入附注编辑器，目录树有章节
- [ ] UAT-7: 流程进度条在每个页面正确显示
- [ ] UAT-8: 宜宾大药房也能走通试算表→报表流程
