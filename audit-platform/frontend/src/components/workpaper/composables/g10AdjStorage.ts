/** G10-1 审定表 rowStore 读写辅助 */

import { G10_ADJUDICATION_ITEMS, G10_ACCOUNT_CODE } from './g10Constants'

import {

  inferG10AdjudicationRowKey,

  isG10AccountCode,

} from './g10AccountMatch'

import { calcAdjustedAmount, calcSubtotal, parseNum } from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export const G10_AJE_ROWS_KEY = 'G10-aje-rows'



export const G10_ADJ_WRITEBACK_OVERLAY_ID = 'G10-adj-writeback'

export const G10_ADJ_ROWS_KEY = 'G10-adj-rows'



export type G10AdjRowRaw = {

  openingUnadjusted?: number

  openingAJE?: number

  openingRJE?: number

  /** @deprecated 旧版单字段账项调整，读取时并入 openingAJE */

  openingAdjustment?: number

  closingUnadjusted?: number

  closingAJE?: number

  closingRJE?: number

  /** @deprecated 旧版单字段账项调整，读取时并入 closingAJE */

  closingAdjustment?: number

  /** @deprecated 历史字段：期初+贷方-借方推导期末未审 */

  periodCredit?: number

  periodDebit?: number

  reasonAnalysis?: string

  indexRef?: string

}



export type G10AdjRowStore = Record<string, G10AdjRowRaw>



export interface G10AdjustmentEntryLike {

  entryType?: string

  accountCode?: string

  debitAmount?: number

  creditAmount?: number

  summary?: string

  remark?: string

  liabilityType?: string

  adjudicationRowKey?: string

}



export interface G10AdjustmentWritebackRow {

  closingAje: number

  closingRje: number

}



export interface G10AdjustmentWritebackMap {

  byRow: Record<string, G10AdjustmentWritebackRow>

}



export interface G10AdjustmentSummary {

  rowCount: number

  ajeCount: number

  rjeCount: number

  totalDebits: number

  totalCredits: number

  balanceDiff: number

  /** 2101 贷−借净额（回写 G10-1 口径） */

  net2101: number

  ajeNet2101: number

  rjeNet2101: number

  /** 6101 借−贷净额（公允变动损益） */

  fvPlNet: number

}



function normalizeAdjRow(raw: G10AdjRowRaw | undefined, deriveClosingFromPeriod = false): G10AdjRowRaw {

  const base = raw ?? {}

  let openingAJE = parseNum(base.openingAJE)

  let openingRJE = parseNum(base.openingRJE)

  if (base.openingAJE == null && base.openingRJE == null && base.openingAdjustment != null) {

    openingAJE = parseNum(base.openingAdjustment)

  }

  let closingAJE = parseNum(base.closingAJE)

  let closingRJE = parseNum(base.closingRJE)

  if (base.closingAJE == null && base.closingRJE == null && base.closingAdjustment != null) {

    closingAJE = parseNum(base.closingAdjustment)

  }

  let closingUnadjusted = parseNum(base.closingUnadjusted)

  const hasExplicitClosing = !deriveClosingFromPeriod
    && base.closingUnadjusted != null
    && base.closingUnadjusted !== ''

  if (
    !hasExplicitClosing
    && (base.periodCredit != null || base.periodDebit != null)
  ) {
    const opening = parseNum(base.openingUnadjusted)
    closingUnadjusted = opening + parseNum(base.periodCredit) - parseNum(base.periodDebit)
  }

  return {

    ...base,

    openingUnadjusted: parseNum(base.openingUnadjusted),

    openingAJE,

    openingRJE,

    closingUnadjusted,

    closingAJE,

    closingRJE,

  }

}



export function g10RowOpeningAdjusted(raw: G10AdjRowRaw | undefined): number {

  const row = normalizeAdjRow(raw)

  return calcAdjustedAmount(

    parseNum(row.openingUnadjusted),

    parseNum(row.openingAJE),

    parseNum(row.openingRJE),

  )

}



export function g10RowClosingAdjusted(raw: G10AdjRowRaw | undefined): number {

  const row = normalizeAdjRow(raw)

  return calcAdjustedAmount(

    parseNum(row.closingUnadjusted),

    parseNum(row.closingAJE),

    parseNum(row.closingRJE),

  )

}



