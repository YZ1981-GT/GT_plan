import { createRouter, createWebHistory } from 'vue-router'
import NProgress from 'nprogress'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { usePermission } from '@/composables/usePermission'

// NProgress 配置：不显示旋转图标，与 GT 紫色主题一致
NProgress.configure({ showSpinner: false })

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('@/views/Register.vue'),
    },
    {
      path: '/',
      component: () => import('@/layouts/DefaultLayout.vue'),
      meta: { requireAuth: true },
      children: [
        {
          path: '',
          name: 'Dashboard',
          component: () => import(/* webpackPrefetch: true */ '@/views/Dashboard.vue'),
        },
        {
          path: 'projects',
          name: 'Projects',
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
          component: () => import(/* webpackPrefetch: true */ '@/views/TrialBalance.vue'),
        },
        {
          path: 'projects/:projectId/adjustments',
          name: 'Adjustments',
          component: () => import('@/views/Adjustments.vue'),
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
          path: 'projects/:projectId/reports',
          name: 'Reports',
          component: () => import(/* webpackPrefetch: true */ '@/views/ReportView.vue'),
        },
        {
          path: 'projects/:projectId/report-config',
          name: 'ReportConfigEditor',
          component: () => import('@/views/ReportConfigEditor.vue'),
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
          path: 'projects/:projectId/disclosure-notes',
          name: 'DisclosureNotes',
          component: () => import('@/views/DisclosureEditor.vue'),
        },
        {
          path: 'projects/:projectId/audit-report',
          name: 'AuditReport',
          component: () => import('@/views/AuditReportEditor.vue'),
        },
        {
          path: 'projects/:projectId/pdf-export',
          name: 'PDFExport',
          component: () => import('@/views/PDFExportPanel.vue'),
        },
        {
          path: 'projects/:projectId/workpapers',
          name: 'WorkpaperList',
          component: () => import(/* webpackPrefetch: true */ '@/views/WorkpaperList.vue'),
        },
        {
          path: 'projects/:projectId/workpapers/:wpId/edit',
          name: 'WorkpaperEditor',
          component: () => import('@/views/WorkpaperEditor.vue'),
        },
        {
          path: 'projects/:projectId/workpaper-bench',
          name: 'WorkpaperWorkbench',
          component: () => import('@/views/WorkpaperWorkbench.vue'),
        },
        {
          path: 'projects/:projectId/review-inbox',
          name: 'ReviewInbox',
          component: () => import('@/views/ReviewInbox.vue'),
        },
        {
          path: 'projects/:projectId/qc-dashboard',
          name: 'QCDashboard',
          component: () => import('@/views/QCDashboard.vue'),
        },
        {
          path: 'projects/:projectId/progress-board',
          name: 'ProjectProgressBoard',
          component: () => import('@/views/ProjectProgressBoard.vue'),
        },
        {
          path: 'projects/:projectId/templates',
          name: 'TemplateManager',
          component: () => import('@/views/TemplateManager.vue'),
        },
        // Phase 15: 任务树与问题单
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
        // Phase 16: 离线冲突工作台
        {
          path: 'projects/:projectId/offline-conflicts',
          name: 'OfflineConflictWorkbench',
          component: () => import('@/views/OfflineConflictWorkbench.vue'),
        },
        {
          path: 'projects/:projectId/ledger',
          name: 'LedgerPenetration',
          component: () => import('@/views/LedgerPenetration.vue'),
        },
        {
          path: 'projects/:projectId/ledger/import-history',
          name: 'LedgerImportHistory',
          component: () => import('@/views/LedgerImportHistory.vue'),
        },
        {
          path: 'projects/:projectId/attachments',
          name: 'AttachmentManagement',
          component: () => import('@/views/AttachmentManagement.vue'),
        },
        {
          path: 'projects/:projectId/consolidation',
          name: 'Consolidation',
          component: () => import('@/views/ConsolidationIndex.vue'),
        },
        {
          path: 'projects/:projectId/workpaper-summary',
          name: 'WorkpaperSummary',
          component: () => import('@/views/WorkpaperSummary.vue'),
        },
        // ── AIChatView / AIWorkpaperView routes removed (Phase 11) ──
        // Backend endpoints (POST /api/ai/chat, POST /api/ai/chat/file-analysis,
        // GET /api/projects/{id}/chat/history) are not registered in router_registry.py,
        // so all operations return 404. Do NOT re-add these routes.

        // ── Phase 8 Extension Routes ──
        {
          path: 'projects/:projectId/t-accounts',
          name: 'TAccountManagement',
          component: () => import('@/views/extension/TAccountManagement.vue'),
        },
        {
          path: 'extension/custom-templates',
          name: 'CustomTemplateList',
          component: () => import('@/views/extension/CustomTemplateList.vue'),
        },
        {
          path: 'extension/custom-templates/new',
          name: 'CustomTemplateNew',
          component: () => import('@/views/extension/CustomTemplateEditor.vue'),
        },
        {
          path: 'extension/custom-templates/:id/edit',
          name: 'CustomTemplateEdit',
          component: () => import('@/views/extension/CustomTemplateEditor.vue'),
        },
        {
          path: 'extension/template-market',
          name: 'TemplateMarket',
          component: () => import('@/views/extension/TemplateMarket.vue'),
        },
        {
          path: 'extension/signatures',
          name: 'SignatureManagement',
          component: () => import('@/views/extension/SignatureManagement.vue'),
        },
        {
          path: 'extension/regulatory',
          name: 'RegulatoryFiling',
          component: () => import('@/views/extension/RegulatoryFiling.vue'),
        },
        {
          path: 'extension/gt-coding',
          name: 'GTCodingSystem',
          component: () => import('@/views/extension/GTCodingSystem.vue'),
        },
        {
          path: 'extension/ai-plugins',
          name: 'AIPluginManagement',
          component: () => import('@/views/extension/AIPluginManagement.vue'),
        },
        {
          path: 'settings/ai-models',
          name: 'AIModelConfig',
          component: () => import('@/views/AIModelConfig.vue'),
        },
        {
          path: 'recycle-bin',
          name: 'RecycleBin',
          component: () => import('@/views/RecycleBin.vue'),
        },
        // ── Phase 9 Routes ──
        {
          path: 'settings/staff',
          name: 'StaffManagement',
          component: () => import('@/views/StaffManagement.vue'),
        },
        {
          path: 'work-hours',
          name: 'WorkHours',
          component: () => import('@/views/WorkHoursPage.vue'),
        },
        {
          path: 'dashboard/management',
          name: 'ManagementDashboard',
          component: () => import('@/views/ManagementDashboard.vue'),
        },
        {
          path: 'dashboard/partner',
          name: 'PartnerDashboard',
          component: () => import('@/views/PartnerDashboard.vue'),
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
          path: 'settings/users',
          name: 'UserManagement',
          component: () => import('@/views/UserManagement.vue'),
          meta: { permission: 'admin' },
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
          path: 'my/dashboard',
          name: 'PersonalDashboard',
          component: () => import('@/views/PersonalDashboard.vue'),
        },
        {
          path: 'my-procedures',
          name: 'MyProcedureTasks',
          component: () => import('@/views/MyProcedureTasks.vue'),
        },
        // ── Phase 10 Routes ──
        {
          path: 'private-storage',
          name: 'PrivateStorage',
          component: () => import('@/views/PrivateStorage.vue'),
        },
        {
          path: 'forum',
          name: 'Forum',
          component: () => import('@/views/ForumPage.vue'),
        },
        {
          path: 'projects/:projectId/review-conversations',
          name: 'ReviewConversations',
          component: () => import('@/views/ReviewConversations.vue'),
        },
        {
          path: 'projects/:projectId/annotations',
          name: 'Annotations',
          component: () => import('@/views/AnnotationsPanel.vue'),
        },
        {
          path: 'projects/:projectId/report-trace',
          name: 'ReportTrace',
          component: () => import('@/views/ReportTracePanel.vue'),
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
          path: 'settings/report-format',
          name: 'ReportFormatManager',
          component: () => import('@/views/ReportFormatManager.vue'),
          meta: { developing: true },
        },
        {
          path: 'settings',
          name: 'SystemSettings',
          component: () => import('@/views/SystemSettings.vue'),
        },
        {
          path: 'knowledge',
          name: 'KnowledgeBase',
          component: () => import('@/views/KnowledgeBase.vue'),
        },
        {
          path: 'consolidation',
          name: 'ConsolidationHub',
          component: () => import('@/views/ConsolidationHub.vue'),
        },
        {
          path: 'attachments',
          name: 'AttachmentHub',
          component: () => import('@/views/AttachmentHub.vue'),
        },
        {
          path: 'staff/:staffId/check-ins',
          name: 'CheckIns',
          component: () => import('@/views/CheckInsPage.vue'),
          meta: { developing: true },
        },
        // ── Phase 8 Routes ──
        {
          path: 'projects/:projectId/data-validation',
          name: 'DataValidation',
          component: () => import('@/views/DataValidationPanel.vue'),
          props: (route: any) => ({ projectId: route.params.projectId }),
        },
        {
          path: 'admin/performance',
          name: 'PerformanceMonitor',
          component: () => import('@/views/PerformanceMonitor.vue'),
          meta: { permission: 'admin' },
        },
        // ── Mobile Routes ──
        {
          path: 'projects/:projectId/mobile-penetration',
          name: 'MobilePenetration',
          component: () => import('@/views/MobilePenetration.vue'),
          meta: { developing: true },
          props: (route: any) => ({ projectId: route.params.projectId }),
        },
        {
          path: 'projects/:projectId/mobile-review',
          name: 'MobileReviewView',
          component: () => import('@/views/MobileReviewView.vue'),
          meta: { developing: true },
          props: (route: any) => ({ projectId: route.params.projectId }),
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('@/views/NotFound.vue'),
    },
  ],
})

