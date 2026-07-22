/** G11-1 审定表 rowStore 读写 + G11-3 分项回写 */
import { G11_ACCOUNT_CODE, G11_ADJUDICATION_ITEMS } from './g11Constants'
import { inferG11AdjudicationRowKey, isG11AccountCode } from './g11AccountMatch'
import { parseNum } from './useG11FormulaEngine'

export type G11AdjRowStore = Record<string, {
  currentUnadjusted?: number
  currentAdjustment?: number
  priorUnadjusted?: number
  priorAdjustment?: number
  reasonAnalysis?: string
  indexRef?: string
}>

export interface G11AdjustmentEntryLike {
  category?: string
  entryType?: string
  accountCode?: string
  accountName?: string
  debitAmount?: number
  creditAmount?: number
  description?: string
  summary?: string
  noteItem?: string
  remark?: string
  adjudicationRowKey?: string
}

/** 分项回写：rowKey → 本期账项调整净额（6111 贷−借） */
export type G11AdjustmentWritebackMap = Record<string, number>

export interface G11AdjustmentSummary {
  rowCount: number
  ajeCount: number
  rjeCount: number
  totalDebits: number
  totalCredits: number
  balanceDiff: number
  /** 6111 账项调整净额（贷−借） */
  netAje6111: number
  /** 6111 报表调整净额（不回写审定） */
  netRje6111: number
}

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

function isReportReclass(row: G11AdjustmentEntryLike): boolean {
  if (row.category === '报表调整') return true
  if (row.entryType === 'RJE') return true
  return false
}

/** 6111 贷方科目：单行净额 = 贷方 − 借方（收益增加为正） */
export function calcG11AdjustmentNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number; category?: string; entryType?: string }>,
): number {
  return rows
    .filter((r) => isG11AccountCode(r.accountCode ?? G11_ACCOUNT_CODE) || String(r.accountCode ?? '').startsWith('6111'))
    .filter((r) => !isReportReclass(r))
    .reduce((s, r) => s + parseNum(r.creditAmount) - parseNum(r.debitAmount), 0)
}

/** G11-1 未审本期合计 → G11-5「本期发生额 / 总体金额」 */
export function calcG11AdjPopulationAmount(store: G11AdjRowStore): number {
  return Object.values(store).reduce((s, r) => s + parseNum(r?.currentUnadjusted), 0)
}

/**
 * 按审定表分项汇总 6111 账项调整净额。
 * 「报表调整」不计入；未匹配分项落入 other。
 */
export function aggregateG11AdjustmentByRow(
  rows: G11AdjustmentEntryLike[],
): G11AdjustmentWritebackMap {
  const byRow: G11AdjustmentWritebackMap = {}
  for (const def of G11_ADJUDICATION_ITEMS) byRow[def.rowKey] = 0

  for (const r of rows) {
    if (isReportReclass(r)) continue
    const code = String(r.accountCode ?? G11_ACCOUNT_CODE)
    if (!isG11AccountCode(code) && !code.startsWith('6111') && !String(r.accountName ?? '').includes('投资收益')) {
      continue
    }
    const key = inferG11AdjudicationRowKey(r)
    const net = parseNum(r.creditAmount) - parseNum(r.debitAmount)
    byRow[key] = (byRow[key] ?? 0) + net
  }
  return byRow
}

/** 将分项净额写入 G11-1 store 的 currentAdjustment（覆盖式，仅写出现在 map 中的键） */
export function applyG11AdjustmentWriteback(
  store: G11AdjRowStore,
  byRow: G11AdjustmentWritebackMap,
): G11AdjRowStore {
  let next = { ...store }
  for (const [rowKey, net] of Object.entries(byRow)) {
    next = patchG11AdjRow(next, rowKey, { currentAdjustment: parseNum(net) })
  }
  return next
}

export function summarizeG11Adjustment(rows: G11AdjustmentEntryLike[]): G11AdjustmentSummary {
  let ajeCount = 0
  let rjeCount = 0
  let totalDebits = 0
  let totalCredits = 0
  let netAje6111 = 0
  let netRje6111 = 0

  for (const r of rows) {
    totalDebits += parseNum(r.debitAmount)
    totalCredits += parseNum(r.creditAmount)
    const isRje = isReportReclass(r)
    if (isRje) rjeCount += 1
    else ajeCount += 1
    const code = String(r.accountCode ?? '')
    const is6111 = isG11AccountCode(code) || code.startsWith('6111') || String(r.accountName ?? '').includes('投资收益')
    if (!is6111) continue
    const net = parseNum(r.creditAmount) - parseNum(r.debitAmount)
    if (isRje) netRje6111 += net
    else netAje6111 += net
  }

  return {
    rowCount: rows.length,
    ajeCount,
    rjeCount,
    totalDebits,
    totalCredits,
    balanceDiff: totalDebits - totalCredits,
    netAje6111,
    netRje6111,
  }
}
