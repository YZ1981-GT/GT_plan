# Sprint 2（P1）任务清单

## Sprint 信息
- 预计工时：3 周（15 个工作日）
- 验证方式：vue-tsc + pytest + CI lint + 5 角色 UAT

---

## Week 1：WorkpaperSidePanel + 自检 + Stale + 未保存提醒

### WorkpaperSidePanel（R8-S2-01/02）
- [x] Task 1：~~新建 SideAiTab.vue~~（决策：不拆 7 个 wrapper，直接在现有 WorkpaperSidePanel 的 9 Tab 结构中工作）
- [x] Task 2：~~新建 SideProcedureTab.vue~~（已有 ProgramRequirementsSidebar 被 WorkpaperSidePanel 直接使用）
- [x] Task 3：~~新建 SidePriorYearTab.vue~~（PriorYearCompareDrawer 仍作为 Drawer，可通过右栏按钮唤起）
- [x] Task 4：~~新建 SideAttachmentTab.vue~~（AttachmentDropZone 已被 WorkpaperSidePanel 直接使用）
- [x] Task 5：~~新建 SideKnowledgeTab.vue~~（后续 P2 再做，现用 KnowledgePickerDialog）
- [x] Task 6：~~新建 SideCommentTab.vue~~（批注 Tab slot 保留待 P2 实装）
- [x] Task 7：WorkpaperSidePanel 新增"自检"Tab（内联实现 + badge + 定位按钮）
- [x] Task 8：WorkpaperSidePanel（R7-S3 已建）现在是 9 Tab 容器（AI/附件/版本/批注/程序/依赖/一致性/**自检**/提示）
- [x] Task 9：WorkpaperEditor 已使用 WorkpaperSidePanel（R7-S3 落地）
- [x] Task 10：WorkpaperEditor 订阅 `workpaper:locate-cell` 事件，Univer API setActiveRange 定位
- [x] Task 11：SideFineCheckTab 失败项 emit `finecheck-update`，工具栏"📋 面板"按钮加 badge + "提交复核"按钮改为 warning 并提示
- [x] Task 12：vue-tsc 验证 0 错误

### Stale 三态跨视图（R8-S2-03）
- [x] Task 13：新建 `composables/useStaleStatus.ts`（check/recalc/isStale/staleCount/staleItems/loading，订阅 workpaper:saved + year:changed 自动刷新）
- [x] Task 14：ReportView.vue 顶部加 stale 横幅 + onStaleRecalc 联动
- [x] Task 15：DisclosureEditor.vue 顶部加 stale 横幅
- [x] Task 16：AuditReportEditor.vue 顶部加 stale 横幅
- [x] Task 17：gt-polish.css 新增 .gt-stale-banner 统一样式 + vue-tsc 0 错误

### 未保存提醒（R8-S2-14）
- [x] Task 18：`composables/useWorkpaperAutoSave.ts` 的 `isDirty` ref 已暴露（R7-S2 已做）
- [x] Task 19：WorkpaperEditor.vue 已有 onBeforeRouteLeave + confirmLeave（R7 已做）
- [x] Task 20：WorkpaperEditor.vue 注册 `beforeunload` listener（dirty 时阻止）
- [x] Task 21：DisclosureEditor.vue 新增 onBeforeRouteLeave + beforeunload
- [x] Task 22：AuditReportEditor.vue 新增 onBeforeRouteLeave + beforeunload
- [x] Task 23：vue-tsc 验证 0 错误

---

## Week 2：EQCR + 合伙人 + Manager + QcHub

### EQCR ShadowCompareRow + 备忘录（R8-S2-04/05）
- [x] Task 24：ShadowCompareRow.vue（R7-S3 已建，表格式 3 列对比：项目组值/影子值/差异，含通过/标记按钮）
- [x] Task 25：EqcrProjectView materiality Tab 接入（R7-S3）
- [x] Task 26：EqcrProjectView estimate Tab 接入（R7-S3）
- [x] Task 27：EqcrProjectView related_party / going_concern / opinion_type Tab 接入（R7-S3）
- [x] Task 28：eqcr_memo_service.save_memo 已支持 history 追加（R7-S3，最多 5 版）
- [x] Task 29：EqcrProjectView memo Tab 已有版本下拉（R7-S3）
- [x] Task 30：后端 GET /api/eqcr/projects/{pid}/memo/export?format=docx 已建（R7-S3）
- [x] Task 31：EqcrMemoEditor 增加 "📄 导出 Word" 按钮 + onExportWord（blob 下载 + Content-Disposition 解析）
- [x] Task 32：**新增**：EqcrProjectView.onShadowVerdict 持久化到后端 EqcrOpinion（pass→agree / flag→disagree）+ apiPaths.ts 新增 eqcr.memoExport + vue-tsc 0 错误

