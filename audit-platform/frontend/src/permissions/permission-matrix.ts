/**
 * Permission Matrix — 单一权限定义（前后端共享）
 * Feature: platform-global-hardening
 *
 * 5 角色项目级权限区分，单一入口 `can(role, action, resource, context)`。
 * 前端仅用于体验优化（按钮显隐/只读态），后端 deps 层为安全边界。
 *
 * 角色映射（中文→code）：
 * - 审计助理 = assistant
 * - 现场经理 = manager
 * - 业务合伙人 = partner
 * - 质量控制复核合伙人 = qc_partner
 * - EQCR 技术复核人 = eqcr
 */

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export type Role = 'assistant' | 'manager' | 'partner' | 'qc_partner' | 'eqcr'

export type Action = 'edit' | 'review' | 'approve' | 'delete' | 'export' | 'import' | 'refresh' | 'view'

export type Resource = 'workpaper' | 'adjustment' | 'report' | 'note' | 'template' | 'project_settings'

export interface PermissionContext {
  projectId?: string
  wpCode?: string
  /** 底稿是否已锁定（仅 partner 可解锁） */
  isLocked?: boolean
  /** 复核状态：approved = 审批后不可编辑 */
  reviewStatus?: string
}

// ─── 角色→资源→动作 权限定义表 ────────────────────────────────────────────────

/**
 * 基础权限矩阵：role → resource → allowed actions
 *
 * 规则来源（design.md + requirements 7.6）：
 * - assistant: edit workpaper, view all, export, import
 * - manager: all assistant + review, approve adjustments, edit project_settings
 * - partner: all manager + approve reports, refresh, delete
 * - qc_partner: view all, review all, cannot edit
 * - eqcr: view all, review (read-only), cannot edit/approve
 */
const PERMISSION_TABLE: Record<Role, Record<Resource, Set<Action>>> = {
  assistant: {
    workpaper: new Set(['edit', 'view', 'export', 'import']),
    adjustment: new Set(['edit', 'view', 'export', 'import']),
    report: new Set(['view', 'export']),
    note: new Set(['edit', 'view', 'export']),
    template: new Set(['view']),
    project_settings: new Set(['view']),
  },
  manager: {
    workpaper: new Set(['edit', 'review', 'view', 'export', 'import']),
    adjustment: new Set(['edit', 'review', 'approve', 'view', 'export', 'import']),
    report: new Set(['edit', 'review', 'view', 'export']),
    note: new Set(['edit', 'review', 'view', 'export']),
    template: new Set(['edit', 'view']),
    project_settings: new Set(['edit', 'view']),
  },
  partner: {
    workpaper: new Set(['edit', 'review', 'approve', 'delete', 'view', 'export', 'import', 'refresh']),
    adjustment: new Set(['edit', 'review', 'approve', 'delete', 'view', 'export', 'import']),
    report: new Set(['edit', 'review', 'approve', 'delete', 'view', 'export', 'refresh']),
    note: new Set(['edit', 'review', 'approve', 'delete', 'view', 'export', 'refresh']),
    template: new Set(['edit', 'delete', 'view']),
    project_settings: new Set(['edit', 'delete', 'view']),
  },
  qc_partner: {
    workpaper: new Set(['review', 'view', 'export']),
    adjustment: new Set(['review', 'view', 'export']),
    report: new Set(['review', 'view', 'export']),
    note: new Set(['review', 'view', 'export']),
    template: new Set(['view']),
    project_settings: new Set(['view']),
  },
  eqcr: {
    workpaper: new Set(['review', 'view', 'export']),
    adjustment: new Set(['review', 'view', 'export']),
    report: new Set(['review', 'view', 'export']),
    note: new Set(['review', 'view', 'export']),
    template: new Set(['view']),
    project_settings: new Set(['view']),
  },
}

// ─── 全部角色列表（用于属性测试枚举） ──────────────────────────────────────────
export const ALL_ROLES: readonly Role[] = ['assistant', 'manager', 'partner', 'qc_partner', 'eqcr'] as const
export const ALL_ACTIONS: readonly Action[] = ['edit', 'review', 'approve', 'delete', 'export', 'import', 'refresh', 'view'] as const
export const ALL_RESOURCES: readonly Resource[] = ['workpaper', 'adjustment', 'report', 'note', 'template', 'project_settings'] as const

// ─── 核心判定函数 ─────────────────────────────────────────────────────────────

/**
 * 单一入口：判断指定角色是否可对指定资源执行指定动作。
 *
 * 前后端共享此定义——前端用于体验优化（按钮显隐/只读），后端 deps 层为安全边界。
 *
 * 特殊规则：
 * 1. 锁定底稿：仅 partner 可解锁（执行 edit 动作）
 * 2. 复核通过后（reviewStatus === 'approved'）：任何角色均不可 edit
 * 3. view 动作对所有角色始终允许（信息透明）
 *
 * @param role - 当前用户角色
 * @param action - 请求的动作
 * @param resource - 目标资源类型
 * @param context - 可选上下文（锁定状态/复核状态等）
 * @returns 是否允许执行
 */
export function can(
  role: Role,
  action: Action,
  resource: Resource,
  context?: PermissionContext,
): boolean {
  // view 始终允许（信息透明原则）
  if (action === 'view') return true

  // 特殊规则 2：复核通过后不可编辑（任何角色）
  if (context?.reviewStatus === 'approved' && action === 'edit') {
    return false
  }

  // 特殊规则 1：锁定底稿仅 partner 可操作 edit
  if (context?.isLocked && resource === 'workpaper' && action === 'edit') {
    return role === 'partner'
  }

  // 基础权限表查询
  const rolePermissions = PERMISSION_TABLE[role]
  if (!rolePermissions) return false

  const resourcePermissions = rolePermissions[resource]
  if (!resourcePermissions) return false

  return resourcePermissions.has(action)
}

/**
 * 判断角色对指定资源是否只读（不可 edit）。
 * 等价于 `!can(role, 'edit', resource, context)`
 */
export function isReadonly(
  role: Role,
  resource: Resource,
  context?: PermissionContext,
): boolean {
  return !can(role, 'edit', resource, context)
}

/**
 * 获取角色对指定资源的所有允许动作集合。
 */
export function getAllowedActions(
  role: Role,
  resource: Resource,
  context?: PermissionContext,
): Action[] {
  return ALL_ACTIONS.filter(action => can(role, action, resource, context))
}

/**
 * 返回拒绝原因，允许则返回 null。
 */
export function whyCannotDo(
  role: Role,
  action: Action,
  resource: Resource,
  context?: PermissionContext,
): string | null {
  if (can(role, action, resource, context)) return null

  if (context?.reviewStatus === 'approved' && action === 'edit') {
    return `复核已通过，${resource} 不可编辑`
  }

  if (context?.isLocked && resource === 'workpaper' && action === 'edit') {
    return `底稿已锁定，仅业务合伙人可解锁编辑`
  }

  const roleNames: Record<Role, string> = {
    assistant: '审计助理',
    manager: '现场经理',
    partner: '业务合伙人',
    qc_partner: '质量控制复核合伙人',
    eqcr: 'EQCR技术复核人',
  }

  return `${roleNames[role]}无权对${resource}执行${action}操作`
}
