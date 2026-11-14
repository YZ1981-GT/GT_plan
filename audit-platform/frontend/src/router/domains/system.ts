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
          path: 'settings/users',
          name: 'UserManagement',
          component: () => import('@/views/UserManagement.vue'),
          meta: { permission: 'admin' },
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
          // spec platform-global-display-settings-closure 任务 5 / AC-07：
          // 显示偏好是**每个登录用户**都要能改的（字号 / 密度 / 单位 / 固定列），
          // 所以不能挂在只有 admin 能进的 `settings` 下。这里不设 permission 门控，
          // 系统配置仍留在 admin 门内。普通用户的设置入口只指向本页。
          path: 'display-settings',
          name: 'DisplaySettings',
          component: () => import('@/views/DisplaySettingsView.vue'),
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