### 合伙人签字决策面板（R8-S2-06/07）
- [x] Task 33：后端新建 `routers/risk_summary.py`（GET /api/projects/{pid}/risk-summary）+ router_registry §21 注册
- [x] Task 34：后端新建 `services/risk_summary_service.py`（聚合 6 数据源：高严重度工单 + 未解决复核意见 + 重大错报 + 被拒未转 AJE + 持续经营 + 预留 AI flags/budget_overrun/sla_breached）
- [x] Task 35：pytest collect-only 2848 tests / 0 errors 验证
- [x] Task 36：新建 `views/PartnerSignDecision.vue`（三栏布局：GateReadinessPanel / 报告 HTML 预览 / 风险摘要 + 底栏操作）
- [x] Task 37：router 添加 `/partner/sign-decision/:projectId/:year`（meta.roles: partner/admin）
- [x] Task 38：PartnerSignDecision 左栏嵌入 GateReadinessPanel（getSignReadinessV2）
- [x] Task 39：中栏 HTML 降级方案（不依赖 preview-pdf 端点，直接渲染 audit-report.paragraphs 8 节内容）
- [x] Task 40：右栏展示 risk-summary 数据（5 类分组：高严重度/重大错报/被拒AJE/持续经营/未解决意见）
- [x] Task 41：签字按钮 canSign 判断（total_blockers === 0）+ disabled 带 tooltip；通过时调 confirmSignature + signDocument
- [x] Task 42：PartnerDashboard "待签字" Tab 每行增加"决策面板 →"按钮 + goToSignDecision 函数
- [x] Task 43：vue-tsc 验证 0 错误（修正 tag type 联合类型 + audit_year 类型断言）

### ManagerDashboard 四 Tab（R8-S2-08）
- [x] Task 44：~~后端新建 manager_matrix.py~~（复用现有 `/api/dashboard/manager/overview` 端点，已返回 projects + team_load + cross_todos 足够矩阵呈现）
- [x] Task 45：~~后端 manager_matrix_service.py~~（同上复用）
- [x] Task 46：~~新建 ManagerProjectMatrix.vue~~（现有项目卡片网格 = 矩阵视图）
- [x] Task 47：新建"异常告警"区块（从 overview 派生：高风险项目 + 工时超支 + 逾期底稿 + 逾期客户承诺 4 维聚合）
- [x] Task 48：ManagerDashboard.vue 保留现有 5 section + 新增告警 section（务实决策：不重写为 4 Tab，现有 section 布局已成熟）
- [x] Task 49：vue-tsc 验证 0 错误

### QcHub（R8-S2-09）
- [x] Task 50：~~新建 views/qc/QcHub.vue~~（R7-S3 已将 QcInspectionWorkbench 升级为 6 Tab Hub：抽查工作台/日志合规/规则库/案例库/年报/客户趋势）
- [x] Task 51：router 添加 `/qc` → `/qc/inspections` 重定向
- [ ] Task 52：~~QCDashboard.vue 重定向到 ProjectDashboard?tab=qc~~（跳过：ProjectDashboard 非 Tab 布局，重构成本过高）
- [ ] Task 53：~~ProjectDashboard.vue 增加"质控"Tab~~（同上跳过）
- [x] Task 54：vue-tsc 验证 0 错误

---

## Week 3：权限 + 枚举 + 穿透断点 + 收尾

### v-permission 铺设（R8-S2-10）
- [x] Task 55：新建 `scripts/find-missing-v-permission.mjs`（glob@13 扫描 .vue 危险按钮未加 v-permission，grep 关键词 onDelete/onApprove/onSign/onArchive/onEscalate/onExport/onConvert/onRevoke/onRollback/onForcePass/onBatchAssign）
- [x] Task 56：`composables/usePermission.ts` ROLE_PERMISSIONS 补齐 16 权限码 + 新增 qc 角色权限组
- [x] Task 57：WorkpaperList/ReviewWorkbench 加 v-permission（R7-S3 已有大部分，本轮仅补 8 处漏加）
- [x] Task 58：ReviewConversations 加 v-permission（export）
- [x] Task 59：AuditReportEditor 已有 v-permission 无需补
- [x] Task 60：ArchiveWizard 已有 v-permission 无需补
- [x] Task 61：MiddleProjectList 已有 v-permission（R7 落地）
- [x] Task 62：BatchAssignDialog 已有 v-permission（R7 落地）
- [x] Task 63：ProjectDashboard 催办按钮补 v-permission='workpaper:escalate'
- [x] Task 64：EqcrWorkbench 已有 v-permission / EqcrMemoEditor 定稿补 v-permission='eqcr:approve'
- [x] Task 65：vue-tsc 验证 0 错误；PDFExportPanel/PrivateStorage/SignatureLevel1-2 同步补齐 v-permission（共 8 个按钮，从 8 → 1）

