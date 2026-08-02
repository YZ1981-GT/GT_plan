/**
 * m10NoteSectionMap — M10 其他权益工具 披露→附注映射
 *
 * 章节：五、54（上市 3 表）/ 八、59（国企 1 表）
 * 源 xlsx：`backend/wp_templates/M/M10 其他权益工具.xlsx`
 *
 * 上市三表：
 *   表1「参考披露格式：」10 列 flat — 基本情况
 *   表2「期末发行在外的优先股、永续债等其他金融工具变动情况」两级 9 列 — 期初/增/减/末 各含 数量·账面价值
 *   表3「权益工具持有者的相关信息」3 列 flat
 *
 * 国企单表：两级 9 列（同上市表2 结构，期初/增/减/末 各含 数量·账面价值）
 *
 * 表名权威 = `note_template_{listed,soe}.json` 对应章节 tables[].name
 */

import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type M10Variant = 'listed' | 'soe'

// ─── 章节号 ─────────────────────────────────────────────────────────────────

export const M10_NOTE_SECTION = {
  listed: '五、54',
  soe: '八、59',
} as const

export const M10_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const

export const M10_LISTED_SUBTABLE = {
  basic: '参考披露格式：',
  movement: '期末发行在外的优先股、永续债等其他金融工具变动情况',
  holders: '权益工具持有者的相关信息',
} as const

export const M10_SOE_SUBTABLE = {
  main: '其他权益工具',
} as const

// ─── 列定义 ─────────────────────────────────────────────────────────────────

/** 上市表1：基本情况（10 列 flat） */
export function buildM10ListedBasicColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '发行在外的金融工具', is_label: true, flat: true },
    { key: 'issue_time', label: '发行时间', format: 'text' },
    { key: 'classification', label: '会计分类', format: 'text' },
    { key: 'dividend_rate', label: '股利率或利息率', format: 'text' },
    { key: 'issue_price', label: '发行价格', format: 'amount', align: 'right' },
    { key: 'quantity', label: '数量', format: 'amount', align: 'right' },
    { key: 'amount', label: '金额', format: 'amount', align: 'right' },
    { key: 'maturity', label: '到期日或续期情况', format: 'text' },
    { key: 'conversion_terms', label: '转股条件', format: 'text' },
    { key: 'conversion_status', label: '转换情况', format: 'text' },
  ])
}

/** 上市表2 / 国企主表：变动情况（两级 9 列） */
export function buildM10MovementColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '发行在外的金融工具', is_label: true },
    { key: 'begin_qty', label: '数量', format: 'amount', align: 'right', group: '期初余额' },
    { key: 'begin_value', label: '账面价值', format: 'amount', align: 'right', group: '期初余额' },
    { key: 'increase_qty', label: '数量', format: 'amount', align: 'right', group: '本期增加' },
    { key: 'increase_value', label: '账面价值', format: 'amount', align: 'right', group: '本期增加' },
    { key: 'decrease_qty', label: '数量', format: 'amount', align: 'right', group: '本期减少' },
    { key: 'decrease_value', label: '账面价值', format: 'amount', align: 'right', group: '本期减少' },
    { key: 'end_qty', label: '数量', format: 'amount', align: 'right', group: '期末余额' },
    { key: 'end_value', label: '账面价值', format: 'amount', align: 'right', group: '期末余额' },
  ])
}

/** 上市表3：持有者相关信息（3 列 flat） */
export function buildM10HoldersColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'current', label: '期末余额/本期发生额', format: 'amount', align: 'right' },
    { key: 'prior', label: '上年年末余额/上期发生额', format: 'amount', align: 'right' },
  ])
}

/** 上市版全量列定义（三表） */
export function buildM10ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [M10_LISTED_SUBTABLE.basic]: buildM10ListedBasicColumns(),
    [M10_LISTED_SUBTABLE.movement]: buildM10MovementColumns(),
    [M10_LISTED_SUBTABLE.holders]: buildM10HoldersColumns(),
  }
}

/** 国企版列定义（单表） */
export function buildM10SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [M10_SOE_SUBTABLE.main]: buildM10MovementColumns(),
  }
}

// ─── 行模型 ─────────────────────────────────────────────────────────────────

/** 变动表行（上市表2 / 国企表） */
export interface M10MovementRow {
  label: string
  beginQty: number
  beginValue: number
  increaseQty: number
  increaseValue: number
  decreaseQty: number
  decreaseValue: number
}

/** 基本情况行（上市表1） */
export interface M10BasicRow {
  label: string
  issueTime: string
  classification: string
  dividendRate: string
  issuePrice: number
  quantity: number
  amount: number
  maturity: string
  conversionTerms: string
  conversionStatus: string
}

/** 持有者信息行（上市表3） */
export interface M10HoldersRow {
  label: string
  current: number
  prior: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 期末数量/账面价值 = 期初 + 增加 − 减少 */
export function m10EndQty(r: M10MovementRow): number {
  return num(r.beginQty) + num(r.increaseQty) - num(r.decreaseQty)
}
export function m10EndValue(r: M10MovementRow): number {
  return num(r.beginValue) + num(r.increaseValue) - num(r.decreaseValue)
}

// ─── 载荷构建 ───────────────────────────────────────────────────────────────

export interface M10SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns: Record<string, ColumnDef[]>
}

