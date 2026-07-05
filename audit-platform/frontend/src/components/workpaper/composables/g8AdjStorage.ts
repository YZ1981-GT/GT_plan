/** G8-1 审定表 rowStore 读写辅助 */
import { G8_ADJUDICATION_ITEMS, G8_ADJ_WRITEBACK_ROW_KEY } from './g8Constants'
import { parseNum } from './useG8FormulaEngine'

export { G8_ADJ_WRITEBACK_ROW_KEY }

export type G8AdjRowStore = Record<string, {
  openingUnadjusted?: number
  openingAdjustment?: number
  closingUnadjusted?: number
  closingAdjustment?: number
  reasonAnalysis?: string
  indexRef?: string
}>

export interface G8AdjustmentWriteback {
  rowKey: string
  closingAdjustment: number
}

export interface G8AdjustmentEntryLike {
  entryType?: string
  accountCode?: string
  debitAmount?: number
  creditAmount?: number
}

export function defaultG8AdjStore(): G8AdjRowStore {
  const s: G8AdjRowStore = {}
  for (const def of G8_ADJUDICATION_ITEMS) {
    s[def.rowKey] = {
      openingUnadjusted: 0,
      openingAdjustment: 0,
      closingUnadjusted: 0,
      closingAdjustment: 0,
      reasonAnalysis: '',
      indexRef: '',
    }
  }
  return s
}

export function parseG8AdjStore(json: string | null | undefined): G8AdjRowStore {
  if (!json) return defaultG8AdjStore()
  try {
    return { ...defaultG8AdjStore(), ...JSON.parse(json) as G8AdjRowStore }
  } catch {
    return defaultG8AdjStore()
  }
}

export function patchG8AdjRow(
  store: G8AdjRowStore,
  rowKey: string,
  patch: Partial<G8AdjRowStore[string]>,
): G8AdjRowStore {
  return {
    ...store,
    [rowKey]: { ...(store[rowKey] ?? {}), ...patch },
  }
}

export function calcG8AdjustmentNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
): number {
  return rows
    .filter((r) => String(r.accountCode ?? '1503').startsWith('1503'))
    .reduce((s, r) => s + parseNum(r.debitAmount) - parseNum(r.creditAmount), 0)
}

/** 按 AJE/RJE 汇总 1503 科目净额，回写 G8-1 期末账项调整 */
export function aggregateG8AdjustmentWriteback(
  rows: G8AdjustmentEntryLike[],
  rowKey = G8_ADJ_WRITEBACK_ROW_KEY,
): G8AdjustmentWriteback {
  return { rowKey, closingAdjustment: calcG8AdjustmentNet(rows) }
}

export function applyG8AdjustmentWriteback(
  store: G8AdjRowStore,
  writeback: G8AdjustmentWriteback,
): G8AdjRowStore {
  return patchG8AdjRow(store, writeback.rowKey, {
    closingAdjustment: writeback.closingAdjustment,
  })
}
