/** G11-1 审定表 rowStore 读写辅助 */
import { G11_ADJUDICATION_ITEMS } from './g11Constants'
import { parseNum } from './useG11FormulaEngine'

export type G11AdjRowStore = Record<string, {
  currentUnadjusted?: number
  currentAdjustment?: number
  priorUnadjusted?: number
  priorAdjustment?: number
  reasonAnalysis?: string
  indexRef?: string
}>

export function defaultG11AdjStore(): G11AdjRowStore {
  const s: G11AdjRowStore = {}
  for (const def of G11_ADJUDICATION_ITEMS) {
    s[def.rowKey] = {
      currentUnadjusted: 0,
      currentAdjustment: 0,
      priorUnadjusted: 0,
      priorAdjustment: 0,
      reasonAnalysis: '',
      indexRef: '',
    }
  }
  return s
}

export function parseG11AdjStore(json: string | null | undefined): G11AdjRowStore {
  if (!json) return defaultG11AdjStore()
  try {
    return { ...defaultG11AdjStore(), ...JSON.parse(json) as G11AdjRowStore }
  } catch {
    return defaultG11AdjStore()
  }
}

export function patchG11AdjRow(
  store: G11AdjRowStore,
  rowKey: string,
  patch: Partial<G11AdjRowStore[string]>,
): G11AdjRowStore {
  return {
    ...store,
    [rowKey]: { ...(store[rowKey] ?? {}), ...patch },
  }
}

/** 6111 贷方科目：调整净额 = 贷方 − 借方 */
export function calcG11AdjustmentNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
): number {
  return rows
    .filter((r) => String(r.accountCode ?? '6111').startsWith('6111'))
    .reduce((s, r) => s + parseNum(r.creditAmount) - parseNum(r.debitAmount), 0)
}
