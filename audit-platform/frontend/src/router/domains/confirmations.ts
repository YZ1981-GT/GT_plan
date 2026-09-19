import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: confirmations
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const confirmationsRoutes: RouteRecordRaw[] = [
{
          path: 'confirmation',
          name: 'ConfirmationIndex',
          component: () => import('@/views/ConfirmationIndex.vue'),
        },
{
          path: 'projects/:projectId/confirmation',
          name: 'ConfirmationHub',
          component: () => import('@/views/ConfirmationHub.vue'),
        }
]
