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
          path: 'projects/:projectId/workpapers/:wpId/edit',
          name: 'WorkpaperEditor',
          component: () => import('@/views/WorkpaperEditor.vue'),
        },
{
          // 底稿短链（ACNR jump_route / AI 提及 / 证据治理产出 /workpapers/{id}?sheet=…）：按底稿 id 查项目后重定向到编辑器
          path: 'workpapers/:wpId',
          name: 'WorkpaperShortLink',
          component: () => import('@/views/WorkpaperShortLink.vue'),
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
