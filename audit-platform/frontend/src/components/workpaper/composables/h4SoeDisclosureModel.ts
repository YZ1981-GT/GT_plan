/**
 * H4 附注披露（国有企业）数据模型
 *
 * 对齐致同 Excel「附注披露信息（国有企业）」列结构（列不可改）：
 *   交叉索引：【在建工程与工程物资的合计数据披露详见J2-1】
 *   23、在建工程
 *     行：在建工程 / 工程物资 / 合计
 *     列：项目 | 期末余额(账面余额/减值准备/账面价值) | 期初余额(账面余额/减值准备/账面价值)
 *   账面价值 = 账面余额 − 减值准备
 *
 * 说明：H4 国企披露仅含附注「23」汇总表（与 H2 国企披露的汇总段同构），
 * 工程物资行由 H4-1 审定取数；在建工程行需与 H2-1 / J2-1 勾稽（可手工录入）。
 */

import { num } from './h4ListedDisclosureModel'

export { num }

export const H4_SOE_ITEM = {
  summary: 'H4-soe-summary',
  noteText: 'H4-disclosure-soe-text',
} as const

export function soeCarrying(book: number, impairment: number): number {
  return num(book) - num(impairment)
}

export interface H4SoeSummaryRow {
  key: 'cip' | 'materials'
  label: string
  endBook: number
  endImpairment: number
  beginBook: number
  beginImpairment: number
}

export function createDefaultH4SoeSummary(): H4SoeSummaryRow[] {
  return [
    { key: 'cip', label: '在建工程', endBook: 0, endImpairment: 0, beginBook: 0, beginImpairment: 0 },
    { key: 'materials', label: '工程物资', endBook: 0, endImpairment: 0, beginBook: 0, beginImpairment: 0 },
  ]
}

export function h4SoeSummaryTotal(rows: H4SoeSummaryRow[]) {
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

export interface H4SoeSummaryDisplayRow extends H4SoeSummaryRow {
  endCarrying: number
  beginCarrying: number
  editable: boolean
}

export function buildH4SoeSummaryDisplay(rows: H4SoeSummaryRow[]): H4SoeSummaryDisplayRow[] {
  const tot = h4SoeSummaryTotal(rows)
  return [
    ...rows.map((r) => ({
      ...r,
      endCarrying: soeCarrying(r.endBook, r.endImpairment),
      beginCarrying: soeCarrying(r.beginBook, r.beginImpairment),
      editable: true,
    })),
    {
      key: '__total__' as any,
      label: '合  计',
      endBook: tot.endBook,
      endImpairment: tot.endImpairment,
      endCarrying: tot.endCarrying,
      beginBook: tot.beginBook,
      beginImpairment: tot.beginImpairment,
      beginCarrying: tot.beginCarrying,
      editable: false,
    },
  ]
}

/** 从 H4-1 审定分段（原值/减值）种子工程物资行 */
export function seedH4SoeMaterialsFromAdjudication(src: {
  endBook?: number
  endImpairment?: number
  beginBook?: number
  beginImpairment?: number
}): H4SoeSummaryRow {
  return {
    key: 'materials',
    label: '工程物资',
    endBook: num(src.endBook),
    endImpairment: num(src.endImpairment),
    beginBook: num(src.beginBook),
    beginImpairment: num(src.beginImpairment),
  }
}
