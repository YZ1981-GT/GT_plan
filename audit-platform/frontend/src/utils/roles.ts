/**
 * 角色体系治理（2026-05-20 复盘修复）
 *
 * 解决问题：
 * 1. 后端 UserRole 枚举仅 6 种，但代码出现 11+ 种角色字符串
 * 2. assistant 角色后端不存在（实际是 auditor），前端处处误判
 * 3. partner 不是 manager 权限 superset
 * 4. EQCR 是项目级角色被混入系统级
 * 5. 角色显示名 i18n 缺失
 *
 * 设计原则：
 * - 后端枚举保持不变（admin/partner/manager/site_lead/auditor/qc/eqcr/readonly，8 值）— 避免 Alembic migration
 * - 前端引入统一映射层：业务角色名 → 后端枚举值
 * - 显示名集中管理
 * - 权限继承明确化
 *
 * 命名双轨（易混，改动前务必分清）：
 *   - `site_lead`  = **现场经理**，系统角色（`users.role`）
 *   - `field_lead` = **现场负责人**，项目级角色（`project_members.role`，varchar 非枚举）
 *   两者不是同一个东西，也不在同一张表。
 */

/** 后端实际存在的系统角色（UserRole 枚举，8 值） */
export type SystemRole =
  | 'admin'
  | 'partner'
  | 'manager'
  | 'site_lead'
  | 'auditor'
  | 'qc'
  | 'eqcr'
  | 'readonly'

/** 项目级角色（ProjectAssignment.role 字段，独立于系统角色） */
export type ProjectRole = 'partner' | 'manager' | 'site_lead' | 'auditor' | 'qc' | 'readonly' | 'eqcr'

/** UI 视图角色（与后端枚举对齐，不再有"assistant"幽灵角色） */
export type ViewRole = SystemRole

/**
 * 别名兼容映射 — 处理历史代码中混用的角色字符串
 *
 * 'assistant' 是历史前端别名，对应后端 auditor
 * 'quality_control' 是历史前端别名，对应后端 qc
 * 'pm' / 'project_manager' 历史别名，对应后端 manager
 */
const ROLE_ALIAS_MAP: Record<string, SystemRole> = {
  assistant: 'auditor',
  quality_control: 'qc',
  pm: 'manager',
  project_manager: 'manager',
  qc_reviewer: 'qc',
}

/**
 * 后端枚举值全集 —— `normalizeRole` 的白名单。
 *
 * 🔴 必须与 `SystemRole` 联合类型逐一对应：漏一个值就等于把那个角色判成
 * 「未知」并返回 `''`（不报错、不打红，只表现为该角色权限全丢 / 显示名变原始串）。
 * `eqcr` 此前正是这样被漏掉的。`satisfies` 让「联合类型加了成员但这里忘了加」
 * 在编译期暴露。
 */
const VALID_SYSTEM_ROLES = [
  'admin',
  'partner',
  'manager',
  'site_lead',
  'auditor',
  'qc',
  'eqcr',
  'readonly',
] as const satisfies readonly SystemRole[]

/** 标准化角色：把别名转为后端枚举值 */
export function normalizeRole(role: string | null | undefined): SystemRole | '' {
  if (!role) return ''
  const lower = role.toLowerCase()
  if (lower in ROLE_ALIAS_MAP) return ROLE_ALIAS_MAP[lower]
  if ((VALID_SYSTEM_ROLES as readonly string[]).includes(lower)) return lower as SystemRole
  return ''
}

/**
 * 角色中文显示名（单一真源）
 *
 * ⚠️ `manager` = 「项目经理」、`site_lead` = 「现场经理」，两者**必须不同名** ——
 * 若都叫「现场经理」，界面上两个不同角色会显示成同一个中文名，用户无法区分。
 */
const ROLE_DISPLAY_NAMES: Record<SystemRole, string> = {
  admin: '系统管理员',
  partner: '合伙人',
  manager: '项目经理',
  site_lead: '现场经理',
  auditor: '审计助理',
  qc: '质控人员',
  eqcr: 'EQCR 独立复核',
  readonly: '只读用户',
}

/** 获取角色中文显示名 */
export function roleDisplayName(role: string | null | undefined): string {
  const normalized = normalizeRole(role || '')
  if (normalized) return ROLE_DISPLAY_NAMES[normalized] ?? role ?? ''
  return role ?? ''
}

/**
 * 角色继承关系（superset 关系）
 *
 * partner 继承 manager 全部权限
 * manager 继承 auditor 全部权限
 * site_lead 权限等同 manager（故也继承 auditor）
 * qc 继承 auditor 全部权限
 * admin 全权
 *
 * ⚠️ `eqcr` 只含自身：它是**项目级双层**判断的角色（见 `isEqcrEligible`），
 * 系统级不赋予任何继承 —— 若给它继承 auditor 之类，会让「仅项目级 eqcr」
 * 的账号凭空获得系统级权限。
 */
export const ROLE_HIERARCHY: Record<SystemRole, SystemRole[]> = {
  admin: ['admin', 'partner', 'manager', 'site_lead', 'auditor', 'qc', 'eqcr', 'readonly'],
  partner: ['partner', 'manager', 'site_lead', 'auditor'], // partner 继承 manager + site_lead + auditor
  manager: ['manager', 'auditor'],
  // 现场经理：权限完全等同 manager（继承 auditor）。
  // 后端侧靠 ROLE_ALIAS_MAP['site_lead']='manager' 保证等价，此处与之对齐。
  site_lead: ['site_lead', 'manager', 'auditor'],
  qc: ['qc', 'auditor'],
  eqcr: ['eqcr'],
  auditor: ['auditor'],
  readonly: ['readonly'],
}

/** 检查角色是否包含目标角色（含继承） */
export function roleIncludes(currentRole: string | null | undefined, targetRole: SystemRole): boolean {
  const normalized = normalizeRole(currentRole || '')
  if (!normalized) return false
  return ROLE_HIERARCHY[normalized]?.includes(targetRole) ?? false
}

/** 检查是否为合伙人级及以上（admin/partner） */
export function isPartnerOrAbove(role: string | null | undefined): boolean {
  const n = normalizeRole(role || '')
  return n === 'admin' || n === 'partner'
}

/**
 * 检查是否为经理级及以上（admin/partner/manager/site_lead）
 *
 * `site_lead` 必须在列：它权限等同 manager，漏掉会让现场经理在所有
 * 「经理级才显示」的入口处看不到按钮（不报错，只是少东西，极难定位）。
 */
export function isManagerOrAbove(role: string | null | undefined): boolean {
  const n = normalizeRole(role || '')
  return n === 'admin' || n === 'partner' || n === 'manager' || n === 'site_lead'
}

/** 检查是否为质控相关（admin/partner/qc） */
export function canDoQC(role: string | null | undefined): boolean {
  const n = normalizeRole(role || '')
  return n === 'admin' || n === 'partner' || n === 'qc'
}

/**
 * EQCR 资格判断（项目级双层）
 *
 * @param systemRole 系统级角色（仅 admin/partner 可候选）
 * @param projectRole 项目级角色（必须为 'eqcr'）
 */
export function isEqcrEligible(
  systemRole: string | null | undefined,
  projectRole: string | null | undefined,
): boolean {
  const sysN = normalizeRole(systemRole || '')
  const isSystemEligible = sysN === 'admin' || sysN === 'partner'
  return isSystemEligible && projectRole === 'eqcr'
}
