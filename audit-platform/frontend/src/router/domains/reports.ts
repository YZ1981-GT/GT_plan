import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: reports
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const reportsRoutes: RouteRecordRaw[] = [
{
          path: 'projects/:projectId/reports',
          name: 'Reports',
          component: () => import(/* webpackPrefetch: true */ '@/views/ReportView.vue'),
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
          // 税审报告（鉴证报告组）：企业所得税年度纳税申报审核报告正文。
          // 🔴 与上面的 AuditReport（财报审计报告编辑器）是两份不同的文书，不要合并。
          path: 'projects/:projectId/tax-audit-report',
          name: 'TaxAuditReport',
          component: () => import('@/views/TaxAuditReportPage.vue'),
          meta: { permission: 'project:view' },
        },
{
          // 纳税申报表（鉴证报告组）：占位页，入口已就位、表单结构待定义。
          // 与 AuditReport 同属鉴证报告组，故放在本域、紧挨其后。
          path: 'projects/:projectId/tax-return',
          name: 'TaxReturn',
          component: () => import('@/views/TaxReturnPage.vue'),
          meta: { permission: 'project:view' },
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
