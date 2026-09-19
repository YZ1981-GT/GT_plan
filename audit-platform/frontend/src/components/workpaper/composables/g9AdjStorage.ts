/** G9-1 审定表 rowStore 读写辅助 */
import { G9_ADJUDICATION_ITEMS, G9_ADJ_WRITEBACK_ROW_KEY, G9_ACCOUNT_CODE } from './g9Constants'
import { isG9AccountCode } from './g9AccountMatch'
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

export interface G9AdjustmentSummary {
  rowCount: number
  ajeCount: number
  rjeCount: number
  totalDebits: number
  totalCredits: number
  balanceDiff: number
  /** G9 科目借−贷净额（回写口径；字段名 net1504 保留兼容） */
  net1504: number
  ajeNet1504: number
  rjeNet1504: number
  /** 6101 公允变动损益净额 */
  fvPlNet: number
  /** 4002 OCI 净额 */
  ociNet: number
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

function accountNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
  matcher: (code: string) => boolean,
): number {
  return rows
    .filter((r) => matcher(String(r.accountCode ?? '')))
    .reduce((s, r) => s + parseNum(r.debitAmount) - parseNum(r.creditAmount), 0)
}

export function calcG9AdjustmentNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
): number {
  return accountNet(rows, isG9AccountCode)
}

export function summarizeG9Adjustment(
  rows: Array<{
    entryType?: string
    accountCode?: string
    debitAmount?: number
    creditAmount?: number
  }>,
): G9AdjustmentSummary {
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
    net1504: calcG9AdjustmentNet(list),
    ajeNet1504: calcG9AdjustmentNet(aje),
    rjeNet1504: calcG9AdjustmentNet(rje),
    fvPlNet: accountNet(list, (c) => c.startsWith('6101')),
    ociNet: accountNet(list, (c) => c.startsWith('4002')),
  }
}

/** 按 AJE/RJE 分别汇总 G9 科目净额（借方−贷方），用于回写 G9-1 */
export function aggregateG9AdjustmentAjeRje(
  rows: G9AdjustmentEntryLike[],
  rowKey = G9_ADJ_WRITEBACK_ROW_KEY,
): G9AdjustmentWriteback {
  let closingAje = 0
  let closingRje = 0
  for (const row of rows) {
    const code = String(row.accountCode ?? G9_ACCOUNT_CODE)
    if (!isG9AccountCode(code)) continue
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
