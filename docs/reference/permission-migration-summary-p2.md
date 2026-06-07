# 权限与上下文迁移总结 — P2 阶段

> 生成时间：2026-06-07
> 相关 spec：platform-context-permission-foundation P2

## 1. 迁移状态概览

| 阶段 | 状态 | 说明 |
|------|------|------|
| P0 高频页面接入 | ✅ 完成 | 5 个页面已用 usePermissionMatrix + ProjectContext |
| P1 项目设置中心 | ✅ 完成 | ProjectSettingsCenter + ProjectContextBar 全量接入 |
| P2 临时授权 | ✅ 完成 | ADR-030 + V060 + ORM + Service + 14 测试 |
| P2 旧入口 deprecated | ✅ 完成 | usePermission() 加 DEV 环境 console.warn |

## 2. `route.params.projectId` 解析点现状

### 已迁移到 ProjectContext（P0 首批）

| 页面 | 迁移方式 |
|------|----------|
| WorkpaperEditor | 使用 projectStore.projectId + route fallback |
| WorkpaperList | 使用 projectStore.projectId + route fallback |
| TrialBalance | 使用 projectStore.projectId ‖ route.params.projectId |
| ReportView | 使用 projectStore.projectId + route fallback |
| DisclosureEditor | 使用 projectStore.projectId + route fallback |

### 白名单：保留 route.params.projectId 的合理场景

以下页面因路由结构需要保留 `route.params.projectId` 作为入口获取项目 ID，
但应在 `onMounted` 时调用 `projectStore.loadProjectContext(projectId)` 确保统一：

| 页面 | 原因 |
|------|------|
| ProjectDashboard | 项目入口页，从 route 获取后加载 context |
| ProjectSettingsCenter | 项目设置入口，已接入 ProjectContext |
| PartnerProjectDashboard | 合伙人仪表盘入口 |
| PartnerSignDecision | 签发决策页入口 |
| QCDashboard | QC 仪表盘入口 |
| EqcrProjectView | EQCR 项目视图入口 |
| DeliverableCenter | 交付件中心入口 |
| ReviewWorkbench | 复核工作台（支持无 projectId 全局模式） |

### 待迁移（P3 可选，低优先级）

| 页面 | 说明 |
|------|------|
| LedgerPenetration | 已从 route 获取，可改为 projectStore |
| LedgerImportPage | 直接 route.params，可改为 projectStore |
| LedgerImportHistory | 直接 route.params + query.year |
| IssueTicketList | 简单页面，直接 route.params |
| CollaborationIndex | onMounted 中直接 route.params |
| OfflineConflictWorkbench | 简单页面 |
| ArchiveWizard | 归档向导，route 入口 |
| TaskTreeView | 任务树，route 入口 |
| SubsequentEvents | 期后事项 |
| SamplingEnhanced | 抽样 |
| ProcedureTrimming | 程序裁剪 |
| TemplateManager | 模板管理 |
| TemplateLibraryMgmt | 模板库（支持无 projectId） |
| PDFExportPanel | PDF 导出 |
| ReportConfigBaselineTab | 报表配置 |
| LinkagePanoramaView | 联动全景 |
| Drilldown | 穿透 |
| TAccountManagement | T 型账 |
| IndependenceDeclarationForm | 独立性声明 |
| AuditReportEditor | 审计报告编辑器 |
| WorkpaperSummary | 底稿汇总 |
| ReportTracePanel | 报表追溯面板 |
| ReviewConversations | 复核对话 |
| ProjectProgressBoard | 项目进度板 |
| ConsolidationIndex | 合并索引 |
| ConsistencyDashboard | 一致性仪表盘 |
| ConfirmationHub | 函证中心 |

## 3. 旧 `usePermission()` 调用点

### 已加 deprecated warning

`usePermission()` 函数已在 DEV 环境输出 console.warn 提示迁移。

### 当前仍使用 `usePermission()` 的文件

| 文件 | 用法 | 迁移建议 |
|------|------|----------|
| TrialBalance.vue | `can('admin')`, `can('project:edit')` 控制冻结开关 | → `canOp('archive:manage')` |
| WorkHoursPage.vue | `can(...)` 控制工时审批按钮 | → 权限矩阵新增 `workhour:approve` |
| BatchActionBar.vue | `can(...)` 控制批量操作 | → `canOp('wp:edit')` / `canOp('wp:review')` |
| ProcedureTrimmingPanel.vue | `role` 判断 manager+ | → `canOp('wp:edit')` |
| WorkpaperAuditNav.vue | `role` 判断 partner/qc/manager | → `canOp('wp:review')` |

### 直接角色字符串判断

| 文件 | 模式 | 迁移建议 |
|------|------|----------|
| ReportView.vue | `authStore.user?.role === 'eqcr'` | → `canOp('report:edit')` 取反 |
| DisclosureEditor.vue | `authStore.user?.role === 'eqcr'` | → `canOp('note:edit')` 取反 |

## 4. 年度硬编码残留

| 文件 | 问题 | 严重程度 |
|------|------|----------|
| LedgerPenetration.vue | `selectedYear = ref(2025)` → 已改用 route.query.year ‖ projectStore.year | ⚠️ 需确认 |
| ReportView.vue | `new Date().getFullYear() - 1` fallback | 低（有 projectStore.year 优先） |
| DisclosureEditor.vue | `new Date().getFullYear() - 1` fallback | 低（有 projectStore.year 优先） |
| LedgerImportHistory.vue | `route.query.year ‖ new Date().getFullYear()` | 低 |
| IndependenceDeclarationForm.vue | `currentYear = new Date().getFullYear()` | 低（独立性表单年度合理） |

## 5. 下一步（P3+ 可选）

1. 为 `WorkHoursPage` 权限矩阵新增 `workhour:approve` operation code
2. 逐步将白名单外的页面改为从 `projectStore.projectId` 获取
3. 全部迁移完成后可删除 `usePermission()` 及 `ROLE_PERMISSIONS` 导出
4. 前端 ESLint 规则禁止新增 `usePermission()` 调用

## 6. 临时授权产物清单

| 产物 | 路径 |
|------|------|
| ADR | `docs/adr/ADR-030-temporary-grant-dedicated-table.md` |
| Migration | `backend/migrations/V060__temporary_grants.sql` |
| Rollback | `backend/migrations/R060__temporary_grants_rollback.sql` |
| ORM Model | `backend/app/models/temporary_grant_models.py` |
| Pydantic Schema | `backend/app/models/temporary_grant_schemas.py` |
| Service | `backend/app/services/temporary_grant_service.py` |
| Contract Tests | `backend/tests/test_temporary_grant_contract.py` (14 tests) |
