/**
 * G12 交叉验证 — G12-1↔G12-2 汇总 + G12-2↔G12-4 FV测试
 */
import { parseNum } from './useG12FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

const TOLERANCE = 0.01

export interface G12FvCrossMismatch {
  hedgeRelationId: string
  field: 'instrumentFVChange' | 'itemFVChange'
  hedgeValue: number
  fvTestValue: number
  variance: number
}

export interface G12AdjudicationHedgeMismatch {
  rowKey: string
  label: string
  adjudicationAudited: number
  hedgeAudited: number
  variance: number
}

const HEDGE_TOTAL_FIELD: Record<string, 'instrumentFVChange' | 'itemFVChange' | 'ineffectiveness' | 'profitLossAmount'> = {
  instrument_fv: 'instrumentFVChange',
  item_fv: 'itemFVChange',
  ineffectiveness: 'ineffectiveness',
  net_hedge: 'profitLossAmount',
}

export function findG12AdjudicationHedgeMismatches(
  adjudicationRows: Array<{ rowKey: string; label: string; currentUnadjusted: number }>,
  hedgeTotals: {
    instrumentFVChange: number
    itemFVChange: number
    ineffectiveness: number
    profitLossAmount: number
  },
): G12AdjudicationHedgeMismatch[] {
  const out: G12AdjudicationHedgeMismatch[] = []
  for (const row of adjudicationRows) {
    if (row.rowKey === 'total' || row.rowKey === 'other') continue
    const field = HEDGE_TOTAL_FIELD[row.rowKey]
    if (!field) continue
    const hedgeAudited = hedgeTotals[field]
    const variance = row.currentUnadjusted - hedgeAudited
    if (Math.abs(variance) > TOLERANCE) {
      out.push({
        rowKey: row.rowKey,
        label: row.label,
        adjudicationAudited: row.currentUnadjusted,
        hedgeAudited,
        variance,
      })
    }
  }
  return out
}

export function formatG12AdjudicationHedgeCrossMessage(mismatches: G12AdjudicationHedgeMismatch[]): string | null {
  if (!mismatches.length) return null
  const parts = mismatches.map(
    (m) => `${m.label}：未审 ${m.adjudicationAudited.toFixed(2)} ≠ G12-2汇总 ${m.hedgeAudited.toFixed(2)}（差异 ${m.variance.toFixed(2)}）`,
  )
  return `G12-1 与 G12-2 套期明细汇总不一致 — ${parts.join('；')}`
}

export function hasG12HedgeDetailData(allResponses: Map<string, ChecklistResponse>): boolean {
  const raw = allResponses.get('G12-hedge-detail-rows')?.remark
  if (!raw) return false
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) && arr.length > 0
  } catch {
    return false
  }
}

export function hasG12FvTestData(allResponses: Map<string, ChecklistResponse>): boolean {
  const raw = allResponses.get('G12-fv-test-rows')?.remark
  if (!raw) return false
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) && arr.length > 0
  } catch {
    return false
  }
}

export function formatG12FvCrossSummaryMessage(mismatches: G12FvCrossMismatch[]): string | null {
  if (!mismatches.length) return null
  const first = mismatches[0]
  const fieldLabel = first.field === 'instrumentFVChange' ? '工具FV变动' : '项目FV变动'
  const head = `${first.hedgeRelationId} · ${fieldLabel}：G12-2=${first.hedgeValue.toFixed(2)} vs G12-4=${first.fvTestValue.toFixed(2)}（差 ${first.variance.toFixed(2)}）`
  if (mismatches.length === 1) {
    return `G12-2 与 G12-4 公允价值测试不一致 — ${head}`
  }
  return `G12-2 与 G12-4 公允价值测试不一致 — ${mismatches.length} 处差异；${head}`
}

export function parseG12FvTestRows(allResponses: Map<string, ChecklistResponse>): Map<string, { instrumentFVChange: number; itemFVChange: number }> {
  const map = new Map<string, { instrumentFVChange: number; itemFVChange: number }>()
  const raw = allResponses.get('G12-fv-test-rows')?.remark
  if (!raw) return map
  try {
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return map
    for (const r of arr) {
      const id = String(r.hedgeRelationId ?? '').trim()
      if (!id) continue
      map.set(id, {
        instrumentFVChange: parseNum(r.instrumentFVChange ?? (parseNum(r.instrumentClosingFV) - parseNum(r.instrumentOpeningFV))),
        itemFVChange: parseNum(r.itemFVChange ?? (parseNum(r.itemClosingFV) - parseNum(r.itemOpeningFV))),
      })
    }
  } catch { /* ignore */ }
  return map
}

export function findG12FvCrossMismatches(
  hedgeRows: Array<{ hedgeRelationId: string; instrumentFVChange: number; itemFVChange: number }>,
  allResponses: Map<string, ChecklistResponse>,
): G12FvCrossMismatch[] {
  const fvMap = parseG12FvTestRows(allResponses)
  const out: G12FvCrossMismatch[] = []
  for (const h of hedgeRows) {
    const id = h.hedgeRelationId?.trim()
    if (!id) continue
    const fv = fvMap.get(id)
    if (!fv) continue
    for (const field of ['instrumentFVChange', 'itemFVChange'] as const) {
      const variance = h[field] - fv[field]
      if (Math.abs(variance) > TOLERANCE) {
        out.push({ hedgeRelationId: id, field, hedgeValue: h[field], fvTestValue: fv[field], variance })
      }
    }
  }
  return out
}
