/**
 * 角色与数据权限管理 API（dept-role-data-permission Task 11.1）
 *
 * ⚠️ **路径偏离说明**：tasks.md 写的是 `api/system.ts`，但本仓库前端没有
 *    `api/` 目录，所有后端调用封装统一在 `services/` 下（`services/*Api.ts`）。
 *    照 tasks.md 字面新建 `api/` 会凭空多出一套并行目录约定。
 *    故实际落在 `services/systemRoleApi.ts`，命名对齐既有的
 *    `operationAuditApi.ts` / `qcRuleApi.ts`。
 *
 * 🔴 **响应信封已由 `utils/http.ts` 的响应拦截器解开**（`{code,message,data}`
 *    → `response.data = d.data`）⇒ 本文件里 `const { data } = await http.get()`
 *    拿到的**就是业务数据**，不要再写 `data.data`。
 *
 * ⚠️ **未验证**：本文件尚未经 vitest 或浏览器实测（用户要求跳过测试执行）。
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3
 */

import http from '@/utils/http'
import { sysRoles as P_role, sysUserRoles as P_ur } from './apiPaths'

// ─── 类型 ───────────────────────────────────────────────────────────────────

/**
 * 数据权限范围。
 *
 * 🔴 **只有 1/2/5/6 四个合法值**。历史上的 3（本部门）/4（本部门及以下）已废弃
 *    —— 本平台按项目而非部门组织数据，部门维度的数据权限没有落地场景。
 *    后端 `role_service.validate_data_scope` 对 3/4 也返回 400。
 *
 * 📌 **6「我参与的项目」是 2026-08-31 新增**（spec `data-scope-participant-visibility`）：
 *    语义 = 项目级可见集（`project_users` ∪ `partner_id` ∪ `manager_id` ∪
 *    `project_members` ∪ `created_by` 五来源并集）。
 *
 *    与 5「仅本人数据」的区别是本档存在的全部理由：5 只认「我**创建**的」，
 *    6 认「我**参与**的」。被指派为项目经理／现场负责人但不是创建人的账号，
 *    在 scope=5 下最终可见集为**空**（真库实测）。
 *
 *    ⚠️ 权限序上 **6 比 5 宽**（数值大小与权限大小无关）：`created_by` 本身
 *       就是项目级五来源之一 ⇒ scope=5 的结果恒为 scope=6 结果的子集。
 *       后端 `PRIORITY_ORDER = {1:0, 2:1, 6:2, 5:3}`。
 */
export type DataScope = 1 | 2 | 5 | 6

export interface SysRole {
  id: number
  name: string
  role_key: string
  data_scope: number
  status: string
}

export interface RoleCreatePayload {
  name: string
  role_key: string
  data_scope: DataScope
  status?: string
  /** 仅 data_scope=2 时有意义；其余 scope 传了也会被后端忽略/清空 */
  project_ids?: string[] | null
}

/**
 * 修改角色的载荷。
 *
 * 🔴 **每个字段的 `undefined` 与显式值语义不同**：不传 = 不改该字段。
 *    尤其 `project_ids`：
 *      - `undefined` → 保持原有项目关联
 *      - `[]`        → **清空**项目关联
 *    若前端图省事把 undefined 也序列化成 `[]`，「只改角色名」的操作会把
 *    项目配置全抹掉。故本类型全部字段可选，且调用方须只放真正要改的字段。
 */
export interface RoleUpdatePayload {
  name?: string
  role_key?: string
  data_scope?: DataScope
  status?: string
  project_ids?: string[] | null
}

export interface BoundRole {
  id: number
  name: string
  role_key: string
  data_scope: number
}

/** 数据权限范围的中文标签（UI 全中文化） */
export const DATA_SCOPE_LABELS: Record<number, string> = {
  1: '全部数据',
  2: '自定义项目',
  6: '我参与的项目',
  5: '仅本人数据',
}

/**
 * 下拉选项（顺序即展示顺序：**从宽到窄**）。
 *
 * ⚠️ 顺序是 `1, 2, 6, 5` 而不是数值升序 —— 它对齐后端的权限序
 *    `PRIORITY_ORDER = {1:0, 2:1, 6:2, 5:3}`。6 排在 5 之前是因为
 *    scope=5 的结果恒为 scope=6 结果的**子集**（`created_by` 是项目级
 *    五来源之一）⇒ 6 的范围恒不小于 5。
 *    按数值排会让管理员以为"5 比 6 宽"，配错权限。
 */
