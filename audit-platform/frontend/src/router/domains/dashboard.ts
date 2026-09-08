import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: dashboard
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const dashboardRoutes: RouteRecordRaw[] = [
{
          path: '',
          name: 'Dashboard',
          component: () => import(/* webpackPrefetch: true */ '@/views/Dashboard.vue'),
        },
{
          path: 'dashboard/management',
          name: 'ManagementDashboard',
          component: () => import('@/views/ManagementDashboard.vue'),
        },
{
          path: 'dashboard/manager',
          name: 'ManagerDashboard',
          component: () => import('@/views/ManagerDashboard.vue'),
          meta: { permission: 'view_dashboard_manager' },
        },
{
          path: 'dashboard/partner',
          name: 'PartnerDashboard',
          component: () => import('@/views/PartnerDashboard.vue'),
        },
{
          path: 'my/dashboard',
          name: 'PersonalDashboard',
          component: () => import('@/views/PersonalDashboard.vue'),
        },
{
          path: 'my-procedures',
          name: 'MyProcedureTasks',
          component: () => import('@/views/MyProcedureTasks.vue'),
        }
]
