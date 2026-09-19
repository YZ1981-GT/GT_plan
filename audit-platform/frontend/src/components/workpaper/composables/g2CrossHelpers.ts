/**
 * G2 跨表取数辅助 — G2-2 明细 / G2-3 坏账滚动态
 */
import { parseNum } from './useG2IntRecFormulaEngine'

export const G2_DETAIL_STORAGE_KEY = 'G2-2-detail-rows'
export const G2_BAD_DEBT_STORAGE_KEY = 'G2-3-bad-debt-rows'
export const G2_ADJ_STORAGE_KEY = 'G2-1-rows'

export interface G2DetailPartial {
  id: string
  investTarget: string
  investType: string
  netReceivable: number
  bookValue: number
  eclStage: string
  agingPrior: Record<string, number>
  agingAudited: Record<string, number>
  remark: string
}

export interface G2BadDebtLeafPartial {
  id: string
  category: 'individual' | 'portfolio'
  item: string
  agingKey?: string
  openingUnadjusted: number
  openingAdjustment: number
  openingAudited: number
  provisionIncrease: number
  otherIncrease: number
  reversal: number
  writeOff: number
  otherDecrease: number
  closingAdjustment: number
  closingUnadjusted: number
  closingAudited: number
  reason: string
}

function sumAgingBucket(bucket: Record<string, number> | undefined): number {
  if (!bucket || typeof bucket !== 'object') return 0
  return Object.values(bucket).reduce((s, v) => s + parseNum(v), 0)
}

function isWithin1Key(key: string): boolean {
  return key === 'within1' || /^within\s*1$/i.test(key)
}

/** 从 allResponses 解析 G2-2 明细行 */
export function loadG2DetailPartials(allResponses: Map<string, any>): G2DetailPartial[] {
  const raw = allResponses.get(G2_DETAIL_STORAGE_KEY)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => {
      const face = parseNum(r.faceValue)
      const rate = parseNum(r.couponRate)
      const start = String(r.accrualStart || '')
      const end = String(r.accrualEnd || '')
      let accruedDays = 0
      if (start && end) {
        const a = new Date(start).getTime()
        const b = new Date(end).getTime()
        if (Number.isFinite(a) && Number.isFinite(b) && b > a) {
          accruedDays = Math.floor((b - a) / 86400000)
        }
      }
      const accruedInterest = (face * rate / 100 * accruedDays) / 365
      const netReceivable = accruedInterest - parseNum(r.receivedInterest)
      return {
        id: String(r.id || `d-${i}`),
        investTarget: String(r.investTarget || ''),
        investType: String(r.investType || ''),
        netReceivable: Number.isFinite(netReceivable) ? netReceivable : parseNum(r.netReceivable),
        bookValue: parseNum(r.bookValue),
        eclStage: String(r.eclStage || 'Stage1'),
        agingPrior: (r.agingPrior && typeof r.agingPrior === 'object') ? r.agingPrior : {},
        agingAudited: (r.agingAudited && typeof r.agingAudited === 'object') ? r.agingAudited : {},
        remark: String(r.remark || ''),
      }
    })
  } catch {
    return []
  }
}

/** Stage3 → 单项；其余 → 组合 */
export function aggregateGrossFromDetail(details: G2DetailPartial[]): {
  individualOpening: number
  individualClosing: number
  collectiveOpening: number
  collectiveClosing: number
} {
  let individualOpening = 0
  let individualClosing = 0
  let collectiveOpening = 0
  let collectiveClosing = 0
  for (const d of details) {
    const opening = sumAgingBucket(d.agingPrior) || 0
    const closing = d.netReceivable || d.bookValue || sumAgingBucket(d.agingAudited)
    if (d.eclStage === 'Stage3') {
      individualOpening += opening
      individualClosing += closing
    } else {
      collectiveOpening += opening
      collectiveClosing += closing
    }
  }
  return { individualOpening, individualClosing, collectiveOpening, collectiveClosing }
}

function computeClosing(r: any): { openingAudited: number; closingUnadjusted: number; closingAudited: number } {
  const openingUnadjusted = parseNum(r.openingUnadjusted)
  const openingAdjustment = parseNum(r.openingAdjustment)
  const openingAudited = openingUnadjusted + openingAdjustment
  const closingUnadjusted =
    openingAudited +
    parseNum(r.provisionIncrease) +
    parseNum(r.otherIncrease) -
    parseNum(r.reversal) -
    parseNum(r.writeOff) -
    parseNum(r.otherDecrease)
  const closingAudited = closingUnadjusted + parseNum(r.closingAdjustment)
  return { openingAudited, closingUnadjusted, closingAudited }
}

