/**
 * H2 在建工程审定 → H4 国企披露 CIP 行跨底稿桥接
 *
 * H2 确认审定后经 EventBus `substantive:adjudicated` 发布 CIP 三栏快照，
 * 并写入 sessionStorage，供 H4 附注（国有企业）打开时回放。
 */

export const H2_CIP_CACHE_PREFIX = 'gt:h2-cip-adjudicated:'

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export interface H2CipAdjudicatedSnapshot {
  endBook: number
  endImpairment: number
  beginBook: number
  beginImpairment: number
  endNet: number
  beginNet: number
  auditedAmount: number
  timestamp: number
  projectId?: string
}

export function buildH2CipSnapshot(input: {
  endBook?: number
  endImpairment?: number
  beginBook?: number
  beginImpairment?: number
  auditedAmount?: number
  projectId?: string
  timestamp?: number
}): H2CipAdjudicatedSnapshot {
  const endBook = num(input.endBook)
  const endImpairment = num(input.endImpairment)
  const beginBook = num(input.beginBook)
  const beginImpairment = num(input.beginImpairment)
  return {
    endBook,
    endImpairment,
    beginBook,
    beginImpairment,
    endNet: endBook - endImpairment,
    beginNet: beginBook - beginImpairment,
    auditedAmount: num(input.auditedAmount) || endBook,
    timestamp: input.timestamp ?? Date.now(),
    projectId: input.projectId,
  }
}

export function cacheH2CipSnapshot(projectId: string, snap: H2CipAdjudicatedSnapshot): void {
  if (!projectId || typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(
      `${H2_CIP_CACHE_PREFIX}${projectId}`,
      JSON.stringify({ ...snap, projectId }),
    )
  } catch {
    /* quota / private mode */
  }
}

export function readH2CipSnapshot(projectId: string): H2CipAdjudicatedSnapshot | null {
  if (!projectId || typeof sessionStorage === 'undefined') return null
  try {
    const raw = sessionStorage.getItem(`${H2_CIP_CACHE_PREFIX}${projectId}`)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return buildH2CipSnapshot(parsed)
  } catch {
    return null
  }
}

/** 是否为 H2 / 1604 在建工程审定事件 */
export function isH2CipAdjudicatedEvent(detail: Record<string, any> | null | undefined): boolean {
  if (!detail) return false
  const wp = String(detail.wpCode ?? detail.wp_code ?? '').toUpperCase()
  if (wp === 'H2') return true
  const codes = detail.account_codes
  if (Array.isArray(codes) && codes.some((c) => String(c).startsWith('1604'))) return true
  const ac = String(detail.accountCode ?? detail.account_code ?? '')
  return ac === '1604' || ac.startsWith('1604')
}

/**
 * 从 substantive:adjudicated 载荷解析 CIP 三栏。
 * 兼容 camelCase / snake_case / 嵌套 cip 对象。
 */
export function parseH2CipFromAdjudicatedEvent(
  detail: Record<string, any> | null | undefined,
): H2CipAdjudicatedSnapshot | null {
  if (!isH2CipAdjudicatedEvent(detail)) return null
  const d = detail!
  const nested = d.cip && typeof d.cip === 'object' ? d.cip : null
  const hasExplicit =
    nested
    || d.end_audited != null
    || d.begin_audited != null
    || d.endAudited != null
    || d.beginAudited != null
  if (!hasExplicit) return null
  const endBook = num(
    nested?.endBook ?? nested?.end_book ?? d.end_audited ?? d.endAudited,
  )
  const endImpairment = num(
    nested?.endImpairment ?? nested?.end_impairment ?? d.impair_audited ?? d.impairAudited,
  )
  const beginBook = num(
    nested?.beginBook ?? nested?.begin_book ?? d.begin_audited ?? d.beginAudited,
  )
  const beginImpairment = num(
    nested?.beginImpairment ?? nested?.begin_impairment ?? d.begin_impair_audited ?? d.beginImpairAudited,
  )
  return buildH2CipSnapshot({
    endBook,
    endImpairment,
    beginBook,
    beginImpairment,
    auditedAmount: num(d.auditedAmount ?? d.audited_amount) || endBook,
    projectId: d.projectId ? String(d.projectId) : undefined,
    timestamp: Number(d.timestamp) || Date.now(),
  })
}
