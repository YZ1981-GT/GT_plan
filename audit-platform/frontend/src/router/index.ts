import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
    },
    {
      path: '/',
      component: () => import('@/layouts/DefaultLayout.vue'),
      meta: { requireAuth: true },
      children: [
        {
          path: '',
          name: 'Dashboard',
          component: () => import('@/views/Dashboard.vue'),
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
          path: 'poc',
          name: 'WopiPoc',
          component: () => import('@/views/WopiPoc.vue'),
        },
        {
          path: 'projects/:projectId/drilldown',
          name: 'Drilldown',
          component: () => import('@/views/Drilldown.vue'),
        },
        {
          path: 'projects/:projectId/trial-balance',
          name: 'TrialBalance',
          component: () => import('@/views/TrialBalance.vue'),
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
          component: () => import('@/views/ReportView.vue'),
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
          component: () => import('@/views/WorkpaperList.vue'),
        },
        {
          path: 'projects/:projectId/workpapers/:wpId/edit',
          name: 'WorkpaperEditor',
          component: () => import('@/views/WorkpaperEditor.vue'),
        },
        {
          path: 'projects/:projectId/consolidation',
          name: 'Consolidation',
          component: () => import('@/views/ConsolidationIndex.vue'),
        },
        {
          path: 'projects/:projectId/collaboration',
          name: 'Collaboration',
          component: () => import('@/views/CollaborationIndex.vue'),
        },
        {
          path: 'projects/:projectId/templates',
          name: 'TemplateManager',
          component: () => import('@/views/TemplateManager.vue'),
        },
        { path: 'projects/:projectId/dashboard', name: 'ProjectDashboard', component: () => import('@/views/Dashboard.vue') },
        { path: 'users', name: 'UserManagement', component: () => import('@/views/UserManagement.vue'), meta: { roles: ['admin'] } },

        // AI 模块路由
        { path: 'ai/chat', name: 'AIChat', component: () => import('@/components/ai/AIChatPanel.vue') },
        { path: 'ai/workpaper/:id', name: 'AIWorkpaperFill', component: () => import('@/components/ai/WorkpaperAIFill.vue') },
        { path: 'projects/:projectId/ai/documents', name: 'AIDocuments', component: () => import('@/components/ai/DocumentOCRPanel.vue') },
        { path: 'projects/:projectId/ai/contracts', name: 'AIContracts', component: () => import('@/components/ai/ContractAnalysisPanel.vue') },
        { path: 'projects/:projectId/ai/evidence', name: 'AIEvidenceChain', component: () => import('@/components/ai/EvidenceChainPanel.vue') },
        { path: 'projects/:projectId/ai/knowledge', name: 'AIKnowledge', component: () => import('@/components/ai/KnowledgeBasePanel.vue') },
        { path: 'projects/:projectId/ai/content', name: 'AIContentDashboard', component: () => import('@/components/ai/AIContentDashboard.vue') },
        { path: 'projects/:projectId/ai/confirmations', name: 'AIConfirmations', component: () => import('@/components/ai/ConfirmationAIPanel.vue') },
        { path: 'ai/insights', name: 'AIInsights', component: () => import('@/components/ai/AIInsightsDashboard.vue') },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('@/views/NotFound.vue'),
    },
  ],
})

// Helper: check if token is expired based on JWT exp claim
function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    if (!payload.exp) return false
    return Date.now() >= payload.exp * 1000
  } catch {
    return false
  }
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  // Already logged in → redirect away from login
  if (to.path === '/login' && authStore.isAuthenticated) {
    return { path: '/' }
  }

  // Requires auth but not logged in → redirect to login
  if (to.matched.some((r) => r.meta.requireAuth) && !authStore.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // Token expiry check
  if (authStore.isAuthenticated && authStore.token && isTokenExpired(authStore.token)) {
    try {
      await authStore.refreshAccessToken()
    } catch {
      authStore.logout()
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  // Role-based access control
  const requiredRoles = to.meta.roles as string[] | undefined
  if (requiredRoles && requiredRoles.length > 0) {
    const userRole = authStore.user?.role
    if (!userRole || !requiredRoles.includes(userRole)) {
      return { path: '/', query: { error: 'unauthorized' } }
    }
  }
})

export default router
