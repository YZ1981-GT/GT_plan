/**
 * G5 跨表汇总辅助 — G5-2 / G5-3 → G5-1 未审数
 */
import { parseNum } from '@/composables/useG5FormulaEngine'
import { readCanonicalRaw } from './g5StorageContract'

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
