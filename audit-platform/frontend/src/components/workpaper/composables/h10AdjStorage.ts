/** H10-1 审定表 rowStore 读写辅助 */
import { H10_ADJUDICATION_ITEMS, H10_ADJ_WRITEBACK_ROW_KEY } from './h10Constants'
import { parseNum } from './useH10FormulaEngine'

export { H10_ADJ_WRITEBACK_ROW_KEY }

export type H10AdjRowStore = Record<string, {
  currentUnadjusted?: number
  currentAje?: number
  currentRje?: number
  priorUnadjusted?: number
  priorAje?: number
  priorRje?: number
  reasonAnalysis?: string
  indexRef?: string
}>

export interface H10AdjustmentWriteback {
  rowKey: string
  currentAje: number
  currentRje: number
}

export interface H10AdjustmentEntryLike {
  entryType?: string
  accountCode?: string
  debitAmount?: number
  creditAmount?: number
}

export function defaultH10AdjStore(): H10AdjRowStore {
  const s: H10AdjRowStore = {}
  for (const def of H10_ADJUDICATION_ITEMS) {
    s[def.rowKey] = {
      currentUnadjusted: 0,
      currentAje: 0,
      currentRje: 0,
      priorUnadjusted: 0,
      priorAje: 0,
      priorRje: 0,
      reasonAnalysis: '',
      indexRef: '',
    }
  }
  return s
}

export function parseH10AdjStore(json: string | null | undefined): H10AdjRowStore {
  if (!json) return defaultH10AdjStore()
  try {
    return { ...defaultH10AdjStore(), ...JSON.parse(json) as H10AdjRowStore }
  } catch {
    return defaultH10AdjStore()
  }
}

export function patchH10AdjRow(
  store: H10AdjRowStore,
  rowKey: string,
  patch: Partial<H10AdjRowStore[string]>,
): H10AdjRowStore {
  return {
    ...store,
    [rowKey]: { ...(store[rowKey] ?? {}), ...patch },
  }
}

/** 6115 贷方科目：调整净额 = 贷方 − 借方 */
export function calcH10AdjustmentNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
): number {
  return rows
    .filter((r) => String(r.accountCode ?? '6115').startsWith('6115'))
    .reduce((s, r) => s + parseNum(r.creditAmount) - parseNum(r.debitAmount), 0)
}

/** 按 AJE/RJE 分别汇总 6115 科目净额（贷−借），用于回写 H10-1 */
export function aggregateH10AdjustmentAjeRje(
  rows: H10AdjustmentEntryLike[],
  rowKey = H10_ADJ_WRITEBACK_ROW_KEY,
): H10AdjustmentWriteback {
  let currentAje = 0
  let currentRje = 0
  for (const row of rows) {
    if (!String(row.accountCode ?? '6115').startsWith('6115')) continue
    const net = parseNum(row.creditAmount) - parseNum(row.debitAmount)
    if (row.entryType === 'RJE') currentRje += net
    else currentAje += net
  }
  return { rowKey, currentAje, currentRje }
}

export function applyH10AdjustmentWriteback(
  store: H10AdjRowStore,
  writeback: H10AdjustmentWriteback,
): H10AdjRowStore {
  return patchH10AdjRow(store, writeback.rowKey, {
    currentAje: writeback.currentAje,
    currentRje: writeback.currentRje,
  })
}
