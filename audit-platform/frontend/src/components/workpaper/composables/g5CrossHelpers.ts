/**
 * G5 跨表汇总辅助 — G5-2 / G5-3 → G5-1 未审数
 */
import { parseNum } from '@/composables/useG5FormulaEngine'
import { G5_ITEM_IDS, readCanonicalRaw } from './g5StorageContract'

export interface G5GrossAggregate {
  individualClosing: number
  businessClosing: number
  customerClosing: number
  oneYearClosing: number
  /** 一年内对应明细债务人名称（用于坏账联动） */
  oneYearDebtors: Set<string>
}

export interface G5ProvisionAggregate {
  individualClosing: number
  businessClosing: number
  customerClosing: number
  oneYearClosing: number
  /** G5-2「一年内」债务人在 G5-3 未匹配到同名行 */
  unmatchedOneYearDebtors: string[]
}

/** 名称归一：去空白，便于 G5-2 / G5-3 勾稽 */
export function normalizeDebtorName(name: string): string {
  return String(name || '').trim().replace(/\s+/g, '')
}

function isWithinOneYearRow(r: any): boolean {
  if (r?.isWithinOneYear === true || r?.isWithinOneYear === '是' || r?.isWithinOneYear === 1) return true
  // 账龄「1年内」段有金额且约占净额/余额主体时，视为一年内
  const aging = r?.agingAudited
  if (aging && typeof aging === 'object') {
    const within = parseNum(aging.within1 ?? aging['1年内'] ?? r.aging1Year)
    const bal = parseNum(r.closingBalance ?? r.netAmount)
    if (within > 0 && bal > 0 && within / bal >= 0.95) return true
  }
  const mat = String(r?.maturityDate || '')
  if (mat && /^\d{4}-\d{2}-\d{2}/.test(mat)) {
    const days = (new Date(mat).getTime() - Date.now()) / 86400000
    if (days >= 0 && days <= 365) return true
  }
  return false
}

/** 供跨循环（如 G7-16）判断是否一年内到期（不构成长期净投资） */
export { isWithinOneYearRow }

export function aggregateGrossFromG52(list: any[]): G5GrossAggregate {
  const result: G5GrossAggregate = {
    individualClosing: 0,
    businessClosing: 0,
    customerClosing: 0,
    oneYearClosing: 0,
    oneYearDebtors: new Set(),
  }
  if (!Array.isArray(list)) return result

  for (const r of list) {
    const bal = parseNum(r.closingBalance ?? r.netAmount)
    const name = normalizeDebtorName(r.debtorName || '')
    const bt = String(r.businessType || '')
    // 明细默认均为组合口径：租赁/分期→业务类型；保理/其他→客户类型
    // 「单项」由坏账表决定，原值侧先全部进组合；若行上标明 individual 则进单项
    if (r.assessmentMethod === 'individual' || r.provisionMethod === 'individual') {
      result.individualClosing += bal
    } else if (bt === 'lease' || bt === 'installment') {
      result.businessClosing += bal
    } else {
      result.customerClosing += bal
    }
    if (isWithinOneYearRow(r)) {
      result.oneYearClosing += bal
      if (name) result.oneYearDebtors.add(name)
    }
  }
  return result
}

export function aggregateProvisionFromG53(
  list: any[],
  oneYearDebtors?: Set<string>,
): G5ProvisionAggregate {
  const result: G5ProvisionAggregate = {
    individualClosing: 0,
    businessClosing: 0,
    customerClosing: 0,
    oneYearClosing: 0,
    unmatchedOneYearDebtors: [],
  }
  if (!Array.isArray(list)) return result

  const matchedOneYear = new Set<string>()

  for (const r of list) {
    // 跳过展示分区行
    if (r?.kind === 'section_header' || r?.kind === 'subtotal' || r?.kind === 'total') continue

    // 滚动态：closingAudited；旧 ECL：adjustedProvision / unadjustedProvision
    const amt = parseNum(
      r.closingAudited
      ?? r.adjustedProvision
      ?? r.unadjustedProvision
      ?? computeClosingAuditedFallback(r),
    )
    const name = normalizeDebtorName(r.item || r.debtorOrGroup || r.debtor || '')
    const isIndividual =
      r.category === 'individual'
      || r.provisionMethod === 'individual'

    if (isIndividual) {
      result.individualClosing += amt
    } else if (r.portfolioType === 'customer') {
      result.customerClosing += amt
    } else {
      // portfolio / group 默认 → 业务类型组合
      result.businessClosing += amt
    }
    if (oneYearDebtors?.size && name && oneYearDebtors.has(name)) {
      result.oneYearClosing += amt
      matchedOneYear.add(name)
    }
  }

  if (oneYearDebtors?.size) {
    result.unmatchedOneYearDebtors = [...oneYearDebtors].filter((n) => !matchedOneYear.has(n))
  }

  return result
}

