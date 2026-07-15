/**
 * importFromSummary — 从各循环 *-1 函证汇总表带入行的共用能力
 *
 * 模式对齐 H0-5 / G0-6：
 *   wp-id-by-code → render-config → 筛 confirmation-v1 rows → 调用方 map/import
 *
 * 不依赖 cycle 专属 unreplied-entities API，D0/F0 可立即接通。
 */
import api from '@/utils/http'
import type { ConfirmationRow } from '../confirmationTypes'

export type SummaryRow = ConfirmationRow

export interface FetchSummaryResult {
  wpId: string
  rows: SummaryRow[]
}

/** 默认：未回函（含 is_replied=false 且非相符） */
export function defaultUnrepliedFilter(r: SummaryRow): boolean {
  return r.match_status === '未回函' || (r.is_replied === false && r.match_status !== '相符')
}

/** 已回函且差异 ≠ 0（供差异调节表） */
export function defaultDiffFilter(r: SummaryRow): boolean {
  if (!r.is_replied && r.match_status !== '不符') return false
  if (r.match_status === '相符') return false
  const sent = Number(r.amount) || 0
  const reply = Number(r.reply_amount) || 0
  const diff = Math.round((sent - reply) * 100) / 100
  return diff !== 0 || r.match_status === '不符'
}

/** 电子回函（传真/电子邮件）— 供可靠性验证表 */
export function defaultElectronicReplyFilter(r: SummaryRow): boolean {
  const method = String(r.reply_method || '')
  return /传真|电子|email|Email|EMAIL|传真\/邮件|电子邮件/.test(method)
}

/** 按科目大类过滤（可选） */
export function accountTypeFilter(types: string[]): (r: SummaryRow) => boolean {
  const set = new Set(types.map(t => t.trim()).filter(Boolean))
  return (r) => {
    if (!set.size) return true
    const t = String(r.account_type || '').trim()
    return set.has(t)
  }
}

/**
 * 拉取同项目汇总表 confirmation-v1 全部行
 * @throws 网络错误；未找到底稿时返回 null（由调用方提示）
 */
export async function fetchConfirmationSummaryRows(
  projectId: string,
  summaryWpCode: string,
): Promise<FetchSummaryResult | null> {
  if (!projectId?.trim() || !summaryWpCode?.trim()) return null

  const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
    params: { project_id: projectId, wp_code: summaryWpCode },
    _silent: true,
  } as any)
  const wpId = (idRes as any)?.wp_id as string | undefined
  if (!wpId) return null

  const cfg = await api.get<any>(`/api/workpapers/${wpId}/render-config`, { _silent: true } as any)
  const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
  let rows: SummaryRow[] = []
  for (const sheet of sheets) {
    const hd = sheet?.html_data ?? sheet?.htmlData
    if (hd?._format === 'confirmation-v1' && Array.isArray(hd.rows)) {
      rows = hd.rows
      break
    }
  }
  return { wpId, rows }
}

export async function filterSummaryRows(
  projectId: string,
  summaryWpCode: string,
  filterFn: (r: SummaryRow) => boolean = defaultUnrepliedFilter,
): Promise<{ wpId: string; rows: SummaryRow[] } | null> {
  const result = await fetchConfirmationSummaryRows(projectId, summaryWpCode)
  if (!result) return null
  return { wpId: result.wpId, rows: result.rows.filter(filterFn) }
}

/** 映射为替代程序公司行的通用字段 */
export function mapSummaryToAlternativeCompany(
  r: SummaryRow,
  defaultItemName = '',
): {
  entity_name: string
  confirm_index?: string
  _source: 'auto'
  balance: { item_name: string; closing_balance: number }
} {
  return {
    entity_name: r.entity_name || '',
    confirm_index: r.confirm_index,
    _source: 'auto',
    balance: {
      item_name: r.account_type || defaultItemName,
      closing_balance: Number(r.amount) || 0,
    },
  }
}

