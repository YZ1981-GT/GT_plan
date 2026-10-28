/**
 * 用户管理「编辑」只发改了的字段（spec procedure-chain-followup-closure R1）。
 *
 * 后端 `PUT /api/users/{id}` 的请求体多余字段直接 422（用户名不可改、密码改走「重置密码」），
 * 原先编辑把整张表单（含用户名、空密码）一起发出去。没改任何字段时返回空对象，调用方不发请求。
 */
export interface EditableUserFields {
  email: string
  role: string
}

export function buildUserUpdateBody(
  original: EditableUserFields,
  edited: EditableUserFields,
): Partial<EditableUserFields> {
  const body: Partial<EditableUserFields> = {}
  const email = (edited.email || '').trim()
  if (email !== (original.email || '').trim()) body.email = email
  if (edited.role !== original.role) body.role = edited.role
  return body
}
