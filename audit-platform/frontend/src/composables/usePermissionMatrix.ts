/**
 * usePermissionMatrix — 统一权限矩阵 composable (P0-5 + P2 Req7 增强)
 * Feature: platform-global-hardening
 *
 * 与后端 permission_matrix_service.py 保持同一份操作 code 定义。
 * 提供两种判断入口：
 * 1. can(operationCode) — 操作码级（原 P0-5，向后兼容）
 * 2. canDo(action, resource, context?) — 资源级（P2 Req7 新增，单一入口）
 *
 * P2 Req7 增强：
 * - 支持 5 角色项目级权限区分（assistant/manager/partner/qc_partner/eqcr）
 * - 共享权限定义来自 `@/permissions/permission-matrix`
 * - `canDo` 为底稿前端判定 isReadonly/按钮禁用/字段可编辑的统一入口
 * - 前端仅体验优化，后端 deps 层为安全边界
 *
 * @example
 * ```ts
 * const { can, canDo, currentRole } = usePermissionMatrix()
 * // 操作码级（向后兼容）
 * if (can('wp:edit')) { ... }
 * // 资源级（P2 推荐用法）
 * if (canDo('edit', 'workpaper', { isLocked: false })) { ... }
 * ```
 */
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import {
  can as matrixCan,
  isReadonly as matrixIsReadonly,
  whyCannotDo as matrixWhyCannotDo,
  getAllowedActions as matrixGetAllowedActions,
  type Role,
  type Action,
  type Resource,
  type PermissionContext,
} from '@/permissions/permission-matrix'

// Re-export types for consumers
export type { Role, Action, Resource, PermissionContext } from '@/permissions/permission-matrix'

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

// ─── P2 Req7: 系统角色→Permission_Matrix 5角色映射 ───────────────────────────
const SYSTEM_ROLE_TO_MATRIX_ROLE: Record<string, Role> = {
  admin: 'partner',          // admin 等效最高权限
  partner: 'partner',
  signing_partner: 'partner',
  manager: 'manager',
  auditor: 'assistant',
  assistant: 'assistant',
  qc: 'qc_partner',
  quality_control: 'qc_partner',
  qc_partner: 'qc_partner',
  eqcr: 'eqcr',
}

/**
 * 标准化角色名（兼容旧别名）— 用于操作码级判断
 */
export function normalizeRole(role: string): string {
  const r = role.toLowerCase().trim()
  if (r === 'assistant') return 'auditor'
  if (r === 'quality_control') return 'qc'
  if (r === 'signing_partner') return 'partner'
  return r
}

/**
 * 将系统角色转换为 Permission_Matrix 的 5 角色之一
 */
export function toMatrixRole(systemRole: string): Role {
  const r = systemRole.toLowerCase().trim()
  return SYSTEM_ROLE_TO_MATRIX_ROLE[r] ?? 'assistant'
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

  /** P2 Req7: 当前用户的 Permission_Matrix 5 角色 */
  const matrixRole = computed<Role>(() => toMatrixRole(authStore.user?.role ?? ''))

  const allowedOperations = computed(() => {
    const base = ROLE_OPERATIONS[currentRole.value] ?? new Set<string>()
    if (projectRole.value) {
      const extra = PROJECT_ROLE_OPERATIONS[projectRole.value] ?? new Set<string>()
      return new Set([...base, ...extra])
    }
    return base
  })

  /**
   * 操作码级判断（向后兼容 P0-5）
   * 判断当前用户是否可以执行指定操作码
   */
  function can(operationCode: string): boolean {
    if (!currentRole.value) return false
    if (currentRole.value === 'admin') return true
    return allowedOperations.value.has(operationCode)
  }

  /**
   * P2 Req7: 资源级权限判断 — 单一入口
   *
   * 底稿前端通过此方法判定 isReadonly/按钮禁用/字段可编辑状态。
   * 前端仅体验优化，后端 deps 层为安全边界。
   *
   * @param action - 请求动作
   * @param resource - 目标资源
   * @param context - 可选上下文（锁定/复核状态）
   */
  function canDo(action: Action, resource: Resource, context?: PermissionContext): boolean {
    // admin 可做一切
    if (currentRole.value === 'admin') return true
    return matrixCan(matrixRole.value, action, resource, context)
  }

  /**
   * P2 Req7: 判断当前用户对指定资源是否只读
   * 等价于 !canDo('edit', resource, context)
   */
  function isReadonlyFor(resource: Resource, context?: PermissionContext): boolean {
    if (currentRole.value === 'admin') return false
    return matrixIsReadonly(matrixRole.value, resource, context)
  }

  /**
   * P2 Req7: 返回当前用户对指定资源的所有允许动作
   */
  function allowedActionsFor(resource: Resource, context?: PermissionContext): Action[] {
    if (currentRole.value === 'admin') {
      return ['edit', 'review', 'approve', 'delete', 'export', 'import', 'refresh', 'view']
    }
    return matrixGetAllowedActions(matrixRole.value, resource, context)
  }

  /**
   * 操作码级：返回不能执行操作的原因
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

  /**
   * P2 Req7: 资源级：返回拒绝原因
   */
  function whyCannotDo(action: Action, resource: Resource, context?: PermissionContext): string | null {
    if (canDo(action, resource, context)) return null
    return matrixWhyCannotDo(matrixRole.value, action, resource, context)
  }

  return {
    // ─── P0-5 向后兼容 ───
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

    // ─── P2 Req7 资源级权限（推荐新代码使用） ───
    matrixRole,
    canDo,
    isReadonlyFor,
    allowedActionsFor,
    whyCannotDo,
  }
}
