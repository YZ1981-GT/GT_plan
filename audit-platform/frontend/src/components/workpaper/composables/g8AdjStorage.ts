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

function accountNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
  prefix: string,
): number {
  return rows
    .filter((r) => String(r.accountCode ?? '').startsWith(prefix))
    .reduce((s, r) => s + parseNum(r.debitAmount) - parseNum(r.creditAmount), 0)
}

/** G8-3 汇总看板：借贷合计、AJE/RJE、1503/OCI 净额 */
export interface G8AdjustmentSummary {
  rowCount: number
  ajeCount: number
  rjeCount: number
  totalDebits: number
  totalCredits: number
  balanceDiff: number
  net1503: number
  ajeNet1503: number
  rjeNet1503: number
  ociNet: number
}

export function summarizeG8Adjustment(
  rows: Array<{
    entryType?: string
    accountCode?: string
    debitAmount?: number
    creditAmount?: number
  }>,
): G8AdjustmentSummary {
  const list = rows ?? []
  const totalDebits = list.reduce((s, r) => s + parseNum(r.debitAmount), 0)
  const totalCredits = list.reduce((s, r) => s + parseNum(r.creditAmount), 0)
  const aje = list.filter((r) => r.entryType !== 'RJE')
  const rje = list.filter((r) => r.entryType === 'RJE')
  return {
    rowCount: list.length,
    ajeCount: aje.length,
    rjeCount: rje.length,
    totalDebits,
    totalCredits,
    balanceDiff: totalDebits - totalCredits,
    net1503: calcG8AdjustmentNet(list),
    ajeNet1503: calcG8AdjustmentNet(aje),
    rjeNet1503: calcG8AdjustmentNet(rje),
    ociNet: accountNet(list, '4002'),
  }
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