export function defaultG10AdjStore(): G10AdjRowStore {

  const s: G10AdjRowStore = {}

  for (const def of G10_ADJUDICATION_ITEMS) {

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



export function parseG10AdjStore(json: string | null | undefined): G10AdjRowStore {

  const defaults = defaultG10AdjStore()

  if (!json) return defaults

  try {

    const parsed = JSON.parse(json) as G10AdjRowStore

    const out = { ...defaults }

    for (const [key, raw] of Object.entries(parsed)) {

      const deriveClosing = raw.closingUnadjusted == null
        && (raw.periodCredit != null || raw.periodDebit != null)

      out[key] = normalizeAdjRow({ ...(defaults[key] ?? {}), ...raw }, deriveClosing)

    }

    return out

  } catch {

    return defaults

  }

}



export function patchG10AdjRow(

  store: G10AdjRowStore,

  rowKey: string,

  patch: Partial<G10AdjRowRaw>,

): G10AdjRowStore {

  return {

    ...store,

    [rowKey]: normalizeAdjRow({ ...(store[rowKey] ?? {}), ...patch }),

  }

}



function accountNet2101(

  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,

): number {

  return rows

    .filter((r) => isG10AccountCode(String(r.accountCode ?? G10_ACCOUNT_CODE)))

    .reduce((s, r) => s + parseNum(r.creditAmount) - parseNum(r.debitAmount), 0)

}



function accountNetFvPl(

  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,

): number {

  return rows

    .filter((r) => String(r.accountCode ?? '').startsWith('6101'))

    .reduce((s, r) => s + parseNum(r.debitAmount) - parseNum(r.creditAmount), 0)

}



/** 2101 贷方科目：调整净额 = 贷方 − 借方 */

export function calcG10AdjustmentNet(

  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,

): number {

  return accountNet2101(rows)

}



export function summarizeG10Adjustment(

  rows: Array<{

    entryType?: string

    accountCode?: string

    debitAmount?: number

    creditAmount?: number

  }>,

): G10AdjustmentSummary {

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

    net2101: calcG10AdjustmentNet(list),

    ajeNet2101: calcG10AdjustmentNet(aje),

    rjeNet2101: calcG10AdjustmentNet(rje),

    fvPlNet: accountNetFvPl(list),

  }

}



/** 按 G10-1 目标行分别汇总 AJE/RJE 净额（2101 贷−借） */

export function aggregateG10AdjustmentAjeRjeByRow(

  rows: G10AdjustmentEntryLike[],

): G10AdjustmentWritebackMap {

  const byRow: Record<string, G10AdjustmentWritebackRow> = {}

  for (const row of rows) {

    if (!isG10AccountCode(row.accountCode)) continue

    const net = parseNum(row.creditAmount) - parseNum(row.debitAmount)

    const rowKey = inferG10AdjudicationRowKey(row)

    const bucket = byRow[rowKey] ?? { closingAje: 0, closingRje: 0 }

    if (row.entryType === 'RJE') bucket.closingRje += net

    else bucket.closingAje += net

    byRow[rowKey] = bucket

  }

  return { byRow }

}



/** @deprecated 使用 aggregateG10AdjustmentAjeRjeByRow */

export function aggregateG10AdjustmentByRow(

  rows: G10AdjustmentEntryLike[],

): G10AdjustmentWritebackMap {

  return aggregateG10AdjustmentAjeRjeByRow(rows)

}



export function applyG10AdjustmentWritebacks(

  store: G10AdjRowStore,

  writeback: G10AdjustmentWritebackMap,

): G10AdjRowStore {

  let next = store

  for (const def of G10_ADJUDICATION_ITEMS) {

    if (def.group === 'book_fv') {

      next = patchG10AdjRow(next, def.rowKey, { closingAJE: 0, closingRJE: 0 })

    }

  }

  for (const [rowKey, wb] of Object.entries(writeback.byRow)) {

    next = patchG10AdjRow(next, rowKey, {

      closingAJE: wb.closingAje,

      closingRJE: wb.closingRje,

    })

  }

  return next

}



/** @deprecated 兼容旧单点回写 */

export function applyG10NetAdjustment(store: G10AdjRowStore, net: number): G10AdjRowStore {

  return patchG10AdjRow(store, 'book_other', { closingAJE: net, closingRJE: 0 })

}

/** G10-1 (三) 账面余额各行期末账项调整净额合计（closingAJE + closingRJE） */
export function sumG10BookFvAdjustmentNet(store: G10AdjRowStore): number {
  const bookKeys = G10_ADJUDICATION_ITEMS.filter((d) => d.group === 'book_fv').map((d) => d.rowKey)
  return calcSubtotal(bookKeys.map((k) => {
    const raw = normalizeAdjRow(store[k])
    return parseNum(raw.closingAJE) + parseNum(raw.closingRJE)
  }))
}

export interface G10Adj3WritebackCross {
  adj3Net2101: number
  g101BookNet: number
  diff: number
}

/** G10-3 2101 净额 vs G10-1 (三) 分项回写勾稽 */
export function compareG10Adj3VsG101Writeback(
  responses: Map<string, ChecklistResponse>,
): G10Adj3WritebackCross | null {
  const raw = responses.get(G10_AJE_ROWS_KEY)?.remark
  if (!raw) return null
  let adjRows: G10AdjustmentEntryLike[]
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) return null
    adjRows = parsed
  } catch {
    return null
  }
  const summary = summarizeG10Adjustment(adjRows)
  const store = parseG10AdjStore(responses.get(G10_ADJ_ROWS_KEY)?.remark)
  const g101BookNet = sumG10BookFvAdjustmentNet(store)
  return {
    adj3Net2101: summary.net2101,
    g101BookNet,
    diff: summary.net2101 - g101BookNet,
  }
}

