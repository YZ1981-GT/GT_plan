/**
 * H10-2 明细 → H10-1 审定「未审」汇总（按来源底稿映射）
 * 保留已有 AJE/RJE；试运行行优先取披露试运行明细净额。
 */
import { H10_SOURCE_WP_TO_ROW_KEY } from './useH10CrossSheet'
import { parseNum } from './useH10FormulaEngine'
import type { H10AdjRowStore } from './h10AdjStorage'
import { patchH10AdjRow } from './h10AdjStorage'

export interface H10DetailLikeRow {
  sourceWp?: string
  disposalGainLoss?: number
  assetType?: string
  assetName?: string
}

export interface H10TrialLikeRow {
  currentIncome?: number
  currentCost?: number
  priorIncome?: number
  priorCost?: number
}

export interface H10FillFromDetailResult {
  nextStore: H10AdjRowStore
  filledKeys: string[]
  currentByKey: Record<string, number>
  trialCurrent: number
  trialPrior: number
}

function trialNet(rows: readonly H10TrialLikeRow[]): { current: number; prior: number } {
  let current = 0
  let prior = 0
  for (const r of rows) {
    current += parseNum(r.currentIncome) - parseNum(r.currentCost)
    prior += parseNum(r.priorIncome) - parseNum(r.priorCost)
  }
  return { current, prior }
}

/** 按 sourceWp 汇总明细处置损益 */
export function aggregateH10DetailByAdjRowKey(
  detailRows: readonly H10DetailLikeRow[],
): Record<string, number> {
  const totals: Record<string, number> = {}
  for (const row of detailRows) {
    const wp = String(row.sourceWp ?? 'OTHER')
    const rowKey = H10_SOURCE_WP_TO_ROW_KEY[wp]
    if (!rowKey) continue
    totals[rowKey] = (totals[rowKey] ?? 0) + parseNum(row.disposalGainLoss)
  }
  return totals
}

/**
 * 将 H10-2 明细汇总写入审定 store 的 currentUnadjusted（保留 AJE/RJE）。
 * 若提供 trialRows，则写入 trial_operation_sales 的本期/上期未审。
 */
export function applyH10DetailToAdjStore(
  store: H10AdjRowStore,
  detailRows: readonly H10DetailLikeRow[],
  trialRows?: readonly H10TrialLikeRow[],
): H10FillFromDetailResult {
  const currentByKey = aggregateH10DetailByAdjRowKey(detailRows)
  let next = { ...store }
  const filledKeys: string[] = []

  for (const [rowKey, amount] of Object.entries(currentByKey)) {
    next = patchH10AdjRow(next, rowKey, {
      currentUnadjusted: amount,
      indexRef: next[rowKey]?.indexRef || 'H10-2',
    })
    filledKeys.push(rowKey)
  }

  const { current: trialCurrent, prior: trialPrior } = trialNet(trialRows ?? [])
  if (Math.abs(trialCurrent) > 0.005 || Math.abs(trialPrior) > 0.005 || (trialRows && trialRows.length > 0)) {
    // 有试运行明细时始终回写（含全 0，便于清空）
    if (trialRows && trialRows.length > 0) {
      next = patchH10AdjRow(next, 'trial_operation_sales', {
        currentUnadjusted: trialCurrent,
        priorUnadjusted: trialPrior,
        indexRef: next.trial_operation_sales?.indexRef || '附注-试运行',
      })
      if (!filledKeys.includes('trial_operation_sales')) filledKeys.push('trial_operation_sales')
    }
  }

  return { nextStore: next, filledKeys, currentByKey, trialCurrent, trialPrior }
}
