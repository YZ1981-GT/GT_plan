import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: notes
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const notesRoutes: RouteRecordRaw[] = [
{
          path: 'projects/:projectId/disclosure-notes',
          name: 'DisclosureNotes',
          // 税审 demo：CITAR「税审报告」在 CITAR 里尚未开发，照搬其待开发页；原页面 @/views/DisclosureEditor.vue
          component: () => import('@/citar/CitarPendingNode.vue'),
          meta: { citarTitle: '税审报告' },
        },
{
          path: 'projects/:projectId/annotations',
          name: 'Annotations',
          component: () => import('@/views/AnnotationsPanel.vue'),
        },
{
          path: 'knowledge',
          name: 'KnowledgeBase',
          component: () => import('@/views/KnowledgeBase.vue'),
        }
]
