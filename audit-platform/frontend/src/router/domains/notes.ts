import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: notes
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const notesRoutes: RouteRecordRaw[] = [
{
          path: 'projects/:projectId/disclosure-notes',
          name: 'DisclosureNotes',
          // 路由壳：年度定不下来（项目没填审计年度）时不挂附注编辑页（post-push-residual-defect-closure 6.5）
          component: () => import('@/views/DisclosureEditorRoute.vue'),
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
