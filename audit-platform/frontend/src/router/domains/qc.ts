import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: qc
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const qcRoutes: RouteRecordRaw[] = [
{
          path: 'projects/:projectId/qc-dashboard',
          name: 'QCDashboard',
          component: () => import('@/views/QCDashboard.vue'),
          meta: { permission: 'qc:initiate' },
        },
{
          path: 'eqcr/workbench',
          name: 'EqcrWorkbench',
          component: () => import('@/views/eqcr/EqcrWorkbench.vue'),
          meta: { requiresAnnualDeclaration: true },
        },
{
          // Round 5 Task 6：EQCR 项目详情视图（5 判断 Tab）
          // 访问控制同 EqcrWorkbench：仅 requireAuth；后端按
          // ProjectAssignment.role='eqcr' 过滤，非 EQCR 用户 overview 返回
          // my_role_confirmed=false，UI 走"只读模式"提示并禁用意见录入。
          path: 'eqcr/projects/:projectId',
          name: 'EqcrProjectView',
          component: () => import('@/views/eqcr/EqcrProjectView.vue'),
          meta: { requiresAnnualDeclaration: true },
        },
{
          // Round 5 Task 20：EQCR 指标仪表盘
          // 权限：admin 或 role='partner' 且被分配为某项目的 qc；
          // 前端路由守卫只做粗筛 admin/partner，真实数据由后端端点进一步控制
          path: 'eqcr/metrics',
          name: 'EqcrMetrics',
          component: () => import('@/views/eqcr/EqcrMetrics.vue'),
          meta: { requiresAnnualDeclaration: true, permission: 'view_eqcr' },
        },
{
          path: 'qc/rules',
          name: 'QcRuleList',
          component: () => import('@/views/qc/QcRuleList.vue'),
          meta: { permission: 'qc:initiate' },
        },
{
          path: 'qc/rules/:ruleId/edit',
          name: 'QcRuleEditor',
          component: () => import('@/views/qc/QcRuleEditor.vue'),
          meta: { permission: 'qc:initiate' },
        },
{
          path: 'qc',
          redirect: '/qc/inspections',
        },
{
          path: 'qc/inspections',
          name: 'QcInspectionWorkbench',
          component: () => import('@/views/qc/QcInspectionWorkbench.vue'),
          meta: { permission: 'qc:initiate' },
        },
{
          path: 'qc/clients/:clientName/trend',
          name: 'ClientQualityTrend',
          component: () => import('@/views/qc/ClientQualityTrend.vue'),
          meta: { permission: 'qc:initiate' },
        },
{
          path: 'qc/cases',
          name: 'QcCaseLibrary',
          component: () => import('@/views/qc/QcCaseLibrary.vue'),
          meta: { permission: 'qc:initiate' },
        },
{
          path: 'qc/annual-reports',
          name: 'QcAnnualReports',
          component: () => import('@/views/qc/QcAnnualReports.vue'),
          meta: { permission: 'qc:initiate' },
        }
]