/** 国企版载荷（单表：变动情况） */
export function buildM10SoeSyncPayload(
  wpId: string,
  rows: readonly M10MovementRow[],
  noteText?: string,
): M10SyncPayload | null {
  if (!wpId) return null

  const dataRows: Record<string, unknown>[] = rows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      begin_qty: num(r.beginQty),
      begin_value: num(r.beginValue),
      increase_qty: num(r.increaseQty),
      increase_value: num(r.increaseValue),
      decrease_qty: num(r.decreaseQty),
      decrease_value: num(r.decreaseValue),
      end_qty: m10EndQty(r),
      end_value: m10EndValue(r),
    }))

  // 合计行
  const total: Record<string, unknown> = {
    label: '合计',
    begin_qty: dataRows.reduce((s, r) => s + num(r.begin_qty), 0),
    begin_value: dataRows.reduce((s, r) => s + num(r.begin_value), 0),
    increase_qty: dataRows.reduce((s, r) => s + num(r.increase_qty), 0),
    increase_value: dataRows.reduce((s, r) => s + num(r.increase_value), 0),
    decrease_qty: dataRows.reduce((s, r) => s + num(r.decrease_qty), 0),
    decrease_value: dataRows.reduce((s, r) => s + num(r.decrease_value), 0),
    end_qty: dataRows.reduce((s, r) => s + num(r.end_qty), 0),
    end_value: dataRows.reduce((s, r) => s + num(r.end_value), 0),
    is_total: true,
  }
  dataRows.push(total)

  const sub: Record<string, unknown> = { [M10_SOE_SUBTABLE.main]: dataRows }
  if (noteText?.trim()) {
    ;(sub as any)._note_texts = [{
      section: 'm10-soe-note',
      title: '其他权益工具说明',
      text: noteText.trim(),
    }]
  }

  return {
    wp_id: wpId,
    sheet_name: M10_DISCLOSURE_SHEET_NAME.soe,
    section_id: M10_NOTE_SECTION.soe,
    current_standard: 'soe_standalone',
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: buildM10SoeColumns(),
  }
}

/** 上市版载荷（三表） */
export function buildM10ListedSyncPayload(
  wpId: string,
  basicRows: readonly M10BasicRow[],
  movementRows: readonly M10MovementRow[],
  holdersRows: readonly M10HoldersRow[],
  noteText?: string,
): M10SyncPayload | null {
  if (!wpId) return null

  // 表1：基本情况
  const basic: Record<string, unknown>[] = basicRows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      issue_time: r.issueTime || '',
      classification: r.classification || '',
      dividend_rate: r.dividendRate || '',
      issue_price: num(r.issuePrice),
      quantity: num(r.quantity),
      amount: num(r.amount),
      maturity: r.maturity || '',
      conversion_terms: r.conversionTerms || '',
      conversion_status: r.conversionStatus || '',
    }))

  // 表2：变动情况
  const movement: Record<string, unknown>[] = movementRows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      begin_qty: num(r.beginQty),
      begin_value: num(r.beginValue),
      increase_qty: num(r.increaseQty),
      increase_value: num(r.increaseValue),
      decrease_qty: num(r.decreaseQty),
      decrease_value: num(r.decreaseValue),
      end_qty: m10EndQty(r),
      end_value: m10EndValue(r),
    }))
  // 合计行
  const mvTotal: Record<string, unknown> = {
    label: '合计',
    begin_qty: movement.reduce((s, r) => s + num(r.begin_qty), 0),
    begin_value: movement.reduce((s, r) => s + num(r.begin_value), 0),
    increase_qty: movement.reduce((s, r) => s + num(r.increase_qty), 0),
    increase_value: movement.reduce((s, r) => s + num(r.increase_value), 0),
    decrease_qty: movement.reduce((s, r) => s + num(r.decrease_qty), 0),
    decrease_value: movement.reduce((s, r) => s + num(r.decrease_value), 0),
    end_qty: movement.reduce((s, r) => s + num(r.end_qty), 0),
    end_value: movement.reduce((s, r) => s + num(r.end_value), 0),
    is_total: true,
  }
  movement.push(mvTotal)

  // 表3：持有者信息
  const holders: Record<string, unknown>[] = holdersRows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      current: num(r.current),
      prior: num(r.prior),
    }))

  const sub: Record<string, unknown> = {
    [M10_LISTED_SUBTABLE.basic]: basic,
    [M10_LISTED_SUBTABLE.movement]: movement,
    [M10_LISTED_SUBTABLE.holders]: holders,
  }
  if (noteText?.trim()) {
    ;(sub as any)._note_texts = [{
      section: 'm10-listed-note',
      title: '其他权益工具说明',
      text: noteText.trim(),
    }]
  }

  return {
    wp_id: wpId,
    sheet_name: M10_DISCLOSURE_SHEET_NAME.listed,
    section_id: M10_NOTE_SECTION.listed,
    current_standard: 'listed_standalone',
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: buildM10ListedColumns(),
  }
}
