import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

/**
 * 角色→权限映射表（前端硬编码，作为后端权限列表不可用时的兜底）
 * 优先使用 authStore.user.permissions（从 /api/users/me 获取），防止前后端权限表不同步。
 * 导出供 v-permission 指令和 router 守卫直接使用，避免在非 setup 上下文调用 usePermission()
 */
export const ROLE_PERMISSIONS: Record<string, string[]> = {
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
 * 优先使用后端下发的 user.permissions 列表（/api/users/me 返回），
 * 后端列表不可用时回退到前端硬编码的 ROLE_PERMISSIONS。
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

  /** 获取当前用户的权限列表（优先后端，回退前端硬编码） */
  function getPermissions(): string[] {
    const user = authStore.user as any
    // 后端 /api/users/me 返回 permissions 字段时优先使用
    if (user?.permissions && Array.isArray(user.permissions) && user.permissions.length > 0) {
      return user.permissions
    }
    // 回退：前端硬编码
    return ROLE_PERMISSIONS[role.value] ?? []
  }

  /**
   * 检查当前用户是否拥有指定权限
   * - admin 角色拥有所有权限
   * - 'admin' 权限字符串仅 admin 角色通过
   */
  function can(permission: string): boolean {
    const r = role.value
    if (!r) return false
    if (r === 'admin') return true
    if (permission === 'admin') return false
    return getPermissions().includes(permission)
  }

  /**
   * 检查当前用户是否拥有任一权限
   */
  function canAny(...permissions: string[]): boolean {
    return permissions.some((p) => can(p))
  }

  return { can, canAny, role }
}