/** 无 closingAudited 时按滚动态公式推算 */
function computeClosingAuditedFallback(r: any): number {
  if (r?.openingUnadjusted == null && r?.provisionIncrease == null) return 0
  const openingAudited =
    parseNum(r.openingUnadjusted) + parseNum(r.openingAdjustment)
  const closingUnadjusted =
    openingAudited
    + parseNum(r.provisionIncrease)
    + parseNum(r.otherIncrease)
    - parseNum(r.reversal)
    - parseNum(r.writeOff)
    - parseNum(r.otherDecrease)
  return closingUnadjusted + parseNum(r.closingAdjustment)
}

/** 从 checklist conclusion/remark JSON 解析数组（兼容旧仅 remark） */
export function parseRowsRemark(
  raw:
    | string
    | null
    | undefined
    | { conclusion?: string | null; remark?: string | null },
): any[] {
  const text =
    raw == null
      ? null
      : typeof raw === 'string'
        ? raw
        : readCanonicalRaw(raw)
  if (!text) return []
  try {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) return parsed
    if (Array.isArray(parsed?.rows)) return parsed.rows
    if (Array.isArray(parsed?.groups)) return parsed.groups
  } catch { /* ignore */ }
  return []
}

/**
 * 从 G5-2 明细构建「实质净投资长期应收」Map（债务人归一名 → 金额）。
 * 默认优先关联方；一年内到期部分剔除。
 */
export function buildG52NetInvestmentMap(
  rows: any[],
  opts?: { relatedPartyOnly?: boolean },
): Map<string, number> {
  const relatedOnly = opts?.relatedPartyOnly !== false
  const map = new Map<string, number>()
  if (!Array.isArray(rows)) return map
  for (const r of rows) {
    if (!r || r.kind === 'section_header' || r.kind === 'subtotal' || r.kind === 'total') continue
    if (isWithinOneYearRow(r)) continue
    const related = r.isRelatedParty === true || r.isRelatedParty === '是' || r.isRelatedParty === 1
    if (relatedOnly && !related) continue
    const name = normalizeDebtorName(r.debtorName || r.counterpartyName || '')
    if (!name) continue
    const amt = parseNum(r.netAmount ?? r.closingBalance ?? r.auditedClosing)
    if (amt <= 0) continue
    map.set(name, Math.round(((map.get(name) || 0) + amt) * 100) / 100)
  }
  return map
}

/** 解析 G5 主底稿 wp_id（G5-2 / G5-1 / G5） */
export async function resolveG5WorkpaperId(
  projectId: string,
  fallbackWpId?: string,
): Promise<string | null> {
  if (!projectId) return fallbackWpId || null
  const http = (await import('@/utils/http')).default
  for (const sheetCode of ['G5-2', 'G5-1', 'G5']) {
    try {
      const { data } = await http.get('/api/acnr/resolve-instance', {
        params: { project_id: projectId, parent: 'G5', sheet_code: sheetCode },
        _silent: true,
      } as any)
      const resolved = data?.data?.wp_id ?? data?.wp_id
      if (resolved) return String(resolved)
    } catch { /* try next */ }
  }
  return fallbackWpId || null
}

/** 拉取 G5-2 并汇总为债务人→实质长期应收 Map */
export async function fetchG52NetInvestmentByDebtor(
  projectId: string,
  opts?: { relatedPartyOnly?: boolean },
): Promise<Map<string, number>> {
  const empty = new Map<string, number>()
  if (!projectId) return empty
  try {
    const { fetchChecklistResponseMap } = await import('./g4CrossHelpers')
    const wpId = await resolveG5WorkpaperId(projectId)
    if (!wpId) return empty
    const map = await fetchChecklistResponseMap(wpId)
    const rows = parseRowsRemark(map.get(G5_ITEM_IDS.G5_2_ROWS) || map.get('G5-2-rows'))
    return buildG52NetInvestmentMap(rows, opts)
  } catch {
    return empty
  }
}

/** TB 1531 辅助核算（客户）→ 债务人余额 Map，作 G5-2 缺失时的降级 */
export async function fetchTb1531AuxByCustomer(
  projectId: string,
  year?: number,
): Promise<Map<string, number>> {
  const out = new Map<string, number>()
  if (!projectId) return out
  try {
    const http = (await import('@/utils/http')).default
    const { resolveAuditYearNumber } = await import('./workpaperAuditYear')
    const y = year
      ?? resolveAuditYearNumber(undefined, new Date().getFullYear() - 1)
      ?? (new Date().getFullYear() - 1)
    const { data } = await http.get(`/api/projects/${projectId}/ledger/aux-balance-detail`, {
      params: {
        account_code: '1531',
        dim_type: '客户',
        year: y,
      },
      _silent: true,
    } as any)
    const rows: any[] = Array.isArray(data) ? data : (data?.data ?? data?.items ?? [])
    for (const r of rows) {
      const name = normalizeDebtorName(r.aux_name ?? r.auxName ?? r.name ?? '')
      if (!name) continue
      const amt = parseNum(r.closing_balance ?? r.closingBalance ?? r.ending_balance)
      if (amt <= 0) continue
      out.set(name, Math.round(((out.get(name) || 0) + amt) * 100) / 100)
    }
  } catch { /* ignore */ }
  return out
}
