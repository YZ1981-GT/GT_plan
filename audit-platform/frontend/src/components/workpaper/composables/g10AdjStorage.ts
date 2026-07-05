/** G10-1 审定表 rowStore 读写辅助 */
import { G10_ADJUDICATION_ITEMS } from './g10Constants'
import { parseNum } from './useG10FormulaEngine'

export type G10AdjRowStore = Record<string, {
  openingUnadjusted?: number
  openingAdjustment?: number
  periodCredit?: number
  periodDebit?: number
  closingAdjustment?: number
  reasonAnalysis?: string
  indexRef?: string
}>

export function defaultG10AdjStore(): G10AdjRowStore {
  const s: G10AdjRowStore = {}
  for (const def of G10_ADJUDICATION_ITEMS) {
    s[def.rowKey] = {
      openingUnadjusted: 0,
      openingAdjustment: 0,
      periodCredit: 0,
      periodDebit: 0,
      closingAdjustment: 0,
      reasonAnalysis: '',
      indexRef: '',
    }
  }
  return s
}

export function parseG10AdjStore(json: string | null | undefined): G10AdjRowStore {
  if (!json) return defaultG10AdjStore()
  try {
    return { ...defaultG10AdjStore(), ...JSON.parse(json) as G10AdjRowStore }
  } catch {
    return defaultG10AdjStore()
  }
}

export function patchG10AdjRow(
  store: G10AdjRowStore,
  rowKey: string,
  patch: Partial<G10AdjRowStore[string]>,
): G10AdjRowStore {
  return {
    ...store,
    [rowKey]: { ...(store[rowKey] ?? {}), ...patch },
  }
}

/** 2101 贷方科目：调整净额 = 贷方 − 借方 */
export function calcG10AdjustmentNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
): number {
  return rows
    .filter((r) => String(r.accountCode ?? '2101').startsWith('2101'))
    .reduce((s, r) => s + parseNum(r.creditAmount) - parseNum(r.debitAmount), 0)
}
