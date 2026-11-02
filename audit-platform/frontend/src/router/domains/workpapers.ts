import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: workpapers
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const workpapersRoutes: RouteRecordRaw[] = [
{
          path: 'projects/:projectId/workpapers',
          name: 'WorkpaperList',
          component: () => import(/* webpackPrefetch: true */ '@/views/WorkpaperList.vue'),
        },
{
          // 税审底稿（项目侧栏「税审底稿」）：目录在布局层二级栏，`?sheet=` 指定当前表。
          // 🔴 与上面的 WorkpaperList（财报审计底稿）是两套底稿，不要合并。
          path: 'projects/:projectId/tax-workpapers',
          name: 'TaxWorkpapers',
          component: () => import('@/views/TaxWorkpaperPage.vue'),
          meta: { permission: 'project:view' },
        },
{
          path: 'projects/:projectId/workpapers/:wpId/edit',
          name: 'WorkpaperEditor',
          component: () => import('@/views/WorkpaperEditor.vue'),
        },
{
          path: 'projects/:projectId/account-packages/:packageId',
          name: 'AccountPackage',
          component: () => import('@/views/AccountPackageView.vue'),
        },
{
          path: 'projects/:projectId/workpaper-bench',
          name: 'WorkpaperWorkbench',
          redirect: (to) => ({
            name: 'WorkpaperList',
            params: { projectId: to.params.projectId },
            query: { view: 'workbench' },
          }),
        },
{
          path: 'projects/:projectId/templates',
          name: 'TemplateManager',
          component: () => import('@/views/TemplateManager.vue'),
        },
{
          path: 'projects/:projectId/workpaper-summary',
          name: 'WorkpaperSummary',
          component: () => import('@/views/WorkpaperSummary.vue'),
        }
]
