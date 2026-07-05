/** G9-1 审定表 rowStore 读写辅助 */
import { G9_ADJUDICATION_ITEMS, G9_ADJ_WRITEBACK_ROW_KEY } from './g9Constants'
import { parseNum } from './useG9FormulaEngine'

export { G9_ADJ_WRITEBACK_ROW_KEY }

export type G9AdjRowStore = Record<string, {
  openingUnadjusted?: number
  openingAJE?: number
  openingRJE?: number
  closingUnadjusted?: number
  closingAJE?: number
  closingRJE?: number
  reasonAnalysis?: string
  indexRef?: string
}>

export interface G9AdjustmentWriteback {
  rowKey: string
  closingAje: number
  closingRje: number
}

export interface G9AdjustmentEntryLike {
  entryType?: string
  accountCode?: string
  debitAmount?: number
  creditAmount?: number
}

export function defaultG9AdjStore(): G9AdjRowStore {
  const s: G9AdjRowStore = {}
  for (const def of G9_ADJUDICATION_ITEMS) {
    s[def.rowKey] = {
      openingUnadjusted: 0,
      openingAJE: 0,
      openingRJE: 0,
      closingUnadjusted: 0,
      closingAJE: 0,
      closingRJE: 0,
      reasonAnalysis: '',
      indexRef: '',
    }
  }
  return s
}

export function parseG9AdjStore(json: string | null | undefined): G9AdjRowStore {
  if (!json) return defaultG9AdjStore()
  try {
    return { ...defaultG9AdjStore(), ...JSON.parse(json) as G9AdjRowStore }
  } catch {
    return defaultG9AdjStore()
  }
}

export function patchG9AdjRow(
  store: G9AdjRowStore,
  rowKey: string,
  patch: Partial<G9AdjRowStore[string]>,
): G9AdjRowStore {
  return {
    ...store,
    [rowKey]: { ...(store[rowKey] ?? {}), ...patch },
  }
}

export function calcG9AdjustmentNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
): number {
  return rows
    .filter((r) => String(r.accountCode ?? '1504').startsWith('1504'))
    .reduce((s, r) => s + parseNum(r.debitAmount) - parseNum(r.creditAmount), 0)
}

/** 按 AJE/RJE 分别汇总 1504 科目净额（借方−贷方），用于回写 G9-1 */
export function aggregateG9AdjustmentAjeRje(
  rows: G9AdjustmentEntryLike[],
  rowKey = G9_ADJ_WRITEBACK_ROW_KEY,
): G9AdjustmentWriteback {
  let closingAje = 0
  let closingRje = 0
  for (const row of rows) {
    if (!String(row.accountCode ?? '1504').startsWith('1504')) continue
    const net = parseNum(row.debitAmount) - parseNum(row.creditAmount)
    if (row.entryType === 'RJE') closingRje += net
    else closingAje += net
  }
  return { rowKey, closingAje, closingRje }
}

export function applyG9AdjustmentWriteback(
  store: G9AdjRowStore,
  writeback: G9AdjustmentWriteback,
): G9AdjRowStore {
  return patchG9AdjRow(store, writeback.rowKey, {
    closingAJE: writeback.closingAje,
    closingRJE: writeback.closingRje,
  })
}