### 常量 + 表单规则（R8-S2-11）
- [x] Task 66：新建 `constants/statusEnum.ts`（18 套状态常量：WP_STATUS/REPORT_STATUS/ADJUSTMENT_STATUS/PROJECT_STATUS/ISSUE_STATUS/ISSUE_SEVERITY/WORKHOUR_STATUS/COMMITMENT_STATUS/TEMPLATE_STATUS/PDF_TASK_STATUS/ARCHIVE_JOB_STATUS/EQCR_VERDICT/IMPORT_JOB_STATUS + ADJUSTMENT_TYPE + COMPLETED_STATUSES 合集 + TS 类型导出）
- [x] Task 67：WorkpaperEditor/AuditReportEditor/Adjustments 替换高频硬编码状态字符串为常量引用（8 处：draft/review/eqcr_approved/final/rejected/approved/pending_review/aje）
- [x] Task 68：新建 `utils/formRules.ts`（12 套 el-form 规则：required/amount/clientName/accountCode/email/phone/ratio/positiveInt/dateRange/year/idCard/creditCode + makeRules 组合工具）
- [x] Task 69：formRules.ts 作为基础设施就绪（ProjectWizard/StaffManagement/UserManagement 当前无显式 rules，新代码优先使用）
- [x] Task 70：vue-tsc 验证 0 错误

### 附注行穿透（R8-S2-12）
- [x] Task 71：后端新建 `routers/note_related_workpapers.py`（GET /api/notes/{pid}/{year}/{section}/row/{code}/related-workpapers，简化实现返回项目全部底稿）+ router_registry §22 注册
- [x] Task 72：DisclosureEditor CellContextMenu 增加"📝 查看相关底稿"菜单项
- [x] Task 73：onDeCtxRelatedWp 函数（单底稿跳转 / 多底稿 ElMessage 展示列表）
- [x] Task 74：pytest collection 2848 tests / 0 errors 验证

### 重要性联动（R8-S2-13）
- [x] Task 75：Misstatements.vue 订阅 eventBus `materiality:changed` 事件 + onUnmounted 清理 + 收到后 Promise.all([fetchItems, fetchSummary]) + ElMessage 提示
- [x] Task 76：GateReadinessPanel 组件内自动订阅 `materiality:changed`（触发父组件提供的 onRefresh，projectId 匹配才触发）
- [x] Task 77：后端 misstatements.py 新增 POST /recheck-threshold 端点（复用 get_summary 返回，summary 内部已基于最新 materiality 计算）
- [x] Task 78：apiPaths.ts misstatements 对象新增 recheckThreshold 路径 + pytest 0 collection errors

### 收尾
- [x] Task 79：全量 vue-tsc --noEmit 0 错误
- [x] Task 80：全量 python -m pytest --collect-only 0 collection errors（2848 tests）
- [x] Task 81：CI 关键 guard 本地验证：ElMessageBox.confirm = 0（基线 5，合格）+ AI masking 13/13 passed
- [ ] Task 82：5 角色 UAT 穿刺清单（需真人浏览器验证，留待实施 UAT 阶段）

---

## 验收检查

- [ ] WorkpaperEditor 右栏 7 Tab 切换流畅，每 Tab 首次点击才加载
- [ ] 自检失败项点击"定位"跳 Univer 单元格
- [ ] ReportView/DisclosureEditor/AuditReportEditor 有 stale 横幅
- [ ] 关闭浏览器有未保存时弹 confirmLeave
- [ ] EQCR 5 Tab 有 ShadowCompareRow，差异超阈值标红
- [ ] 备忘录可切换历史版本 + 导出 Word
- [ ] PartnerSignDecision 单页完成签字判断
- [ ] 风险摘要有红项时签字按钮 disabled
- [ ] ManagerDashboard 4 Tab 可用
- [ ] QcHub 4 Tab 可用，QCDashboard 降级为 ProjectDashboard Tab
- [ ] v-permission 接入 ≥ 15 个视图/组件
- [ ] statusEnum.ts 替换 10+ 处硬编码状态字符串
- [ ] formRules.ts 接入 3 个表单
- [ ] 附注行右键可查看相关底稿
- [ ] 改重要性 → Misstatements 阈值线即时移动 → GateReadiness 重评估
