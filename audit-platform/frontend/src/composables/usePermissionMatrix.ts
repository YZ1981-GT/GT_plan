/**
 * usePermissionMatrix — 统一权限矩阵 composable (P0-5)
 *
 * 与后端 permission_matrix_service.py 保持同一份操作 code 定义。
 * 提供 can() / whyCannot() 作为前端按钮显隐和操作可用性的单一判断入口。
 *
 * P0-5 增强：
 * - 支持项目职责叠加（PROJECT_ROLE_OPERATIONS）
 * - 兼容旧 usePermission 调用模式
 * - 可选传入 projectId 从 store 获取项目角色
 *
 * @example
 * ```ts
 * const { can, whyCannot } = usePermissionMatrix()
 * if (can('wp:edit')) { ... }
 * const reason = whyCannot('report:sign') // "角色 auditor 无 report:sign 权限"
 * ```
 */
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'

// ─── 首批 7 个 Operation Codes（与后端保持一致） ─────────────────────────────
export const OPERATION_CODES = [
  'project:view',
  'wp:edit',
  'wp:review',
  'report:edit',
  'report:sign',
  'note:edit',
  'archive:manage',
] as const

export type OperationCode = (typeof OPERATION_CODES)[number]

// ─── 系统角色 → 允许操作映射（镜像后端 ROLE_OPERATIONS） ─────────────────────
const ROLE_OPERATIONS: Record<string, Set<string>> = {
  admin: new Set(OPERATION_CODES),
  partner: new Set([
    'project:view',
    'wp:edit',
    'wp:review',
    'report:edit',
    'report:sign',
    'note:edit',
    'archive:manage',
  ]),
  manager: new Set([
    'project:view',
    'wp:edit',
    'wp:review',
    'report:edit',
    'note:edit',
  ]),
  auditor: new Set([
    'project:view',
    'wp:edit',
    'note:edit',
  ]),
  qc: new Set([
    'project:view',
    'wp:review',
    'report:edit',
  ]),
  eqcr: new Set([
    'project:view',
    'wp:review',
  ]),
}

// ─── P0-5: 项目职责 → 额外操作映射（镜像后端 PROJECT_ROLE_OPERATIONS） ──────
const PROJECT_ROLE_OPERATIONS: Record<string, Set<string>> = {
  preparer: new Set(['project:view', 'wp:edit', 'note:edit']),
  reviewer: new Set(['project:view', 'wp:review', 'report:edit']),
  manager: new Set(['project:view', 'wp:edit', 'wp:review', 'report:edit', 'note:edit']),
  partner: new Set(OPERATION_CODES),
  eqcr: new Set(['project:view', 'wp:review']),
}

/**
 * 标准化角色名（兼容旧别名）
 */
function normalizeRole(role: string): string {
  const r = role.toLowerCase().trim()
  if (r === 'assistant') return 'auditor'
  if (r === 'quality_control') return 'qc'
  if (r === 'signing_partner') return 'partner'
  return r
}

/**
 * 权限矩阵 composable
 *
 * @param _projectId - 可选，传入时会从项目 store 获取 roleInProject
 */
export function usePermissionMatrix(_projectId?: string) {
  const authStore = useAuthStore()
  const projectStore = useProjectStore()

  const currentRole = computed(() => normalizeRole(authStore.user?.role ?? ''))

  const projectRole = computed(() => {
    const r = projectStore.roleInProject
    return r ? normalizeRole(r) : null
  })

  const allowedOperations = computed(() => {
    const base = ROLE_OPERATIONS[currentRole.value] ?? new Set<string>()
    if (projectRole.value) {
      const extra = PROJECT_ROLE_OPERATIONS[projectRole.value] ?? new Set<string>()
      return new Set([...base, ...extra])
    }
    return base
  })

  /**
   * 判断当前用户是否可以执行指定操作
   */
  function can(operationCode: string): boolean {
    if (!currentRole.value) return false
    if (currentRole.value === 'admin') return true
    return allowedOperations.value.has(operationCode)
  }

  /**
   * 返回不能执行操作的原因，如果可以执行则返回 null
   */
  function whyCannot(operationCode: string): string | null {
    if (can(operationCode)) return null

    if (!currentRole.value) {
      return '未登录，无法执行操作'
    }

    const roleDesc = projectRole.value
      ? `${currentRole.value}(项目职责: ${projectRole.value})`
      : currentRole.value

    return `角色 ${roleDesc} 无 ${operationCode} 权限`
  }

  return {
    can,
    whyCannot,
    currentRole,
    projectRole,
    allowedOperations,
    /** P0-5.3: 兼容旧 usePermission 的 can(roleName) 调用模式 */
    canRole: (roleName: string) => {
      const normalized = normalizeRole(roleName)
      return currentRole.value === normalized || currentRole.value === 'admin'
    },
  }
}
