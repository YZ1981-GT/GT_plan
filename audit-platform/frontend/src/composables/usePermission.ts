import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { normalizeRole, roleIncludes, isPartnerOrAbove, isManagerOrAbove, canDoQC } from '@/utils/roles'

/**
 * 角色→权限映射表（前端硬编码，作为后端权限列表不可用时的兜底）
 *
 * 角色继承铁律（2026-05-20 修复）：
 * - admin > partner > manager > auditor
 * - admin > partner > qc > auditor
 * - partner 必须是 manager 全部权限的 superset
 * - manager 必须是 auditor 全部权限的 superset
 *
 * 优先使用 authStore.user.permissions（从 /api/users/me 获取），防止前后端权限表不同步。
 * 导出供 v-permission 指令和 router 守卫直接使用，避免在非 setup 上下文调用 usePermission()
 */

// auditor 基础权限（最小集）
const AUDITOR_PERMISSIONS = [
  'project:view',
  'adjustment:view', 'adjustment:edit', 'adjustment:create',
  'adjustment:convert_to_misstatement',
  'report:view',
  'workpaper:view', 'workpaper:edit',
  'workpaper:submit_review',
  'independence:edit',
]

// manager 独有权限（manager 不继承的 auditor 权限不写在这里）
const MANAGER_OWN_PERMISSIONS = [
  'project:edit', 'project:create',
  'adjustment:delete', 'adjustment:review',
  'report:edit', 'report:export',
  'workpaper:export',
  'workpaper:review_approve', 'workpaper:review_reject',
  'workpaper:escalate',
  'assignment:batch',
  'template:delete',
  'staff:delete',
  'view_dashboard_manager',
  'approve_workhours',
  'send_reminder',
  'batch_brief',
  'recycle:restore', 'recycle:purge',
  'sampling:execute',
  'report_config:edit',
  'ticket:close',
]

// partner 独有权限
const PARTNER_OWN_PERMISSIONS = [
  'project:delete',
  'report:export_final',
  'sign:execute',
  'archive:execute',
  'user:view',
  'qc:initiate',
]

// qc 独有权限
const QC_OWN_PERMISSIONS = [
  'qc:publish_report',
  'qc:initiate',
  'sampling:execute',
]

// eqcr 独有权限
const EQCR_OWN_PERMISSIONS = [
  'view_eqcr',
  'record_opinion',
  'shadow_compute',
  'approve_eqcr',
  'eqcr:approve',
]

export const ROLE_PERMISSIONS: Record<string, string[]> = {
  // partner = own + manager + auditor (superset)
  partner: [
    ...PARTNER_OWN_PERMISSIONS,
    ...MANAGER_OWN_PERMISSIONS,
    ...AUDITOR_PERMISSIONS,
  ],
  // manager = own + auditor (superset)
  manager: [
    ...MANAGER_OWN_PERMISSIONS,
    ...AUDITOR_PERMISSIONS,
  ],
  // auditor = base
  auditor: [...AUDITOR_PERMISSIONS],
  // R5 任务 2：EQCR 独立复核合伙人
  // 系统级 partner/admin + 项目级 ProjectAssignment.role='eqcr' 双层判断
  // 这里只列项目级 eqcr 独有权限（系统级 partner 权限通过角色继承获得）
  eqcr: [
    ...EQCR_OWN_PERMISSIONS,
    'project:view',
    'workpaper:view',
    'report:view',
    'adjustment:view',
    'independence:edit',
  ],
  // qc = own + auditor (superset)
  qc: [
    ...QC_OWN_PERMISSIONS,
    ...AUDITOR_PERMISSIONS,
    'independence:edit',
  ],
  // 历史别名（向后兼容，请使用 normalizeRole 转换）
  assistant: [...AUDITOR_PERMISSIONS],
  quality_control: [...QC_OWN_PERMISSIONS, ...AUDITOR_PERMISSIONS, 'independence:edit'],
}

/**
 * 权限检查 composable
 *
 * @deprecated 请迁移到 `usePermissionMatrix()`，该 composable 使用统一权限矩阵。
 * `usePermission()` 使用前端硬编码角色映射，与后端权限矩阵可能不同步。
 * 迁移指南：将 `can('project:edit')` 替换为 `usePermissionMatrix().can('wp:edit')` 等操作码。
 *
 * 优先使用后端下发的 user.permissions 列表（/api/users/me 返回），
 * 后端列表不可用时回退到前端硬编码的 ROLE_PERMISSIONS。
 *
 * @example
 * ```ts
 * // ❌ 旧用法（即将移除）
 * const { can, canAny } = usePermission()
 * // ✅ 新用法
 * const { can } = usePermissionMatrix()
 * ```
 */
export function usePermission() {
  if (import.meta.env.DEV) {
    console.warn(
      '[DEPRECATED] usePermission() 已废弃，请迁移到 usePermissionMatrix()。' +
      ' 详见 docs/reference/project-context-migration-inventory.md'
    )
  }
  const authStore = useAuthStore()

  /** 原始角色字符串（可能含别名） */
  const rawRole = computed(() => authStore.user?.role ?? '')

  /** 标准化后的角色（assistant→auditor / quality_control→qc 等） */
  const role = computed(() => normalizeRole(rawRole.value) || rawRole.value)

  /** 获取当前用户的权限列表（优先后端，回退前端硬编码） */
  function getPermissions(): string[] {
    const user = authStore.user as any
    // 后端 /api/users/me 返回 permissions 字段时优先使用
    if (user?.permissions && Array.isArray(user.permissions) && user.permissions.length > 0) {
      return user.permissions
    }
    // 回退：前端硬编码（用标准化后的 role）
    return ROLE_PERMISSIONS[role.value] ?? ROLE_PERMISSIONS[rawRole.value] ?? []
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

  return {
    can,
    canAny,
    role,
    rawRole,
    // 角色继承判断（roles.ts）
    roleIncludes: (target: any) => roleIncludes(role.value, target),
    isPartnerOrAbove: () => isPartnerOrAbove(role.value),
    isManagerOrAbove: () => isManagerOrAbove(role.value),
    canDoQC: () => canDoQC(role.value),
  }
}
