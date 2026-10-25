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
          // 与 ':id/edit' 的先后顺序无关：vue-router 4 按路径特异性打分匹配，
          // 静态段优先于动态段（变异实测两种顺序均解析到本路由）。
          // spec: custom-workpaper-template-ingestion-and-sync-closure Task 12
          path: 'extension/custom-templates/ingest',
          name: 'CustomIngestionWizard',
          component: () => import('@/views/extension/CustomIngestionWizard.vue'),
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
