/**
 * m9NoteSectionMap — M9 其他综合收益 披露→附注映射
 *
 * 章节：五、57（上市 2 表）/ 八、79（国企 2 表）
 * 源 xlsx：`backend/wp_templates/M/M9 其他综合收益.xlsx`
 *
 * 上市两表（§五、57）：
 *   表1「资产负债表中归属于母公司的其他综合收益：」两级 8 列
 *     项目(rowspan2) | 期初余额(rowspan2) | 本期发生金额(税前/转损益/所得税/税后归母/税后归少) | 期末余额(rowspan2)
 *   表2「利润表中归属于母公司的其他综合收益：」同结构
 *
 * 国企两表（§八、79）：
 *   表1「其他综合收益各项目及其所得税影响和转入损益情况」两级 7 列
 *     项目(rowspan2) | 本期发生额(税前金额/所得税/税后净额) | 上期发生额(税前金额/所得税/税后净额)
 *   表2（列转置余额调节表 —— 暂不接同步）
 *
 * 行集：
 *   一、以后不能重分类进损益的（6 子项）
 *   二、以后将重分类进损益的（7 子项）
 *   合计
 *
 * 表名权威 = `note_template_{listed,soe}.json` 对应章节 tables[].name
 */

import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type M9Variant = 'listed' | 'soe'

// ─── 章节号 ─────────────────────────────────────────────────────────────────

export const M9_NOTE_SECTION = {
  listed: '五、57',
  soe: '八、79',
} as const

export const M9_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const

export const M9_LISTED_SUBTABLE = {
  balanceSheet: '资产负债表中归属于母公司的其他综合收益：',
  incomeStatement: '利润表中归属于母公司的其他综合收益：',
} as const

export const M9_SOE_SUBTABLE = {
  main: '其他综合收益各项目及其所得税影响和转入损益情况',
} as const

// ─── 列定义 ─────────────────────────────────────────────────────────────────

/**
 * 上市版（五、57）两级 8 列：
 * 项目(rowspan2) | 期初余额(rowspan2) | 本期发生金额: 本期所得税前发生额 / 减：前期计入OCI当期转入损益 /
 *   减：所得税费用 / 税后归属于母公司 / 税后归属于少数股东 | 期末余额(rowspan2)
 */
export function buildM9ListedColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: 'begin_amount', label: '期初余额', format: 'amount', align: 'right' },
    { key: 'pre_tax', label: '本期所得税前发生额', format: 'amount', align: 'right', group: '本期发生金额' },
    { key: 'transfer_to_pl', label: '减：前期计入其他综合收益当期转入损益', format: 'amount', align: 'right', group: '本期发生金额' },
    { key: 'tax_effect', label: '减：所得税费用', format: 'amount', align: 'right', group: '本期发生金额' },
    { key: 'after_tax_parent', label: '税后归属于母公司', format: 'amount', align: 'right', group: '本期发生金额' },
    { key: 'after_tax_minority', label: '税后归属于少数股东', format: 'amount', align: 'right', group: '本期发生金额' },
    { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
  ])
}

/**
 * 国企版（八、79）两级 7 列：
 * 项目(rowspan2) | 本期发生额: 税前金额 / 所得税 / 税后净额 | 上期发生额: 税前金额 / 所得税 / 税后净额
 */
export function buildM9SoeColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_pre_tax', label: '税前金额', format: 'amount', align: 'right', group: '本期发生额' },
    { key: 'end_tax', label: '所得税', format: 'amount', align: 'right', group: '本期发生额' },
    { key: 'end_net', label: '税后净额', format: 'amount', align: 'right', group: '本期发生额' },
    { key: 'prior_pre_tax', label: '税前金额', format: 'amount', align: 'right', group: '上期发生额' },
    { key: 'prior_tax', label: '所得税', format: 'amount', align: 'right', group: '上期发生额' },
    { key: 'prior_net', label: '税后净额', format: 'amount', align: 'right', group: '上期发生额' },
  ])
}

/** 上市版全量列定义（两表同结构） */
export function buildM9ListedAllColumns(): Record<string, ColumnDef[]> {
  return {
    [M9_LISTED_SUBTABLE.balanceSheet]: buildM9ListedColumns(),
    [M9_LISTED_SUBTABLE.incomeStatement]: buildM9ListedColumns(),
  }
}

/** 国企版列定义 */
export function buildM9SoeAllColumns(): Record<string, ColumnDef[]> {
  return {
    [M9_SOE_SUBTABLE.main]: buildM9SoeColumns(),
  }
}

