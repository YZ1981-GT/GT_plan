import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

/**
 * Router domain: projects
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const projectsRoutes: RouteRecordRaw[] = [
{
          // 税审 demo：项目列表与项目内六个菜单改用 CITAR 版式（spec citar-layout-full-port）。
          // 路由名不变；原页面文件保留，改回 component 即恢复。
          path: 'projects',
          name: 'Projects',
          component: () => import('@/citar/CitarProjectList.vue'),
        },
{
          // CITAR 流程：从项目列表点进来先到项目空页，再由左侧一级栏进入各环节
          path: 'projects/:projectId/home',
          name: 'CitarProjectHome',
          component: () => import('@/citar/CitarProjectHome.vue'),
        },
{
          path: 'projects/full',
          name: 'ProjectsFull',
          component: () => import('@/views/Projects.vue'),
        },
{
          path: 'projects/new',
          name: 'ProjectWizard',
          component: () => import('@/views/ProjectWizard.vue'),
        },
{
          path: 'projects/:projectId/drilldown',
          name: 'Drilldown',
          component: () => import('@/views/Drilldown.vue'),
        },
{
          path: 'projects/:projectId/trial-balance',
          name: 'TrialBalance',
          // CITAR「试算平衡表」（审定科目余额表 / 底稿取数余额表，接试算表）；原页面 @/views/TrialBalance.vue
          component: () => import('@/citar/screens/CitarTrialBalance.vue'),
        },
{
          // CITAR「账务查询」：科目余额表 / 序时账 / 未审资产负债表 / 未审利润表
          path: 'projects/:projectId/ledger-query',
          name: 'CitarLedgerQuery',
          component: () => import('@/citar/screens/CitarLedgerQuery.vue'),
        },
{
          path: 'projects/:projectId/adjustments',
          name: 'Adjustments',
          // CITAR「调整分录」（接平台调整分录与复核流程）；原页面 @/views/Adjustments.vue
          component: () => import('@/citar/screens/CitarAdjustment.vue'),
        },
{
          // 平台暂无对应功能的三个菜单：CITAR 待开发页
          path: 'projects/:projectId/report-analysis',
          name: 'CitarReportAnalysis',
          component: () => import('@/citar/CitarPendingNode.vue'),
          meta: { citarTitle: '报表分析' },
        },
{
          path: 'projects/:projectId/tax-return',
          name: 'CitarTaxReturn',
          component: () => import('@/citar/CitarPendingNode.vue'),
          meta: { citarTitle: '纳税申报表' },
        },
{
          path: 'projects/:projectId/materiality',
          name: 'Materiality',
          component: () => import('@/views/Materiality.vue'),
        },
{
          path: 'projects/:projectId/misstatements',
          name: 'Misstatements',
          component: () => import('@/views/Misstatements.vue'),
        },
{
          path: 'projects/:projectId/audit-checks',
          name: 'AuditCheckDashboard',
          component: () => import('@/views/AuditCheckDashboard.vue'),
        },
{
          path: 'projects/:projectId/cfs-worksheet',
          name: 'CFSWorksheet',
          component: () => import('@/views/CFSWorksheet.vue'),
        },
{
          path: 'projects/:projectId/settings',
          name: 'ProjectSettingsCenter',
          component: () => import('@/views/ProjectSettingsCenter.vue'),
        },
{
          // ACNR 地址坐标名称库 — 项目级 overlay（sheet 别名/绑定/补丁）管理
          path: 'projects/:projectId/acnr-overlays',
          name: 'AcnrOverlayManager',
          component: () => import('@/views/AcnrOverlayManager.vue'),
          meta: { permission: 'project:view' },
        },
{
          path: 'projects/:projectId/review-inbox',
          name: 'ReviewInbox',
          component: () => import('@/views/ReviewWorkbench.vue'),
        },
{
          path: 'review-inbox',
          name: 'ReviewInboxGlobal',
          component: () => import('@/views/ReviewWorkbench.vue'),
        },
{
          path: 'projects/:projectId/independence',
          name: 'IndependenceDeclaration',
          component: () => import('@/views/independence/IndependenceDeclarationForm.vue'),
        },
{
          path: 'projects/:projectId/archive',
          name: 'ArchiveWizard',
          component: () => import('@/views/ArchiveWizard.vue'),
          meta: { permission: 'archive:execute' },
        },
{
          path: 'projects/:projectId/archive/jobs/:jobId',
          name: 'ArchiveWizardJob',
          component: () => import('@/views/ArchiveWizard.vue'),
          meta: { permission: 'archive:execute' },
        },
{
          path: 'projects/:projectId/progress-board',
          name: 'ProjectProgressBoard',
          component: () => import('@/views/ProjectProgressBoard.vue'),
        },
{
          path: 'projects/:projectId/task-tree',
          name: 'TaskTreeView',
          component: () => import('@/views/TaskTreeView.vue'),
        },
{
          path: 'projects/:projectId/issues',
          name: 'IssueTicketList',
          component: () => import('@/views/IssueTicketList.vue'),
        },
{
          path: 'projects/:projectId/offline-conflicts',
          name: 'OfflineConflictWorkbench',
          component: () => import('@/views/OfflineConflictWorkbench.vue'),
        },
{
          path: 'projects/:projectId/mapping',
          name: 'AccountMapping',
          // CITAR「底稿映射」（客户科目 → 标准科目）；原页面 @/views/AccountMappingPage.vue
          component: () => import('@/citar/screens/CitarAccountMapping.vue'),
        },
{
          path: 'projects/:projectId/ledger-import',
          name: 'LedgerImport',
          // CITAR「账套导入」；原页面 @/views/LedgerImportPage.vue
          component: () => import('@/citar/screens/CitarDataImport.vue'),
        },
{
          path: 'projects/:projectId/ledger/import-history',
          name: 'LedgerImportHistory',
          component: () => import('@/views/LedgerImportHistory.vue'),
        },
{
          path: 'projects/:projectId/ledger',
          name: 'LedgerPenetration',
          component: () => import('@/views/LedgerPenetration.vue'),
        },
{
          path: 'projects/:projectId/attachments',
          name: 'AttachmentManagement',
          component: () => import('@/views/AttachmentManagement.vue'),
        },
{
          // 附件·OCR·AI·证据链治理中心
          // [attachment-ocr-ai-evidence-governance-hardening Wave 9 UI 接线]
          path: 'projects/:projectId/evidence-governance',
          name: 'EvidenceGovernanceCenter',
          component: () => import('@/views/EvidenceGovernanceCenter.vue'),
          meta: { permission: 'project:view' },
        },
{
          path: 'projects/:projectId/consolidation',
          name: 'Consolidation',
          component: () => import('@/views/ConsolidationIndex.vue'),
        },
{
          path: 'projects/:projectId/t-accounts',
          name: 'TAccountManagement',
          component: () => import('@/views/extension/TAccountManagement.vue'),
        },
{
          path: 'projects/:projectId/work-hours',
          name: 'ProjectWorkHours',
          component: () => import('@/views/ProjectWorkHoursView.vue'),
        },
{
          path: 'projects/:projectId/consistency',
          name: 'ConsistencyDashboard',
          component: () => import('@/views/ConsistencyDashboard.vue'),
        },
{
          path: 'projects/:projectId/procedures',
          name: 'ProcedureTrimming',
          component: () => import('@/views/ProcedureTrimming.vue'),
        },
{
          path: 'projects/:projectId/subsequent-events',
          name: 'SubsequentEvents',
          component: () => import('@/views/SubsequentEvents.vue'),
        },
{
          path: 'projects/:projectId/collaboration',
          name: 'Collaboration',
          component: () => import('@/views/CollaborationIndex.vue'),
        },
{
          path: 'projects/:projectId/project-dashboard',
          name: 'ProjectDashboard',
          component: () => import('@/views/ProjectDashboard.vue'),
        },
{
          path: 'projects/:projectId/dashboard',
          name: 'PartnerProjectDashboard',
          component: () => import('@/views/PartnerProjectDashboard.vue'),
        },
{
          path: 'projects/:projectId/workbench',
          name: 'RoleWorkbench',
          component: () => import('@/views/RoleWorkbench.vue'),
          meta: { permission: 'project:view' },
        },
{
          path: 'projects/:projectId/linkage-panorama',
          name: 'LinkagePanorama',
          component: () => import('@/views/LinkagePanoramaView.vue'),
          meta: { permission: 'project:view' },
        },
{
          path: 'projects/:projectId/my-reviews',
          name: 'MyReviews',
          component: () => import('@/components/MyReviewsPanel.vue'),
          meta: { permission: 'project:view' },
        },
{
          // 项目入口路由：partner/admin 默认跳转到仪表盘，其他角色跳转到试算表
          path: 'projects/:projectId/entry',
          name: 'ProjectEntry',
          redirect: (to) => {
            const authStore = useAuthStore()
            const role = authStore.user?.role
            const projectId = to.params.projectId as string
            if (role === 'partner' || role === 'admin') {
              return { name: 'PartnerProjectDashboard', params: { projectId } }
            }
            return { name: 'TrialBalance', params: { projectId } }
          },
        },
{
          path: 'projects/:projectId/review-conversations',
          name: 'ReviewConversations',
          component: () => import('@/views/ReviewConversations.vue'),
        },
{
          path: 'projects/:projectId/sampling-enhanced',
          name: 'SamplingEnhanced',
          component: () => import('@/views/SamplingEnhanced.vue'),
        },
{
          path: 'projects/:projectId/aux-summary',
          name: 'AuxSummary',
          component: () => import('@/views/AuxSummaryPanel.vue'),
          meta: { developing: true },
        },
{
          path: 'projects/:projectId/consol-snapshots',
          name: 'ConsolSnapshots',
          component: () => import('@/views/ConsolSnapshots.vue'),
          meta: { developing: true },
        },
{
          path: 'projects/:projectId/data-validation',
          name: 'DataValidation',
          component: () => import('@/views/DataValidationPanel.vue'),
          props: (route: any) => ({ projectId: route.params.projectId }),
        }
]