export const DATA_SCOPE_OPTIONS: Array<{ value: DataScope; label: string; hint: string }> = [
  { value: 1, label: '全部数据', hint: '可见系统内全部未删除项目' },
  { value: 2, label: '自定义项目', hint: '仅可见下方勾选的项目' },
  {
    value: 6,
    label: '我参与的项目',
    hint: '可见本人参与的项目：被指派为项目经理／现场负责人、签字合伙人、项目成员，或由本人创建',
  },
  { value: 5, label: '仅本人数据', hint: '仅可见本人**创建**的项目（不含仅被指派参与的）' },
]

/**
 * 取 data_scope 的中文标签。
 *
 * ⚠️ 传入库里的脏值（3/4 或其他）时返回带原值的提示而**不是**空串 ——
 *    静默显示空白会让人以为"没配"，而实际是配了个非法值。
 */
export function dataScopeLabel(scope: number): string {
  return DATA_SCOPE_LABELS[scope] ?? `未知范围（${scope}）`
}

// ─── 角色 ───────────────────────────────────────────────────────────────────

/**
 * 角色列表。
 *
 * 🔴 **必须做 in-flight 共享，否则会弹「加载角色列表失败：网络不通」**
 *    （2026-08-27 浏览器实测确诊）：
 *
 *    `RoleDataScopeManager` 与 `UserRoleBindingPanel` 都调本函数，而
 *    `PermissionCenter` 的 Tab 是**累积挂载**（切过的 Tab 不销毁）⇒ 两个组件
 *    可同时在飞同一个 `GET /api/system/roles`。此时 `utils/http.ts:97-99` 的
 *    GET 去重会 **abort 先发的那个**（同 key 即取消旧请求），被掐的那次
 *    `status=0` ⇒ `handleApiError` 归类为 network ⇒ 弹「网络不通」。
 *    表格数据其实是好的（另一个请求 200 了），所以现象是
 *    「数据显示正常但红色报错弹窗」，极易被误判成后端/网络故障。
 *
 *    ⇒ 这里让并发调用**复用同一个 promise**，从根上不产生第二个请求。
 *      （只共享"在飞"期间，结束即释放，不做结果缓存 —— 刷新按钮仍能拿到新数据。）
 */
let _rolesInflight: Promise<SysRole[]> | null = null

export async function listRoles(): Promise<SysRole[]> {
  if (_rolesInflight) return _rolesInflight

  _rolesInflight = (async () => {
    const { data } = await http.get(P_role.list)
    return Array.isArray(data) ? data : []
  })()

  try {
    return await _rolesInflight
  } finally {
    _rolesInflight = null
  }
}

export async function createRole(payload: RoleCreatePayload): Promise<SysRole> {
  const { data } = await http.post(P_role.create, payload)
  return data
}

export async function updateRole(
  roleId: number,
  payload: RoleUpdatePayload,
): Promise<SysRole> {
  const { data } = await http.put(P_role.detail(roleId), payload)
  return data
}

/** 取角色的自定义项目 id 列表（后端已过滤软删项目） */
export async function getRoleProjects(roleId: number): Promise<string[]> {
  const { data } = await http.get(P_role.projects(roleId))
  return Array.isArray(data) ? data : []
}

export async function deleteRole(roleId: number): Promise<void> {
  await http.delete(P_role.detail(roleId))
}

// ─── 账号角色绑定 ───────────────────────────────────────────────────────────

export async function getUserRoles(userId: string): Promise<BoundRole[]> {
  const { data } = await http.get(P_ur.ofUser(userId))
  return Array.isArray(data) ? data : []
}

/**
 * 覆盖写某账号的角色绑定。
 *
 * ⚠️ `roleIds` 传 `[]` 是**合法**的，表示清空绑定。此后该账号的数据权限
 *    由其 `users.role` 枚举对应的种子角色决定，**不是**"没有任何权限"。
 *    UI 上不要把"清空"写成"移除权限"。
 */
export async function assignUserRoles(
  userId: string,
  roleIds: number[],
): Promise<number[]> {
  const { data } = await http.put(P_ur.assign(userId), { role_ids: roleIds })
  return Array.isArray(data) ? data : []
}