// ─── 行模型 ─────────────────────────────────────────────────────────────────

/** 上市版 OCI 行 */
export interface M9ListedRow {
  label: string
  beginAmount: number
  preTax: number
  transferToPl: number
  taxEffect: number
  afterTaxParent: number
  afterTaxMinority: number
}

/** 国企版 OCI 行 */
export interface M9SoeRow {
  label: string
  endPreTax: number
  endTax: number
  endNet: number
  priorPreTax: number
  priorTax: number
  priorNet: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 上市：期末 = 期初 + 税后归属于母公司 */
export function m9ListedEnd(r: M9ListedRow): number {
  return num(r.beginAmount) + num(r.afterTaxParent)
}

// ─── 载荷构建 ───────────────────────────────────────────────────────────────

export interface M9SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns: Record<string, ColumnDef[]>
}

/** 上市版载荷 */
export function buildM9ListedSyncPayload(
  wpId: string,
  bsRows: readonly M9ListedRow[],
  plRows: readonly M9ListedRow[],
): M9SyncPayload | null {
  if (!wpId) return null

  function mapRows(rows: readonly M9ListedRow[]): Record<string, unknown>[] {
    const data: Record<string, unknown>[] = rows
      .filter((r) => (r.label ?? '').trim())
      .map((r) => ({
        label: r.label.trim(),
        begin_amount: num(r.beginAmount),
        pre_tax: num(r.preTax),
        transfer_to_pl: num(r.transferToPl),
        tax_effect: num(r.taxEffect),
        after_tax_parent: num(r.afterTaxParent),
        after_tax_minority: num(r.afterTaxMinority),
        end_amount: m9ListedEnd(r),
      }))
    // 合计行
    const total: Record<string, unknown> = {
      label: '合计',
      begin_amount: data.reduce((s, r) => s + num(r.begin_amount), 0),
      pre_tax: data.reduce((s, r) => s + num(r.pre_tax), 0),
      transfer_to_pl: data.reduce((s, r) => s + num(r.transfer_to_pl), 0),
      tax_effect: data.reduce((s, r) => s + num(r.tax_effect), 0),
      after_tax_parent: data.reduce((s, r) => s + num(r.after_tax_parent), 0),
      after_tax_minority: data.reduce((s, r) => s + num(r.after_tax_minority), 0),
      end_amount: data.reduce((s, r) => s + num(r.end_amount), 0),
      is_total: true,
    }
    data.push(total)
    return data
  }

  return {
    wp_id: wpId,
    sheet_name: M9_DISCLOSURE_SHEET_NAME.listed,
    section_id: M9_NOTE_SECTION.listed,
    current_standard: 'listed_standalone',
    sub_table_data: {
      [M9_LISTED_SUBTABLE.balanceSheet]: mapRows(bsRows),
      [M9_LISTED_SUBTABLE.incomeStatement]: mapRows(plRows),
    },
    columns: buildM9ListedAllColumns(),
  }
}

/** 国企版载荷 */
export function buildM9SoeSyncPayload(
  wpId: string,
  rows: readonly M9SoeRow[],
): M9SyncPayload | null {
  if (!wpId) return null

  const data: Record<string, unknown>[] = rows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      end_pre_tax: num(r.endPreTax),
      end_tax: num(r.endTax),
      end_net: num(r.endNet),
      prior_pre_tax: num(r.priorPreTax),
      prior_tax: num(r.priorTax),
      prior_net: num(r.priorNet),
    }))

  // 合计行
  const total: Record<string, unknown> = {
    label: '合计',
    end_pre_tax: data.reduce((s, r) => s + num(r.end_pre_tax), 0),
    end_tax: data.reduce((s, r) => s + num(r.end_tax), 0),
    end_net: data.reduce((s, r) => s + num(r.end_net), 0),
    prior_pre_tax: data.reduce((s, r) => s + num(r.prior_pre_tax), 0),
    prior_tax: data.reduce((s, r) => s + num(r.prior_tax), 0),
    prior_net: data.reduce((s, r) => s + num(r.prior_net), 0),
    is_total: true,
  }
  data.push(total)

  return {
    wp_id: wpId,
    sheet_name: M9_DISCLOSURE_SHEET_NAME.soe,
    section_id: M9_NOTE_SECTION.soe,
    current_standard: 'soe_standalone',
    sub_table_data: {
      [M9_SOE_SUBTABLE.main]: data,
    },
    columns: buildM9SoeAllColumns(),
  }
}
