import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: system
 * Explicit RouteRecordRaw[] — children of DefaultLayout.
 */
export const systemRoutes: RouteRecordRaw[] = [
{
          path: 'settings/ai-models',
          name: 'AIModelConfig',
          component: () => import('@/views/AIModelConfig.vue'),
          meta: { permission: 'admin' },
        },
{
          // 全局公式设置 / 发布记录 / 公式模板（spec formula-global-settings-sync）：
          // 不设 admin 门控 —— 非管理员只读查看全局定义，并管理自己可见的公式模板；写操作由后端判权
          path: 'settings/formula-global',
          name: 'FormulaGlobalSettings',
          component: () => import('@/views/FormulaGlobalSettings.vue'),
        },
{
          path: 'recycle-bin',
          name: 'RecycleBin',
          component: () => import('@/views/RecycleBin.vue'),
        },
{
          path: 'settings/staff',
          name: 'StaffManagement',
          component: () => import('@/views/StaffManagement.vue'),
        },
{
          path: 'work-hours',
          name: 'WorkHours',
          component: () => import('@/views/WorkHoursPage.vue'),
        },
{
          path: 'archive',
          name: 'ArchiveIndex',
          component: () => import('@/views/ArchiveIndex.vue'),
        },
{
          path: 'partner/sign-decision/:projectId/:year',
          name: 'PartnerSignDecision',
          component: () => import('@/views/PartnerSignDecision.vue'),
          meta: { permission: 'sign:execute' },
        },
{
          // （spec nav-grouping-and-permission-center Task 5.2）
          path: 'settings/permissions',
          name: 'PermissionCenter',
          component: () => import('@/views/PermissionCenter.vue'),
          meta: { permission: 'admin' },
        },
        // 旧路径保留为重定向：书签与外链继续可用，落到合并后的「账号权限」Tab。
        {
          path: 'settings/users',
          name: 'UserManagement',
          redirect: { name: 'PermissionCenter', query: { tab: 'users' } },
        },
{
          path: 'private-storage',
          name: 'PrivateStorage',
          component: () => import('@/views/PrivateStorage.vue'),
        },
{
          path: 'forum',
          name: 'Forum',
          component: () => import('@/views/ForumPage.vue'),
        },
{
          path: 'settings',
          name: 'SystemSettings',
          component: () => import('@/views/SystemSettings.vue'),
          meta: { permission: 'admin' },
        },
{
          path: 'consolidation',
          name: 'ConsolidationHub',
          component: () => import('@/views/ConsolidationHub.vue'),
        },
{
          path: 'attachments',
          name: 'AttachmentHub',
          component: () => import('@/views/AttachmentHub.vue'),
        },
{
          path: 'staff/:staffId/check-ins',
          name: 'CheckIns',
          component: () => import('@/views/CheckInsPage.vue'),
          meta: { developing: true },
        },
{
          path: 'admin/performance',
          name: 'PerformanceMonitor',
          component: () => import('@/views/PerformanceMonitor.vue'),
          meta: { permission: 'admin' },
        },
{
          path: 'ledger-import/validation-rules',
          name: 'ValidationRules',
          component: () => import('@/views/ValidationRules.vue'),
        },
{
          path: 'admin/event-dlq',
          name: 'EventDLQ',
          component: () => import('@/views/admin/EventDLQ.vue'),
          meta: { permission: 'admin' },
        }
]
