import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: reports
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const reportsRoutes: RouteRecordRaw[] = [
{
          path: 'projects/:projectId/reports',
          name: 'Reports',
          // 税审 demo：CITAR「审定报表」（资产负债表 / 利润表，接平台报表生成）；原页面 @/views/ReportView.vue
          component: () => import('@/citar/screens/CitarAuditedReports.vue'),
        },
{
          path: 'projects/:projectId/report-config',
          name: 'ReportConfigEditor',
          component: () => import('@/views/ReportConfigEditor.vue'),
        },
{
          path: 'projects/:projectId/report-config-baseline',
          name: 'ReportConfigBaseline',
          component: () => import('@/views/ReportConfigBaselineTab.vue'),
        },
{
          path: 'projects/:projectId/audit-report',
          name: 'AuditReport',
          component: () => import('@/views/AuditReportEditor.vue'),
        },
{
          path: 'projects/:projectId/deliverable-center',
          name: 'DeliverableCenter',
          component: () => import('@/views/DeliverableCenter.vue'),
        },
{
          path: 'projects/:projectId/pdf-export',
          name: 'PDFExport',
          component: () => import('@/views/PDFExportPanel.vue'),
        },
{
          path: 'projects/:projectId/report-trace',
          name: 'ReportTrace',
          component: () => import('@/views/ReportTracePanel.vue'),
        },
{
          path: 'settings/report-format',
          name: 'ReportFormatManager',
          component: () => import('@/views/ReportFormatManager.vue'),
          meta: { developing: true },
        }
]