// ─── 统一路由守卫 [R7.1] ───
// 职责：① 开发中页面拦截 ② 认证守卫 ③ 权限守卫 ④ 项目上下文自动加载
// 注意：未保存变更拦截由 useEditMode 的 onBeforeRouteLeave 在组件级处理，
//       router 级 beforeEach 不重复拦截，也不会干扰组件级守卫。
router.beforeEach(async (to) => {
  NProgress.start()
  const authStore = useAuthStore()

  // ① 开发中页面 → 提示并阻止导航
  if (to.meta.developing) {
    import('element-plus').then(({ ElMessage }) => {
      ElMessage.info('该功能正在开发中，敬请期待')
    })
    NProgress.done()
    return false
  }

  // ② 已登录用户访问 /login → 重定向到首页
  if (to.path === '/login' && authStore.isAuthenticated) {
    return { path: '/' }
  }

  // ③ 认证守卫：需要登录但未认证 → 重定向到登录页
  if (to.matched.some((r) => r.meta.requireAuth) && !authStore.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // ④ 权限守卫：检查路由级 meta.permission
  const permissionRequired = to.meta.permission
  if (permissionRequired && authStore.isAuthenticated) {
    const { can } = usePermission()
    if (!can(permissionRequired)) {
      import('element-plus').then(({ ElMessage }) => {
        ElMessage.warning('您没有访问该页面的权限')
      })
      NProgress.done()
      return { path: '/' }
    }
  }

  // ⑤ 项目上下文自动加载：路由含 :projectId 时同步到 projectStore
  //    DefaultLayout 的 watch 仍保留作为备份，此处提前触发确保数据就绪
  if (to.params.projectId && authStore.isAuthenticated) {
    const projectStore = useProjectStore()
    // 使用 await 确保项目信息在页面渲染前就绪
    await projectStore.syncFromRoute(to as any)
  }
})

// ─── afterEach：结束进度条 ───
router.afterEach(() => {
  NProgress.done()
})

export default router
