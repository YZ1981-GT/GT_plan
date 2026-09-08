import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: extension
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const extensionRoutes: RouteRecordRaw[] = [
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
          path: 'template-library',
          name: 'TemplateLibraryMgmt',
          component: () => import('@/views/TemplateLibraryMgmt.vue'),
          meta: { permission: 'project:view' },
        },
{
          path: 'custom-query',
          name: 'CustomQuery',
          component: () => import('@/views/CustomQuery.vue'),
          meta: { permission: 'project:view' },
        }
]
