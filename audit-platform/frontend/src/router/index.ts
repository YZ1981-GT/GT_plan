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
          path: 'projects/:projectId/templates',
          name: 'TemplateManager',
          component: () => import('@/views/TemplateManager.vue'),
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

router.beforeEach((to) => {
  const authStore = useAuthStore()

  // Already logged in → redirect away from login
  if (to.path === '/login' && authStore.isAuthenticated) {
    return { path: '/' }
  }

  // Requires auth but not logged in → redirect to login
  if (to.matched.some((r) => r.meta.requireAuth) && !authStore.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})

export default router