/** 从 allResponses 解析 G2-3 leaf 行 */
export function loadG2BadDebtLeaves(allResponses: Map<string, any>): G2BadDebtLeafPartial[] {
  const raw = allResponses.get(G2_BAD_DEBT_STORAGE_KEY)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    let leaves: any[] = []
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && parsed.version === 2) {
      leaves = [...(parsed.individual || []), ...(parsed.portfolio || [])]
    } else if (Array.isArray(parsed)) {
      leaves = parsed.filter((r) => r && (r.category === 'individual' || r.category === 'portfolio' || 'openingUnadjusted' in r))
    }
    return leaves.map((r: any, i: number) => {
      const derived = computeClosing(r)
      return {
        id: String(r.id || `bd-${i}`),
        category: r.category === 'portfolio' ? 'portfolio' as const : 'individual' as const,
        item: String(r.item || r.investTarget || ''),
        agingKey: r.agingKey ? String(r.agingKey) : undefined,
        openingUnadjusted: parseNum(r.openingUnadjusted),
        openingAdjustment: parseNum(r.openingAdjustment),
        openingAudited: derived.openingAudited,
        provisionIncrease: parseNum(r.provisionIncrease),
        otherIncrease: parseNum(r.otherIncrease),
        reversal: parseNum(r.reversal),
        writeOff: parseNum(r.writeOff),
        otherDecrease: parseNum(r.otherDecrease),
        closingAdjustment: parseNum(r.closingAdjustment),
        closingUnadjusted: derived.closingUnadjusted,
        closingAudited: derived.closingAudited,
        reason: String(r.reason || r.remark || ''),
      }
    })
  } catch {
    return []
  }
}

export function aggregateProvisionFromBadDebt(leaves: G2BadDebtLeafPartial[]): {
  individualOpening: number
  individualClosing: number
  collectiveOpening: number
  collectiveClosing: number
} {
  let individualOpening = 0
  let individualClosing = 0
  let collectiveOpening = 0
  let collectiveClosing = 0
  for (const r of leaves) {
    if (r.category === 'individual') {
      individualOpening += r.openingAudited
      individualClosing += r.closingAudited
    } else {
      collectiveOpening += r.openingAudited
      collectiveClosing += r.closingAudited
    }
  }
  return { individualOpening, individualClosing, collectiveOpening, collectiveClosing }
}

/** G2-2 → G2-6：账龄超过 1 年的明细 */
export interface G2LongTermImportRow {
  debtorName: string
  openingBalance: number
  closingBalance: number
  aging: string
  unrecoveredReason: string
  auditedBalance: number
}

export function filterLongTermFromDetail(details: G2DetailPartial[]): G2LongTermImportRow[] {
  const out: G2LongTermImportRow[] = []
  for (const d of details) {
    const audited = d.agingAudited || {}
    let longSum = 0
    let topLabel = ''
    let topAmt = 0
    for (const [key, val] of Object.entries(audited)) {
      const amt = parseNum(val)
      if (amt <= 0) continue
      if (isWithin1Key(key)) continue
      longSum += amt
      if (amt > topAmt) {
        topAmt = amt
        topLabel = key
      }
    }
    // 无 nested 账龄时：用备注/类型无法判断，跳过；若净额>0 且无 within1 主导则不导入
    if (longSum <= 0.005) continue
    // 标签：优先用金额最大的超1年段 key 做展示（前端可用枚举 label 覆盖）
    const labelMap: Record<string, string> = {
      y1to2: '1-2年',
      y2to3: '2-3年',
      y3to4: '3-4年',
      y4to5: '4-5年',
      over3: '3年以上',
      over5: '5年以上',
    }
    out.push({
      debtorName: d.investTarget || d.investType || '未命名',
      openingBalance: sumAgingBucket(d.agingPrior),
      closingBalance: longSum || d.netReceivable || d.bookValue,
      aging: labelMap[topLabel] || topLabel || '1年以上',
      unrecoveredReason: d.remark || '',
      auditedBalance: longSum || d.netReceivable || d.bookValue,
    })
  }
  return out
}
