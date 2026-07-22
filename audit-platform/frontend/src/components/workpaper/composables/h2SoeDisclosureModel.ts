/**
 * H2 附注披露（国有企业）数据模型
 *
 * 对齐源模板「附注披露信息（国有企业）」列结构（列不可改）：
 *  23、在建工程汇总（账面余额/减值/账面价值 × 期末+期初）
 *  （1）在建工程情况（同上列，动态项目行）
 *  （2）重要在建工程项目本期变动（宽表：预算+增减转固+进度+利息+资金来源）
 *  （3）本期计提减值（计提金额 + 计提原因）
 */

import {
  listedProjectCumPct,
  listedProjectEnd,
  mapDetailToListedProjects,
  newRowId,
  num,
  type H2DetailSourceRow,
  type ListedProjectRow,
} from './h2ListedDisclosureModel'

export const H2_SOE_ITEM = {
  summary: 'H2-soe-summary',
  detail: 'H2-soe-detail-rows',
  projects: 'H2-soe-project-rows',
  impairment: 'H2-soe-impairment-rows',
  noteImpairment: 'H2-soe-note-impairment',
} as const

export { newRowId, num }

/** 汇总 / （1）明细共用三栏结构 */
export interface SoeBalanceTriple {
  book: number
  impairment: number
  carrying: number
}

export function soeCarrying(book: number, impairment: number): number {
  return num(book) - num(impairment)
}

export interface SoeSummaryRow {
  key: 'cip' | 'materials'
  label: string
  endBook: number
  endImpairment: number
  beginBook: number
  beginImpairment: number
}

export function createDefaultSoeSummary(): SoeSummaryRow[] {
  return [
    { key: 'cip', label: '在建工程', endBook: 0, endImpairment: 0, beginBook: 0, beginImpairment: 0 },
    { key: 'materials', label: '工程物资', endBook: 0, endImpairment: 0, beginBook: 0, beginImpairment: 0 },
  ]
}

export function soeSummaryTotal(rows: SoeSummaryRow[]) {
  const endBook = rows.reduce((s, r) => s + num(r.endBook), 0)
  const endImpairment = rows.reduce((s, r) => s + num(r.endImpairment), 0)
  const beginBook = rows.reduce((s, r) => s + num(r.beginBook), 0)
  const beginImpairment = rows.reduce((s, r) => s + num(r.beginImpairment), 0)
  return {
    endBook,
    endImpairment,
    endCarrying: soeCarrying(endBook, endImpairment),
    beginBook,
    beginImpairment,
    beginCarrying: soeCarrying(beginBook, beginImpairment),
  }
}

/** （1）在建工程情况 — 动态行 */
export interface SoeDetailRow {
  rowId: string
  name: string
  endBook: number
  endImpairment: number
  beginBook: number
  beginImpairment: number
}

export function soeDetailSubtotal(rows: SoeDetailRow[]) {
  return soeSummaryTotal(
    rows.map((r) => ({
      key: 'cip' as const,
      label: r.name,
      endBook: r.endBook,
      endImpairment: r.endImpairment,
      beginBook: r.beginBook,
      beginImpairment: r.beginImpairment,
    })),
  )
}

/** （2）重要项目 — 与上市项目行字段兼容，宽表一次展示 */
export type SoeProjectRow = ListedProjectRow

export const soeProjectEnd = listedProjectEnd
export const soeProjectCumPct = listedProjectCumPct

export function createEmptySoeProject(): SoeProjectRow {
  return {
    rowId: newRowId('soe-proj'),
    name: '',
    beginBalance: 0,
    increase: 0,
    transferToFA: 0,
    otherDecrease: 0,
    interestCapAccum: 0,
    interestCapCurrent: 0,
    interestCapRate: 0,
    budget: 0,
    cumInputPct: 0,
    accumulatedInput: 0,
    progress: '',
    fundSource: '',
  }
}

export function soeProjectSubtotal(rows: SoeProjectRow[]) {
  const beginBalance = rows.reduce((s, r) => s + num(r.beginBalance), 0)
  const increase = rows.reduce((s, r) => s + num(r.increase), 0)
  const transferToFA = rows.reduce((s, r) => s + num(r.transferToFA), 0)
  const otherDecrease = rows.reduce((s, r) => s + num(r.otherDecrease), 0)
  const interestCapAccum = rows.reduce((s, r) => s + num(r.interestCapAccum), 0)
  const interestCapCurrent = rows.reduce((s, r) => s + num(r.interestCapCurrent), 0)
  const budget = rows.reduce((s, r) => s + num(r.budget), 0)
  const accumulatedInput = rows.reduce((s, r) => s + num(r.accumulatedInput), 0)
  return {
    beginBalance,
    increase,
    transferToFA,
    otherDecrease,
    endBalance: beginBalance + increase - transferToFA - otherDecrease,
    interestCapAccum,
    interestCapCurrent,
    budget,
    accumulatedInput,
    cumInputPct: budget > 0 ? Math.round((accumulatedInput / budget) * 10000) / 100 : 0,
  }
}

/** （3）本期计提减值 */
export interface SoeImpairmentRow {
  rowId: string
  name: string
  provisionAmount: number
  reason: string
}

export function soeImpairmentSubtotal(rows: SoeImpairmentRow[]): number {
  return rows.reduce((s, r) => s + num(r.provisionAmount), 0)
}

export function mapDetailToSoeDetail(rows: H2DetailSourceRow[]): SoeDetailRow[] {
  return (rows || [])
    .filter((r) => String(r.name || '').trim())
    .map((r, i) => ({
      rowId: r.rowId || newRowId(`soe-det-${i}`),
      name: String(r.name || ''),
      endBook: num(r.cipEnd),
      endImpairment: 0,
      beginBook: num(r.cipBegin),
      beginImpairment: 0,
    }))
}

export const mapDetailToSoeProjects = mapDetailToListedProjects
