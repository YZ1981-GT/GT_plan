/**
 * useH10CrossSheet — H10 跨 sheet / 跨底稿联动
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcAuditedAmount } from './useH10FormulaEngine'
import { H10_ADJUDICATION_ITEMS } from './h10Constants'
import type { ChecklistResponse } from './useF1FormData'

/** 明细来源底稿 → H10-1 审定行 rowKey */
export const H10_SOURCE_WP_TO_ROW_KEY: Record<string, string> = {
  H1: 'fixed_asset_disposal',
  H3: 'construction_disposal',
  H5: 'productive_bio_disposal',
  H7: 'productive_bio_disposal',
  H8: 'intangible_disposal',
  H6: 'fixed_asset_disposal',
}

function safeParseArray(remark: string | null | undefined): any[] {
  if (!remark) return []
  try {
    const parsed = JSON.parse(remark)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function readAdjRowAmount(storeRaw: string | null | undefined, rowKey: string): number {
  if (!storeRaw) return 0
  try {
    const store = JSON.parse(storeRaw)
    const raw = store[rowKey] ?? {}
    return calcAuditedAmount(
      parseNum(raw.currentUnadjusted),
      parseNum(raw.currentAje),
      parseNum(raw.currentRje),
    )
  } catch {
    return 0
  }
}

export interface H10CrossMatchResult {
  diff: number
  isMatch: boolean
  adjudicationTotal: number
  detailTotal: number
}

export interface H10H6CrossResult {
  diff: number
  isMatch: boolean
  h10FixedAssetTotal: number
  h6NetGainLoss: number | null
  h6Available: boolean
}

export interface H10SourceWpMismatch {
  sourceWp: string
  rowKey: string
  detailTotal: number
  adjudicationTotal: number
  diff: number
  isMatch: boolean
}

export function useH10CrossSheet(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
}) {
  const storeRaw = computed(() => opts.allResponses.value.get('H10-adj-rows')?.remark)

  const adjudicationVsDetail: ComputedRef<H10CrossMatchResult> = computed(() => {
    let adjudicationTotal = 0
    if (storeRaw.value) {
      try {
        const store = JSON.parse(storeRaw.value)
        for (const def of H10_ADJUDICATION_ITEMS) {
          const raw = store[def.rowKey] ?? {}
          adjudicationTotal += calcAuditedAmount(
            parseNum(raw.currentUnadjusted),
            parseNum(raw.currentAje),
            parseNum(raw.currentRje),
          )
        }
      } catch { /* ignore */ }
    } else {
      adjudicationTotal = parseNum(opts.allResponses.value.get('H10-1-adjudicated-amount')?.conclusion)
    }

    const detailRows = safeParseArray(opts.allResponses.value.get('H10-detail-rows')?.remark)
    const detailTotal = calcSubtotal(detailRows.map((r) => parseNum(r.disposalGainLoss)))
    const diff = adjudicationTotal - detailTotal
    return {
      diff,
      isMatch: Math.abs(diff) < 0.01,
      adjudicationTotal,
      detailTotal,
    }
  })

  const h10VsH6: ComputedRef<H10H6CrossResult> = computed(() => {
    const h10FixedAssetTotal = readAdjRowAmount(storeRaw.value, 'fixed_asset_disposal')

    const h6Raw = opts.allResponses.value.get('H6-detail-rows')?.remark
      ?? opts.allResponses.value.get('H6-clearing-rows')?.remark
    let h6NetGainLoss: number | null = null
    if (h6Raw) {
      try {
        const rows = JSON.parse(h6Raw)
        if (Array.isArray(rows)) {
          h6NetGainLoss = calcSubtotal(rows.map((r: any) => parseNum(r.netGainLoss ?? r.disposalGainLoss)))
        }
      } catch { /* ignore */ }
    }

    const h6Available = h6NetGainLoss != null
    const diff = h6Available ? h10FixedAssetTotal - (h6NetGainLoss ?? 0) : 0
    return {
      diff,
      isMatch: !h6Available || Math.abs(diff) < 0.01,
      h10FixedAssetTotal,
      h6NetGainLoss,
      h6Available,
    }
  })

  const sourceWpMismatches: ComputedRef<H10SourceWpMismatch[]> = computed(() => {
    const detailRows = safeParseArray(opts.allResponses.value.get('H10-detail-rows')?.remark)
    const detailByWp: Record<string, number> = {}
    for (const row of detailRows) {
      const wp = String(row.sourceWp ?? 'OTHER')
      if (wp === 'OTHER') continue
      detailByWp[wp] = (detailByWp[wp] ?? 0) + parseNum(row.disposalGainLoss)
    }

    const seen = new Set<string>()
    const mismatches: H10SourceWpMismatch[] = []

    for (const [sourceWp, rowKey] of Object.entries(H10_SOURCE_WP_TO_ROW_KEY)) {
      if (seen.has(rowKey)) continue
      seen.add(rowKey)
      const detailTotal = Object.entries(detailByWp)
        .filter(([wp]) => H10_SOURCE_WP_TO_ROW_KEY[wp] === rowKey)
        .reduce((s, [, amt]) => s + amt, 0)
      if (detailTotal === 0) continue
      const adjudicationTotal = readAdjRowAmount(storeRaw.value, rowKey)
      const diff = adjudicationTotal - detailTotal
      mismatches.push({
        sourceWp,
        rowKey,
        detailTotal,
        adjudicationTotal,
        diff,
        isMatch: Math.abs(diff) < 0.01,
      })
    }

    return mismatches
  })

  const hasSourceWpMismatch = computed(() =>
    sourceWpMismatches.value.some((m) => !m.isMatch),
  )

  const sourceWpTotals = computed(() => {
    const detailRows = safeParseArray(opts.allResponses.value.get('H10-detail-rows')?.remark)
    const totals: Record<string, number> = {}
    for (const row of detailRows) {
      const wp = row.sourceWp || 'OTHER'
      totals[wp] = (totals[wp] ?? 0) + parseNum(row.disposalGainLoss)
    }
    return Object.entries(totals).map(([type, amount]) => ({
      type,
      amount,
      diff: 0,
      isMatch: true,
    }))
  })

  return {
    adjudicationVsDetail,
    h10VsH6,
    h10VsSourceWps: sourceWpTotals,
    sourceWpMismatches,
    hasSourceWpMismatch,
  }
}
