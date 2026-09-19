/**
 * useH10CrossSheet — H10 跨 sheet / 跨底稿联动
 */
import { computed, ref, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcAuditedAmount } from './useH10FormulaEngine'
import { H10_ADJUDICATION_ITEMS } from './h10Constants'
import type { ChecklistResponse } from './useF1FormData'
import { pullH6ClearingNetForH10 } from './h10RelatedH6Pull'

/** 明细来源底稿 → H10-1 审定行 rowKey（H8=使用权、I1=无形资产） */
export const H10_SOURCE_WP_TO_ROW_KEY: Record<string, string> = {
  H1: 'fixed_asset_disposal',
  H2: 'construction_disposal',
  H5: 'oil_gas_disposal',
  H6: 'fixed_asset_disposal',
  H7: 'productive_bio_disposal',
  H8: 'rou_disposal',
  I1: 'intangible_disposal',
  DR: 'debt_restructuring_disposal',
  NM: 'non_monetary_exchange',
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

function sumLocalH6Net(allResponses: Map<string, ChecklistResponse>): number | null {
  for (const key of ['H6-2-rows', 'H6-detail-rows', 'H6-clearing-rows']) {
    const raw = allResponses.get(key)?.remark
    if (!raw) continue
    try {
      const rows = JSON.parse(raw)
      if (!Array.isArray(rows) || !rows.length) continue
      return calcSubtotal(rows.map((r: any) =>
        parseNum(r.netGainLoss ?? r.gainLoss ?? r.disposalGainLoss ?? r.toDisposalGain),
      ))
    } catch { /* next */ }
  }
  return null
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
  h6Source: 'local' | 'remote' | 'none'
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
  projectId?: Ref<string | undefined>
}) {
  const storeRaw = computed(() => opts.allResponses.value.get('H10-adj-rows')?.remark)
  /** 跨 WP 拉取的 H6 净损益（优先于本 WP 内偶然存在的 H6 键） */
  const remoteH6Net = ref<number | null>(null)
  const remoteH6Msg = ref('')
  const h6PullLoading = ref(false)

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
    const detailTotal = calcSubtotal(detailRows.map((r) => parseNum(r.disposalGainLoss ?? r.disposalIncome)))
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
    const local = sumLocalH6Net(opts.allResponses.value)
    const h6NetGainLoss = remoteH6Net.value != null ? remoteH6Net.value : local
    const h6Source: H10H6CrossResult['h6Source'] =
      remoteH6Net.value != null ? 'remote' : local != null ? 'local' : 'none'
    const h6Available = h6NetGainLoss != null
    const diff = h6Available ? h10FixedAssetTotal - (h6NetGainLoss ?? 0) : 0
    return {
      diff,
      isMatch: !h6Available || Math.abs(diff) < 0.01,
      h10FixedAssetTotal,
      h6NetGainLoss,
      h6Available,
      h6Source,
    }
  })

  async function refreshH6CrossCheck(): Promise<H10H6CrossResult> {
    const pid = opts.projectId?.value || ''
    if (!pid) {
      remoteH6Msg.value = '缺少 projectId'
      return h10VsH6.value
    }
    h6PullLoading.value = true
    try {
      const pull = await pullH6ClearingNetForH10(pid)
      remoteH6Msg.value = pull.message
      if (pull.status === 'ok' && pull.netGainLoss != null) {
        remoteH6Net.value = pull.netGainLoss
      } else if (pull.status === 'empty') {
        remoteH6Net.value = 0
      }
    } finally {
      h6PullLoading.value = false
    }
    return h10VsH6.value
  }

  const sourceWpMismatches: ComputedRef<H10SourceWpMismatch[]> = computed(() => {
    const detailRows = safeParseArray(opts.allResponses.value.get('H10-detail-rows')?.remark)
    const detailByWp: Record<string, number> = {}
    for (const row of detailRows) {
      const wp = String(row.sourceWp ?? 'OTHER')
      if (wp === 'OTHER') continue
      detailByWp[wp] = (detailByWp[wp] ?? 0) + parseNum(row.disposalGainLoss ?? row.disposalIncome)
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
      totals[wp] = (totals[wp] ?? 0) + parseNum(row.disposalGainLoss ?? row.disposalIncome)
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
    refreshH6CrossCheck,
    h6PullLoading,
    remoteH6Msg,
  }
}
