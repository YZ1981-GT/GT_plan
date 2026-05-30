# Sprint 1（P0）需求文档 — 零风险快速修复

## 目标

消除死代码、修复硬编码、补齐路由缺口、统一确认弹窗基础函数。1 天内完成，零回归风险。

## 需求清单

### R7-S1-01：删除 ReviewInbox.vue 死代码
- 删除 `audit-platform/frontend/src/views/ReviewInbox.vue`
- router 三条路由（ReviewInbox/ReviewInboxGlobal/review-inbox）已全部指向 ReviewWorkbench.vue，无需改 router
- 验收：vue-tsc 0 错误，grep `ReviewInbox.vue` 零命中

### R7-S1-02：修复 PartnerDashboard + QCDashboard 硬编码
- `PartnerDashboard.vue:561, 582` 的 `/api/my/pending-independence?limit=...` 改走 apiPaths
- `QCDashboard.vue:325` 的 `/api/qc/reviewer-metrics` 改走 apiPaths
- apiPaths.ts 新增 `my.pendingIndependence` 和 `qc.reviewerMetrics`
- 验收：CI "API hardcode guard" 基线从 173 降至 170

### R7-S1-03：EQCR 指标对 eqcr 角色开放
- `DefaultLayout.vue:132` 的 `isEqcrEligible` 加 `role === 'eqcr'`
- `router/index.ts:465` 的 `meta.roles` 加 `'eqcr'`
- 验收：eqcr 角色登录后顶栏可见"📊 EQCR 指标"按钮

### R7-S1-04：登录后角色跳转
- `stores/auth.ts` 的 login 成功后根据 `user.role` 做 `router.replace`
- 角色→路径映射：auditor→/my/dashboard, manager→/dashboard/manager, partner→/dashboard/partner, qc→/qc/inspections, eqcr→/eqcr/workbench, admin→/
- 若 URL 有 `redirect` query 则优先 redirect
- 验收：各角色登录后落到对应页面

### R7-S1-05：删除 Mobile 5 视图
- 删除 MobilePenetration / MobileReviewView / MobileReportView / MobileProjectList / MobileWorkpaperEditor 共 5 个 .vue 文件
- 删除 router/index.ts 中对应 5 条路由
- 验收：vue-tsc 0 错误，grep `Mobile` 在 views/ 零命中

### R7-S1-06：/confirmation 路由修复
- 方案 A（推荐）：router 新增 `/confirmation` 路由，指向 DevelopingPage.vue，meta: { developing: true }
- 侧栏 ThreeColumnLayout.vue:330 保留 maturity='developing'
- 验收：点击侧栏"函证"跳到 DevelopingPage 而非 NotFound

### R7-S1-07：AI 组件死代码清理
- 删除 `components/ai/ContractAnalysis.vue`
- 删除 `components/ai/ContractAnalysisPanel.vue`
- 删除 `components/ai/EvidenceChainPanel.vue`
- 删除 `components/ai/EvidenceChainView.vue`
- 删除 `components/workpaper/AiContentConfirmDialog.vue`（保留 `components/ai/` 版本）
- 修正引用（若有）指向 `components/ai/AiContentConfirmDialog.vue`
- 验收：vue-tsc 0 错误，components.d.ts 自动更新

### R7-S1-08：confirm.ts 补齐语义化函数
- 新增 `confirmSubmitReview(wpCode, wpName)` — 提交复核确认
- 新增 `confirmVersionConflict(serverVer, localVer)` — 版本冲突确认
- 新增 `confirmLeave(moduleLabel)` — 离开未保存确认
- 新增 `confirmConvert(fromLabel, toLabel)` — 转换确认（分录→错报）
- 新增 `confirmEscalate(targetRole)` — 升级催办确认
- 验收：5 个函数导出，类型正确

### R7-S1-09：统一空态组件 GtEmpty.vue
- 新建 `components/common/GtEmpty.vue`
- Props: title, description, actionText, icon?
- Emit: action
- 内部用 el-empty + 统一样式
- 验收：组件可用，vue-tsc 0 错误
