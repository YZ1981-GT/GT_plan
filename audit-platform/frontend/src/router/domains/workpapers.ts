import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: workpapers
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const workpapersRoutes: RouteRecordRaw[] = [
{
          // 税审 demo：「税务底稿」改用 CITAR 版式（底稿目录 + 紫色横幅 + 页签 + 卡片）。
          // 路由名沿用 WorkpaperList，既有 router.push({ name: 'WorkpaperList' }) 无需改；
          // 原审计底稿管理页 WorkpaperList.vue 保留未删，恢复时把 component 改回即可。
          path: 'projects/:projectId/workpapers',
          name: 'WorkpaperList',
          component: () => import(/* webpackPrefetch: true */ '@/views/tax-workpapers/TaxWorkpaperView.vue'),
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
