# Sprint 1（P0）任务清单

## Sprint 信息
- 预计工时：1 天
- 验证方式：vue-tsc --noEmit + CI "API hardcode guard" + 手动登录验证

## 任务

- [x] Task 1：删除 `views/ReviewInbox.vue`
- [x] Task 2：apiPaths.ts 新增 `my.pendingIndependence` + `qcDashboard.reviewerMetrics`
- [x] Task 3：PartnerDashboard.vue 第 561、582 行替换为 apiPaths 调用
- [x] Task 4：QCDashboard.vue 第 325 行替换为 apiPaths 调用
- [x] Task 5：DefaultLayout.vue isEqcrEligible 加 `'eqcr'`
- [x] Task 6：router/index.ts EqcrMetrics meta.roles 加 `'eqcr'`
- [x] Task 7：stores/auth.ts login() 末尾加角色跳转逻辑
- [x] Task 8：删除 5 个 Mobile*.vue + router 对应 5 条路由
- [x] Task 9：router/index.ts 新增 `/confirmation` 路由（developing）
- [x] Task 10：删除 `components/ai/ContractAnalysis.vue`
- [x] Task 11：删除 `components/ai/ContractAnalysisPanel.vue`
- [x] Task 12：删除 `components/ai/EvidenceChainPanel.vue`
- [x] Task 13：删除 `components/ai/EvidenceChainView.vue`
- [x] Task 14：删除 `components/workpaper/AiContentConfirmDialog.vue`，修正引用
- [x] Task 15：utils/confirm.ts 新增 5 个语义化函数
- [x] Task 16：新建 `components/common/GtEmpty.vue`
- [x] Task 17：运行 vue-tsc --noEmit 验证 0 错误
- [x] Task 18：运行 CI "API hardcode guard" 验证基线下降

## UAT 验收（手动）
- [ ] admin 登录落到 /
- [ ] auditor 登录落到 /my/dashboard
- [ ] partner 登录落到 /dashboard/partner
- [ ] eqcr 登录后顶栏可见"📊 EQCR 指标"
- [ ] 点击侧栏"函证"跳到 DevelopingPage
