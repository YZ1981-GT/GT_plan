import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

/**
 * 角色→权限映射表
 * admin 拥有所有权限（在 can() 中直接放行）
 */
const ROLE_PERMISSIONS: Record<string, string[]> = {
  partner: [
    'project:view', 'project:edit', 'project:create', 'project:delete',
    'adjustment:view', 'adjustment:edit', 'adjustment:create', 'adjustment:delete',
    'adjustment:review',
    'report:view', 'report:edit', 'report:export',
    'workpaper:view', 'workpaper:edit',
    'user:view',
  ],
  manager: [
    'project:view', 'project:edit', 'project:create',
    'adjustment:view', 'adjustment:edit', 'adjustment:create', 'adjustment:delete',
    'adjustment:review',
    'report:view', 'report:edit', 'report:export',
    'workpaper:view', 'workpaper:edit',
  ],
  auditor: [
    'project:view',
    'adjustment:view', 'adjustment:edit', 'adjustment:create',
    'report:view',
    'workpaper:view', 'workpaper:edit',
  ],
}

/**
 * 权限检查 composable
 *
 * @example
 * ```ts
 * const { can, canAny } = usePermission()
 * if (can('adjustment:delete')) { ... }
 * if (canAny('project:edit', 'project:create')) { ... }
 * ```
 */
export function usePermission() {
  const authStore = useAuthStore()

  const role = computed(() => authStore.user?.role ?? '')

  /**
   * 检查当前用户是否拥有指定权限
   * - admin 角色拥有所有权限
   * - 'admin' 权限字符串仅 admin 角色通过
   */
  function can(permission: string): boolean {
    const r = role.value
    if (!r) return false
    // admin 角色拥有所有权限
    if (r === 'admin') return true
    // 'admin' 权限仅 admin 角色可通过
    if (permission === 'admin') return false
    const perms = ROLE_PERMISSIONS[r]
    return perms ? perms.includes(permission) : false
  }

  /**
   * 检查当前用户是否拥有任一权限
   */
  function canAny(...permissions: string[]): boolean {
    return permissions.some((p) => can(p))
  }

  return { can, canAny, role }
}
