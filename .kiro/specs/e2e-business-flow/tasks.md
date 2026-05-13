# 业务流程端到端联调 — 任务清单

> 对应：requirements.md F1-F15 / design.md D1-D6
> 总工期：~5 天（3 Sprint）

---

## Sprint 1：P0 基础通路（2 天）

- [ ] 1. F1/D1: start-dev.bat 的 uvicorn 命令加 `--reload-exclude "__pycache__"` 避免 recalc 时 worker 被杀
- [ ] 2. F2: TrialBalance.vue onRecalc 完成后确认 fetchData() 被调用（已有，验证生效）
- [ ] 3. F14: 确认 standard_account_chart.json 的 166 个标准科目已加载到 account_chart 表（source=standard）；如未加载则新建 seed 端点
- [ ] 4. F3/D2: report_engine.py generate_all_reports 开头加前置检查（trial_balance 有数据 + report_config 有配置）
- [ ] 5. F15: 验证 report_config seed 中的 formula 字段（TB 函数语法）能被 ReportEngine 正确解析
- [ ] 6. F3: 检查 report_line_mapping 表是否有数据；无则从 soe_listed_mapping_preset.json 自动加载
- [ ] 7. F4: 用真实项目（陕西华氏）调用 POST /api/reports/generate 验证四张报表生成成功
- [ ] 8. F4: 前端 ReportView.vue 加载报表数据验证（切换四张报表都有行数据）
- [ ] 9. F9: 用真实项目调用 POST /api/disclosure-notes/generate 验证附注生成成功
- [ ] 10. F10: 前端 DisclosureEditor.vue 加载附注目录树验证

---

## Sprint 2：P0+P1 底稿 + 附注取数（2 天）

- [ ] 11. F6: 确认 template_sets seed 已加载（6 个模板集）；为真实项目选择模板集
- [ ] 12. F6: 调用 POST /api/projects/{pid}/working-papers/generate-from-codes 生成底稿
- [ ] 13. F7: 前端 WorkpaperList.vue 验证底稿列表展示（编码/名称/循环/状态）
- [ ] 14. F8: 验证 wp_mapping 关联建立（底稿 → 科目编码，从 wp_account_mapping.json）
- [ ] 15. F11: 附注表格"本期金额"列从试算表审定数自动填充验证
- [ ] 16. F5: 报表行次穿透验证（点击金额 → drilldown 端点返回科目明细）
- [ ] 17. F13/D6: 新建 AccountMappingPage.vue（映射列表 + 完成率 + 手动调整）
- [ ] 18. F13: router/index.ts 新增 /projects/:id/mapping 路由

---

## Sprint 3：P1 流程引导 + 验收（1 天）

- [ ] 19. F12/D5: 新建 WorkflowProgress.vue 组件（6 步进度条）
- [ ] 20. F12: TrialBalance.vue 引入 WorkflowProgress + "生成报表"下一步按钮
- [ ] 21. F12: ReportView.vue 引入 WorkflowProgress + "生成底稿"/"生成附注"下一步按钮
- [ ] 22. F12: WorkpaperList.vue 引入 WorkflowProgress
- [ ] 23. F12: DisclosureEditor.vue 引入 WorkflowProgress
- [ ] 24. 全流程 E2E 验证：陕西华氏项目从试算表→报表→底稿→附注全链路浏览器操作

---

## UAT 验收清单（手动浏览器验证）

- [ ] UAT-1: 选择陕西华氏项目，进入试算表，点"全量重算"，确认数据刷新（≥100 行）
- [ ] UAT-2: 进入报表页面，点"生成报表"，确认资产负债表有数据行
- [ ] UAT-3: 点击报表某行金额，确认穿透到试算表科目
- [ ] UAT-4: 进入底稿列表，确认有底稿（≥20 个）
- [ ] UAT-5: 进入附注编辑器，确认目录树有章节，点击章节有内容
- [ ] UAT-6: 确认附注表格"本期金额"列有数值（从试算表取数）
- [ ] UAT-7: 确认流程进度条在每个页面正确显示当前步骤