/**
 * 一键：取未回函并 map 为替代公司载荷
 * @returns null = 找不到汇总底稿；空数组 = 无未回函
 */
export async function importUnrepliedAsCompanies(
  projectId: string,
  summaryWpCode: string,
  options?: {
    accountTypes?: string[]
    defaultItemName?: string
    extraFilter?: (r: SummaryRow) => boolean
  },
): Promise<{ ok: true; companies: ReturnType<typeof mapSummaryToAlternativeCompany>[]; emptyReason?: string }
  | { ok: false; reason: 'missing-project' | 'missing-summary' | 'error'; message: string }
> {
  if (!projectId?.trim()) {
    return { ok: false, reason: 'missing-project', message: '缺少项目上下文' }
  }
  try {
    const filters: Array<(r: SummaryRow) => boolean> = [defaultUnrepliedFilter]
    if (options?.accountTypes?.length) filters.push(accountTypeFilter(options.accountTypes))
    if (options?.extraFilter) filters.push(options.extraFilter)

    const result = await fetchConfirmationSummaryRows(projectId, summaryWpCode)
    if (!result) {
      return { ok: false, reason: 'missing-summary', message: `未找到 ${summaryWpCode} 函证结果汇总底稿` }
    }
    if (result.rows.length === 0) {
      return { ok: true, companies: [], emptyReason: `${summaryWpCode} 暂无函证数据` }
    }
    const matched = result.rows.filter(r => filters.every(f => f(r)))
    if (matched.length === 0) {
      return { ok: true, companies: [], emptyReason: `${summaryWpCode} 暂无符合条件的未回函项目` }
    }
    return {
      ok: true,
      companies: matched.map(r => mapSummaryToAlternativeCompany(r, options?.defaultItemName || '')),
    }
  } catch (e: any) {
    if (e?.response?.status === 404) {
      return { ok: false, reason: 'missing-summary', message: `未找到 ${summaryWpCode} 函证结果汇总底稿` }
    }
    return { ok: false, reason: 'error', message: e?.message || '带入失败' }
  }
}

/**
 * 拉取同项目任意 confirmation htmlData（按 _format）
 * rows：优先 hd.rows，其次 hd.companies
 */
export async function fetchWorkpaperHtmlRows(
  projectId: string,
  wpCode: string,
  format: string,
): Promise<{ wpId: string; rows: any[]; htmlData: any } | null> {
  if (!projectId?.trim() || !wpCode?.trim()) return null

  const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
    params: { project_id: projectId, wp_code: wpCode },
    _silent: true,
  } as any)
  const wpId = (idRes as any)?.wp_id as string | undefined
  if (!wpId) return null

  const cfg = await api.get<any>(`/api/workpapers/${wpId}/render-config`, { _silent: true } as any)
  const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
  for (const sheet of sheets) {
    const hd = sheet?.html_data ?? sheet?.htmlData
    if (hd?._format === format) {
      const rows = Array.isArray(hd.rows)
        ? hd.rows
        : Array.isArray(hd.companies)
          ? hd.companies
          : []
      return { wpId, rows, htmlData: hd }
    }
  }
  return { wpId, rows: [], htmlData: null }
}

/** 从差异调节表（diff-reconcile-v1）取差异≠0 行 */
export async function fetchDiffReconcileNonZeroRows(
  projectId: string,
  diffWpCode: string,
): Promise<{ wpId: string; rows: any[] } | null> {
  const result = await fetchWorkpaperHtmlRows(projectId, diffWpCode, 'diff-reconcile-v1')
  if (!result) return null
  const rows = result.rows.filter((r) => {
    const diff = Number(r.difference)
    if (Number.isFinite(diff) && diff !== 0) return true
    const sent = Number(r.sent_amount) || 0
    const reply = Number(r.reply_amount) || 0
    return Math.round((sent - reply) * 100) / 100 !== 0
  })
  return { wpId: result.wpId, rows }
}
