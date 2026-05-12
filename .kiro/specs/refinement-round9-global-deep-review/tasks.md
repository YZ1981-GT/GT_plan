# R9 全局深度复盘 — 任务清单

> 对应：requirements.md F1-F25 / design.md D1-D14  
> 总工期：~17 天（5 Sprint）

---

## Sprint 1：P0 金额显示 + 权限 + 穿透 + 页头统一（3-4 天）

- [x] 1. F3: 新建 `utils/formatAmount.ts` 统一千分位格式化函数
- [x] 2. F3: LedgerPenetration.vue 金额列 width 从 170→200，加 min-width="180"
- [x] 3. F3: Drilldown.vue 金额列同步调整列宽
- [x] 4. F4: 补 v-permission — ArchiveWizard "开始归档" (archive:execute)
- [x] 5. F4: 补 v-permission — RecycleBin "恢复/永久删除" (recycle:restore/recycle:purge)
- [x] 6. F4: 补 v-permission — SamplingEnhanced "执行抽样" (sampling:execute)
- [x] 7. F4: 补 v-permission — ReportConfigEditor "保存" (report_config:edit)
- [x] 8. F4: 补 v-permission — IssueTicketList "关闭" (ticket:close)
- [x] 9. F4: 补 v-permission — Adjustments "新增 AJE" (adjustment:create)
- [x] 10. F4: 补 v-permission — ManagerDashboard "派单" (assignment:batch)
- [x] 11. F4: 补 v-permission — QCDashboard "发起抽查" (qc:initiate)
- [x] 12. F4: ROLE_PERMISSIONS 补齐新增权限码 (recycle:restore/purge, sampling:execute, report_config:edit, ticket:close, adjustment:create, qc:initiate)
- [x] 13. F4: 更新 scripts/find-missing-v-permission.mjs 规则（含 onDelete/onArchive/onSign/onExport 模式检测）
- [x] 14. F5: LedgerPenetration.vue drillToLedger 改为调 usePenetrate.toLedger()
- [x] 15. F5: Adjustments.vue 金额列加 @click 穿透到序时账
- [x] 16. F5: Misstatements.vue 错报金额加穿透
- [x] 17. F5: DisclosureEditor.vue 补"穿透到序时账"右键菜单项
- [x] 18. F5: AuxSummaryPanel.vue 辅助余额穿透到辅助序时
- [x] 19. F1: GtPageHeader.vue 新增 variant="banner" + icon prop
- [x] 20. F1: 批量接入模式 A — 18 个简单标题视图替换为 GtPageHeader
- [x] 21. F1: 批量接入模式 B — 7 个 Dashboard banner 视图替换

---

## Sprint 2：P1 角色体验 + AI 统一 + 编辑增强（4-5 天）

- [x] 22. F7-PM: ManagerDashboard 新增"待审批工时"聚合卡片
- [x] 23. F7-QC: QCDashboard 新增"本年抽查覆盖率"卡片
- [x] 24. F7-Partner: PartnerDashboard 补"待签字项目"一键跳转按钮
- [x] 25. F7-EQCR: EqcrProjectView 新增"关键发现摘要"Tab
- [x] 26. F8: 新建 composables/useAiChat.ts（统一 SSE 流式 + 消息历史 + 上下文注入）
- [x] 27. F8: AiAssistantSidebar.vue 改为调 useAiChat（保留 UI 壳）
- [x] 28. F8: AIChatPanel.vue 改为调 useAiChat（保留文件分析功能）
- [x] 29. F8: WorkpaperWorkbench.vue 删除内联 AI 聊天代码，改用 SidePanel AI Tab
- [x] 30. F9: WorkpaperEditor.vue 确认 Univer Ctrl+Z/Y 不被 shortcutManager 拦截
- [x] 31. F9: 移除 shortcutManager 对 undo/redo 的注册（让 Univer 原生处理）
- [x] 32. F10: usePasteImport 接入 TrialBalance.vue（粘贴 AJE 到调整列）
- [x] 33. F10: usePasteImport 接入 Adjustments.vue（粘贴多行分录）
- [x] 34. F10: usePasteImport 接入 WorkHoursPage.vue（粘贴批量工时）
- [x] 35. F15: WorkHoursPage.vue 新增"待审批"Tab + 顶栏 badge

---

## Sprint 3：P1 续 组件接入 + 硬编码清零 + 枚举（3 天）

- [x] 36. F2: Drilldown.vue 12 处 `<span class="gt-amt">` 替换为 GtAmountCell
- [x] 37. F2: LedgerPenetration.vue 20+ 处替换为 GtAmountCell
- [x] 38. F2: LedgerImportHistory.vue 6 处替换为 GtAmountCell
- [x] 39. F2: Adjustments.vue 金额列改用 GtAmountCell
- [x] 40. F2: Misstatements.vue 金额列改用 GtAmountCell
- [x] 41. F11: Adjustments.vue 从 el-table 改为 GtEditableTable
- [x] 42. F12: TrialBalance.vue 4 处 /api/ 硬编码迁移到 apiPaths
- [x] 43. F12: PartnerSignDecision.vue 5 处迁移
- [x] 44. F12: ProjectDashboard.vue 3 处迁移
- [x] 45. F12: DisclosureEditor.vue 4 处迁移
- [x] 46. F12: LedgerPenetration.vue 5 处迁移
- [x] 47. F12: 其他散落 9 处迁移（StaffManagement/Dashboard/QCDashboard/DataValidationPanel/WorkpaperEditor/WorkpaperList/ValidationRules/ManagerDashboard/qc/ClientQualityTrend）
- [x] 48. F13: statusEnum.ts 补齐缺失的状态常量（检查各视图硬编码 === 'xxx' 的字符串）
- [x] 49. F13: 各视图替换硬编码状态字符串为 statusEnum 常量引用

