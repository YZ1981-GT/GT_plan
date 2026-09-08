import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: notes
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const notesRoutes: RouteRecordRaw[] = [
{
          path: 'projects/:projectId/disclosure-notes',
          name: 'DisclosureNotes',
          component: () => import('@/views/DisclosureEditor.vue'),
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
