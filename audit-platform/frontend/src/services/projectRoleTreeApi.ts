/**
 * 用户 → 项目 → 角色 三层树 API（project-data-permission-isolation Task 6.1）
 *
 * ⚠️ **路径偏离说明**：tasks.md 写的是 `src/api/system.ts`，但本仓库前端**没有
 *    `api/` 目录**，所有后端调用封装统一在 `services/` 下（`services/*Api.ts`）。
 *    照字面新建 `api/` 会凭空多出一套并行目录约定。故落在
 *    `services/projectRoleTreeApi.ts`，与既有 `systemRoleApi.ts` 同一命名法。
 *
 * 🔴 **响应信封已由 `utils/http.ts` 的响应拦截器解开**（`{code,message,data}`
 *    → `response.data = d.data`）⇒ 这里 `const { data } = await http.get()`
 *    拿到的**就是业务数据**，不要再写 `data.data`（那会得到 undefined）。
 *
 * 🔴 **只读**：本模块只有 GET。变更项目角色分配走既有 project_users 分配 API，
 *    不在此新建与其并行的写路径（Req 6.1/6.3/6.4）。
 *
 * Validates: Requirements 1.1, 1.4, 1.5, 2.1, 2.2, 2.3, 5.1, 5.2, 5.3
 */

import http from '@/utils/http'
import { userProjectRoleTree as P } from './apiPaths'

// ─── 类型（与后端 schemas/project_role_tree.py 一一对应） ────────────────────

/**
 * 数据权限范围。
 *
 * 🔴 只有 1/2/5 三个合法值 —— 3（本部门）/4（本部门及以下）已废弃，
 *    后端 `normalize_data_scope` 会把它们降级为 5。
 */
export type DataScope = 1 | 2 | 5

/**
 * 树第 3 层：账号在某项目下的项目角色。
 *
 * ⚠️ 枚举字段都是 `string` 而非联合字面量类型：库里可能存在后端 ORM 枚举
 *    尚未收录的历史值（本仓 `ProjectUserRole` 就因 V109 补过 `eqcr`）。
 *    用窄类型会让 TS 在遇到新值时报错、或诱使写出漏分支的 switch。
 */
export interface RoleNode {
  role: string
  permission_level: string
  valid_from: string | null
  valid_to: string | null
  /** ⚠️ 后端是 `Text` 列，原样透出的**逗号分隔字符串**，不是数组。 */
  scope_cycles: string | null
  scope_accounts: string | null
}

/** 树第 2 层：账号参与的一个项目。 */
export interface ProjectNode {
  project_id: string
  name: string
  client_name: string
  status: string
  /**
   * 该项目**不在**该账号数据权限可见集内（Req 5.4 的视觉标记依据）。
   *
   * 语义是「项目级可见但数据权限不可见」：账号在 project_users 里有绑定
   * （所以出现在树上），但数据权限算出的集合里没有它 ⇒ 实际打不开。
   * 这个"配了角色却看不到"的矛盾状态正是要暴露的东西。
   */
  out_of_scope: boolean
  role: RoleNode
}

/** 树第 1 层：一个账号。 */
export interface UserNode {
  id: string
  username: string
  full_name: string | null
  email: string
  system_role: string
  is_active: boolean
  /**
   * 是否有可展开的项目层。
   *
   * ⚠️ **无项目的账号也会返回**（`has_children=false`）—— 管理员需要看到
   *    "这个账号没有任何项目角色"这个事实，那往往正是要排查的问题。
   */
  has_children: boolean
}

export interface UserNodePage {
  items: UserNode[]
  /** **过滤后**的未删除账号总数（搜索生效时是搜索结果总数，不是全库数）。 */
  total: number
}

export interface UserSubtree {
  user_id: string
  effective_data_scope: number
  effective_data_scope_label: string
  projects: ProjectNode[]
}

export interface ListUserNodesParams {
  search?: string
  page?: number
  page_size?: number
}

// ─── API ────────────────────────────────────────────────────────────────────

/** 取树的根层（账号分页列表）。 */
export async function listUserNodes(
  params: ListUserNodesParams = {},
): Promise<UserNodePage> {
  const { data } = await http.get<UserNodePage>(P.users, { params })
  return data
}

/**
 * 取某账号的子树（项目层 + 角色层 + 数据权限视角）。
 *
 * ⚠️ 账号不存在或已软删时后端返回 **404**，调用方应捕获而不是当成空子树 ——
 *    "账号没了"与"账号没有项目"是两回事。
 */
export async function getUserSubtree(userId: string): Promise<UserSubtree> {
  const { data } = await http.get<UserSubtree>(P.subtree(userId))
  return data
}

export default { listUserNodes, getUserSubtree }
