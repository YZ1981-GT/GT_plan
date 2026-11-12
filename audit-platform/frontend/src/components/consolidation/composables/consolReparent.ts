/**
 * 「合并」总览页拖拽改上级的结果提示（spec consol-autotree-linkage-closure R3.3）。
 *
 * 后端 `PATCH /api/projects/{id}/parent-code` 把同企业同年度的合并项目与单户项目一起改（上级代码、上级名称、
 * 与上级关系、补齐最终控制方、向导回填数据），返回同步了哪些项目的哪些字段与说明；这里拼成一句给用户看。
 */

export interface ReparentSyncedItem {
  id: string
  name: string
  report_scope: string
  /** 变化了的字段（中文名，后端 FIELD_LABELS） */
  fields: string[]
}

export interface ReparentResult {
  parent_company_code?: string | null
  parent_company_name?: string | null
  synced?: ReparentSyncedItem[]
  notices?: string[]
}

const SCOPE_LABELS: Record<string, string> = { consolidated: '合并项目', standalone: '单户项目' }

/**
 * 判断拖拽改上级是否因改前上级已变化而发生 CAS 冲突。
 *
 * 该判断集中在组合式函数中，调用方才能把 CAS 冲突与其他 409（重复数据、业务冲突）
 * 区分开，避免全局错误拦截器和页面通用错误处理重复提示，也避免误重试 PATCH。
 */
export function isParentCodeConflict(error: unknown): boolean {
  const response = (error as { response?: { status?: unknown; data?: unknown } } | null)?.response
  if (response?.status !== 409) return false

  const data = response.data
  const detail = data && typeof data === 'object' && !Array.isArray(data) && 'detail' in data
    ? (data as { detail?: unknown }).detail
    : data
  return Boolean(
    detail &&
    typeof detail === 'object' &&
    !Array.isArray(detail) &&
    (detail as { error_code?: unknown }).error_code === 'PARENT_CODE_CONFLICT',
  )
}

/** 「已同步 甲公司（单户项目）的上级企业代码、上级企业名称；甲公司（合并项目）的…。上级企业 X 本年度尚未建项…。」 */
export function reparentSummary(result: ReparentResult | null | undefined): string {
  const changed = (result?.synced || []).filter((s) => Array.isArray(s.fields) && s.fields.length)
  const parts = [changed.length
    ? `已同步 ${changed.map((s) => `${s.name}（${SCOPE_LABELS[s.report_scope] || '项目'}）的${s.fields.join('、')}`).join('；')}`
    : '项目信息没有变化']
  for (const notice of result?.notices || []) if (notice) parts.push(notice.replace(/[。.]$/, ''))
  return `${parts.join('。')}。`
}
