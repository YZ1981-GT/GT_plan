/**
 * 公式引用校验问题 → 中文提示（spec formula-fetch-followup-defect-closure 7.2 浏览器实测发现）。
 *
 * 后端「保存前引用校验」同一契约：报表公式 / 底稿公式 / 底稿用户公式 / 附注公式保存 422 与地址库 `/validate`
 * 逐个引用给问题 `{ref, uri, status, reason?, message, target?}` —— **原因文案在 `message`**，`reason` / `status`
 * 是状态码（`not_found`）。原状：附注公式弹窗只显示引用不显示原因、底稿公式面板把问题对象拼成「[object Object]」、
 * 全局提示与 `handleApiError` 只取 `detail.message`（底稿公式 422 没有 message ⇒ 整段 JSON 或「请求参数有误」）。
 */

/** 422 detail 带逐引用问题清单的错误码（报表 / 附注 / 底稿用户公式 = DANGLING_REFS，底稿公式 = REF_NOT_FOUND） */
export const REF_ISSUE_ERROR_CODES: ReadonlySet<string> = new Set(['FORMULA_DANGLING_REFS', 'FORMULA_REF_NOT_FOUND'])

/** 一条引用问题 → 「引用：原因」；带目标单元格时前缀「【单元格】」。取不到任何内容返回空串。 */
export function formatRefIssue(issue: unknown): string {
  if (typeof issue === 'string') return issue.trim()
  if (!issue || typeof issue !== 'object') return ''
  const it = issue as Record<string, unknown>
  const text = (v: unknown) => (typeof v === 'string' ? v.trim() : '')
  const ref = text(it.ref) || text(it.uri)
  const why = text(it.message)
  const target = text(it.target) || text(it.target_cell)
  const body = ref && why ? `${ref}：${why}` : ref || why
  return body && target ? `【${target}】${body}` : body
}

/** 问题清单 → 去重后以「；」连接；不是数组或全空返回空串。 */
export function formatRefIssues(issues: unknown): string {
  if (!Array.isArray(issues)) return ''
  return [...new Set(issues.map(formatRefIssue).filter(Boolean))].join('；')
}

/**
 * 后端 422 detail 是公式引用校验失败 → 「后端说明：逐条问题」；不是这类 detail 返回空串（调用方照旧取 message）。
 * 底稿公式的 422 没有 message，用「公式引用无法解析，未保存」。
 */
export function refIssueDetailText(detail: unknown): string {
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return ''
  const d = detail as Record<string, unknown>
  if (!REF_ISSUE_ERROR_CODES.has(String(d.error_code || ''))) return ''
  const head = (typeof d.message === 'string' && d.message.trim()) || '公式引用无法解析，未保存'
  const list = formatRefIssues(d.issues)
  return list ? `${head}：${list}` : head
}
