# 项目上下文迁移清单 — 基线冻结

> 生成时间：P0-1 现状扫描
> 目的：记录所有需要迁移到统一 ProjectContext / 年度协议 / 权限矩阵 的散点

## 1. 项目 ID 解析点 (`route.params.projectId` / `route.query.project_id` / localStorage)

### 高频页面（P0 首批接入）

| 文件 | 解析方式 | 迁移优先级 |
|------|----------|-----------|
| `views/WorkpaperEditor.vue` | `route.params.projectId` (via useAuditContext) | P0 |
| `views/WorkpaperList.vue` | `route.params.projectId` (computed) | P0 |
| `views/TrialBalance.vue` | `projectStore.projectId \|\| route.params.projectId` | P0 |
| `views/ReportView.vue` | `projectStore.projectId \|\| route.params.projectId` | P0 |
| `views/DisclosureEditor.vue` | `route.params.projectId` (via useAuditContext) | P0 |

### 其他项目页面（P2 全量迁移）

| 文件 | 解析方式 |
|------|----------|
| `views/LedgerPenetration.vue` | `route.params.projectId` |
| `views/LedgerImportPage.vue` | `route.params.projectId` |
| `views/LedgerImportHistory.vue` | `route.params.projectId` |
| `views/IssueTicketList.vue` | `route.params.projectId` |
| `views/LinkagePanoramaView.vue` | `route.params.projectId` |
| `views/ConsolidationIndex.vue` | `route.params.projectId` |
| `views/ConsistencyDashboard.vue` | `route.params.projectId` |
| `views/ConfirmationHub.vue` | `projectStore.projectId \|\| route.params.projectId` |
| `views/ProjectDashboard.vue` | `route.params.projectId` |
| `views/ProjectProgressBoard.vue` | `route.params.projectId` |
| `views/PartnerProjectDashboard.vue` | `route.params.projectId` |
| `views/PartnerSignDecision.vue` | `route.params.projectId` |
| `views/QCDashboard.vue` | `route.params.projectId` |
| `views/ReviewWorkbench.vue` | `route.params.projectId` |
| `views/DeliverableCenter.vue` | `route.params.projectId` |
| `views/eqcr/EqcrProjectView.vue` | `route.params.projectId` |
| `views/extension/TAccountManagement.vue` | `route.params.projectId` |
| `views/independence/IndependenceDeclarationForm.vue` | `route.params.projectId` |
| `views/SamplingEnhanced.vue` | `route.params.projectId` |
| `views/SubsequentEvents.vue` | `route.params.projectId` |
| `views/TemplateManager.vue` | `route.params.projectId` |
| `views/TemplateLibraryMgmt.vue` | `route.params.projectId \|\| route.query.project_id` |
| `views/ProcedureTrimming.vue` | `route.params.projectId` |
| `views/ReportConfigBaselineTab.vue` | `route.params.projectId` |
| `views/PDFExportPanel.vue` | `route.params.projectId` |
| `views/TaskTreeView.vue` | `route.params.projectId` |
| `views/OfflineConflictWorkbench.vue` | `route.params.projectId` |
| `views/ConsolSnapshots.vue` | `route.params.projectId` |
| `views/Drilldown.vue` | `route.params.projectId` |

## 2. 年度硬编码 / selectedYear 散点

### 高频页面

| 文件 | 模式 | 问题 |
|------|------|------|
| `views/TrialBalance.vue` | `selectedYear = ref(projectStore.year)` | ✅ 已从 store 取 |
| `views/ReportView.vue` | `selectedYear = ref(new Date().getFullYear() - 1)` | ⚠️ 硬编码 fallback |
| `views/DisclosureEditor.vue` | `selectedYear = ref(new Date().getFullYear() - 1)` | ⚠️ 硬编码 fallback |
| `views/LedgerPenetration.vue` | `selectedYear = ref(2025)` | 🔴 硬编码年度 |
| `views/LedgerImportHistory.vue` | `selectedYear = ref(Number(route.query.year) \|\| new Date().getFullYear())` | ⚠️ fallback 到当年 |

### 注意项

- `views/ReportView.vue` L648: `new Date().getFullYear() - 1` — 应从 projectStore.year 取
- `views/LedgerPenetration.vue` L1036: `selectedYear = ref(2025)` — 硬编码，严重
- `views/DisclosureEditor.vue` L917: `new Date().getFullYear() - 1` — 应从 projectStore.year 取

## 3. 角色判断散点 (`role ===` / `user.role` / `usePermission`)

### 高频页面

| 文件 | 模式 | 迁移目标 |
|------|------|----------|
| `views/TrialBalance.vue` | `usePermission()` → `can('admin')`, `can('project:edit')` | → `usePermissionMatrix().can('wp:edit')` |
| `views/ReportView.vue` | `authStore.user?.role === 'eqcr'` | → `usePermissionMatrix().can('report:edit')` |
| `views/DisclosureEditor.vue` | `authStore.user?.role === 'eqcr'` | → `usePermissionMatrix().can('note:edit')` |
| `views/WorkpaperList.vue` | `authStore.user?.role` === 'auditor'/'qc' 判 Tab 可见 | → `usePermissionMatrix().can()` |
| `views/WorkHoursPage.vue` | `usePermission()` → `can(...)` | → `usePermissionMatrix()` |

### 组件层

| 文件 | 模式 |
|------|------|
| `views/components/NoteEditorToolbar.vue` | prop `isEqcrRole` 控制按钮显隐 |

## 4. 迁移策略总结

1. **P0 首批**：5 个高频页面（WorkpaperEditor/WorkpaperList/TrialBalance/ReportView/DisclosureEditor）接入 `useProjectStore().currentProjectContext` + `usePermissionMatrix()`
2. **P1**：其余项目内页面逐步替换 `route.params.projectId` → `projectStore.projectId`
3. **P2**：删除旧 `usePermission` 直接角色判断，全量迁移到权限矩阵

## 5. 风险标注

- `LedgerPenetration.vue` 硬编码 `2025` 是最高优先修复项
- `ReportView.vue` 和 `DisclosureEditor.vue` 使用 `new Date().getFullYear() - 1` 作为默认年度，在 12 月/1 月切换时可能展示错误年度
- 旧 `usePermission` composable 仍被多处使用，不可立即删除