---

## Sprint 4：P2 维护性 + 通知 + 显示一致 + 全屏 + 加载规范（4-5 天）

- [x] 50. F18: 安装 vitest + @vue/test-utils + jsdom，新建 vitest.config.ts
- [x] 51. F18: 编写 usePenetrate 单测（≥5 用例）
- [x] 52. F18: 编写 useEditingLock 单测（≥5 用例）
- [x] 53. F18: 编写 useProjectEvents 单测（≥5 用例）
- [x] 54. F18: 编写 useAiChat 单测（≥5 用例）
- [x] 55. F19: 安装 @playwright/test，新建 playwright.config.ts
- [x] 56. F19: 编写 E2E — 登录 happy path
- [x] 57. F19: 编写 E2E — 创建项目 + 导入账套
- [x] 58. F19: 编写 E2E — 查账穿透（余额→序时账）
- [x] 59. F16: NotificationCenter.vue 新增分类 Tab（全部/复核/导入/系统）
- [x] 60. F16: 免打扰时段逻辑（22:00-08:00 不弹 toast）
- [x] 61. F20: 审计全局 CSS 变量覆盖率，消除内联 style 硬编码字号/间距
- [x] 62. F6: 穿透闭环路径文档化（docs/PENETRATION_MAP.md）+ 前端面包屑导航验证
- [x] 63. F14: ReviewWorkbench.vue 中栏嵌入 Univer 只读实例（加载 wpSnapshot + reviewMarkers 高亮）
- [x] 64. F17: KnowledgeBase.vue / KnowledgePickerDialog.vue 搜索时注入当前底稿上下文（wp_code + account_name）
- [x] 65. F17: 后端 /api/knowledge-library/search 新增可选 context 参数做相关性加权
- [x] 66. F24: LedgerPenetration.vue 全屏改用 useFullscreen composable（替代自定义 isFullscreen ref）
- [x] 67. F24: Adjustments.vue 新增全屏按钮 + useFullscreen 接入
- [x] 68. F24: Misstatements.vue 新增全屏按钮 + useFullscreen 接入
- [x] 69. F23: 审计所有视图 loading 模式，统一规范文档（表格=v-loading / 页面首屏=el-skeleton / 弹窗=v-loading）

---

## Sprint 5：P0+P1 补充 — 错误处理 + 编辑模式 + 死代码（2-3 天）

- [x] 70. F25: 删除 components/ai/ContractAnalysis.vue（零引用）
- [x] 71. F25: 删除 components/ai/ContractAnalysisPanel.vue（零引用）
- [x] 72. F25: 删除 components/ai/EvidenceChainPanel.vue（零引用）
- [x] 73. F25: 删除 components/ai/EvidenceChainView.vue（零引用）
- [x] 74. F25: 删除 components/workpaper/AiContentConfirmDialog.vue（与 ai/ 下重复）
- [x] 75. F25: 删除 views/ReviewInbox.vue（无路由引用）
- [x] 76. F21: 批量替换 — 所有 catch 块内 ElMessage.error 改为 handleApiError（预计 20+ 视图）
- [x] 77. F21: CI 新增 grep 卡点：catch 块内禁止裸 ElMessage.error（基线 0）
- [x] 78. F22: Adjustments.vue 接入 useEditMode（替代自定义 editing ref）
- [x] 79. F22: WorkHoursPage.vue 接入 useEditMode
- [x] 80. F22: StaffManagement.vue 接入 useEditMode
- [x] 81. F22: SubsequentEvents.vue 接入 useEditMode
- [x] 82. F22: SamplingEnhanced.vue 接入 useEditMode
- [x] 83. F22: CFSWorksheet.vue 接入 useEditMode

---

## UAT 验收清单（手动浏览器验证，不占 taskStatus）

- [ ] UAT-1: 以审计助理登录，LedgerPenetration 查看大金额科目（12 位数字），确认不折行
- [ ] UAT-2: 以审计助理登录，点击任意金额穿透到序时账，再穿透到凭证详情
- [ ] UAT-3: 以项目经理登录，确认 ManagerDashboard 显示"待审批工时"卡片
- [ ] UAT-4: 以合伙人登录，确认 PartnerDashboard 有"待签字"跳转按钮
- [ ] UAT-5: 以 EQCR 登录，确认 EqcrProjectView 有"关键发现摘要"Tab
- [ ] UAT-6: 以 admin 登录，尝试无权限操作（如普通用户点归档），确认被 v-permission 拦截
- [ ] UAT-7: 在底稿编辑器中编辑单元格后按 Ctrl+Z，确认撤销生效
- [ ] UAT-8: 从 Excel 复制多行数据粘贴到调整分录表，确认自动解析入库
