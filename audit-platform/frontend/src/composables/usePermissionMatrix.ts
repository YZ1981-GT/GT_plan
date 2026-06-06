/**
 * usePermissionMatrix — 统一权限矩阵 composable (MVP)
 *
 * 与后端 permission_matrix_service.py 保持同一份操作 code 定义。
 * 提供 can() / whyCannot() 作为前端按钮显隐和操作可用性的单一判断入口。
 *
 * MVP 阶段使用静态映射（镜像后端 7 个 operation code + 6 角色），
 * 后续 P0 阶段接入 API 动态加载。
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

/**
 * 标准化角色名（兼容旧别名）
 */
function normalizeRole(role: string): string {
  const r = role.toLowerCase().trim()
  if (r === 'assistant') return 'auditor'
  if (r === 'quality_control') return 'qc'
  return r
}

/**
 * 权限矩阵 composable
 */
export function usePermissionMatrix() {
  const authStore = useAuthStore()

  const currentRole = computed(() => normalizeRole(authStore.user?.role ?? ''))

  const allowedOperations = computed(() => {
    return ROLE_OPERATIONS[currentRole.value] ?? new Set<string>()
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

    return `角色 ${currentRole.value} 无 ${operationCode} 权限`
  }

  return {
    can,
    whyCannot,
    currentRole,
    allowedOperations,
  }
}
