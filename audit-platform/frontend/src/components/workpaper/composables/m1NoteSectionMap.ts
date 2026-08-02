/**
 * m1NoteSectionMap — M1 应付股利（利润）披露→附注映射（浅合并推 K3 章节）
 *
 * **M1 没有独立附注章节**——应付股利披露归 K3 §五、42/八、42 的子表。
 * M1 底稿持有「应付股利」+「重要的超过1年未支付的应付股利」两表的完整录入数据，
 * K3 侧这两张表从不推送（底稿无录入区块）。
 *
 * 同 H4→H2 / L6→L5 浅合并范式：M1 推自己的 2/1 张子表，按 key 与 K3 其它表共存。
 *
 * 源 xlsx：`backend/wp_templates/M/M1 应付股利（利润）.xlsx`
 *   上市 R7~R20：项目/期末余额/上年年末余额 + 重要的超过1年（股东名称/金额/原因）
 *   国企 R8~R12：项目/期末余额/期初余额（无「超1年」表）
 */

import { defineColumns, type ColumnDef } from './disclosureColumnDefs'
import { K3_LISTED_SUBTABLE, K3_SOE_SUBTABLE } from './k3NoteSectionMap'

export type M1Variant = 'listed' | 'soe'

// ─── 章节号（引用 K3 的章节） ────────────────────────────────────────────────

export const M1_NOTE_SECTION = {
  /** 五、42（K3 其他应付款 listed） */
  listed: '五、42',
  /** 八、42（K3 其他应付款 soe） */
  soe: '八、42',
} as const

export const M1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const

// ─── 子表名（与 K3 共享同一章节，M1 只推这 2/1 张） ────────────────────────

export const M1_LISTED_SUBTABLES = {
  dividend: K3_LISTED_SUBTABLE.dividend,               // '应付股利'
  dividendOverdue: K3_LISTED_SUBTABLE.dividendOverdue, // '重要的超过1年未支付的应付股利'
} as const

export const M1_SOE_SUBTABLES = {
  dividend: K3_SOE_SUBTABLE.dividend, // '应付股利'
} as const

// ─── 列定义（复用 K3 已有定义） ─────────────────────────────────────────────

function twoPeriodListed(labelCol: string): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: labelCol, is_label: true, flat: true },
    { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
    { key: 'prior_amount', label: '上年年末余额', format: 'amount', align: 'right' },
  ])
}

function twoPeriodSoe(labelCol: string): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: labelCol, is_label: true, flat: true },
    { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
    { key: 'prior_amount', label: '期初余额', format: 'amount', align: 'right' },
  ])
}

export function buildM1ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [M1_LISTED_SUBTABLES.dividend]: twoPeriodListed('项目（或股东名称）'),
    [M1_LISTED_SUBTABLES.dividendOverdue]: defineColumns([
      { key: 'label', label: '股东名称', is_label: true, flat: true },
      { key: 'dividend_amount', label: '应付股利金额', format: 'amount', align: 'right' },
      { key: 'unpaid_reason', label: '未支付原因', format: 'text' },
    ]),
  }
}

export function buildM1SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [M1_SOE_SUBTABLES.dividend]: twoPeriodSoe('项目'),
  }
}

// ─── 行模型 ─────────────────────────────────────────────────────────────────

export interface M1DividendRow {
  label: string
  endAmount: number
  priorAmount: number
}

export interface M1OverdueRow {
  shareholder: string
  dividendAmount: number
  unpaidReason: string
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── 载荷构建 ───────────────────────────────────────────────────────────────

export interface M1SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns: Record<string, ColumnDef[]>
}

export function buildM1SyncPayload(
  wpId: string,
  variant: M1Variant,
  dividendRows: readonly M1DividendRow[],
  overdueRows?: readonly M1OverdueRow[],
): M1SyncPayload | null {
  if (!wpId) return null

  const isListed = variant === 'listed'
  const sub: Record<string, Record<string, unknown>[]> = {}

  // 应付股利主表
  const dividendData = dividendRows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      end_amount: num(r.endAmount),
      prior_amount: num(r.priorAmount),
    }))
  // 合计行
  dividendData.push({
    label: '合计',
    end_amount: dividendData.reduce((s, r) => s + num(r.end_amount), 0),
    prior_amount: dividendData.reduce((s, r) => s + num(r.prior_amount), 0),
    ...({ is_total: true } as any),
  })
  sub[isListed ? M1_LISTED_SUBTABLES.dividend : M1_SOE_SUBTABLES.dividend] = dividendData

  // 超1年表（仅上市）
  if (isListed && overdueRows && overdueRows.length > 0) {
    const overdueData = overdueRows
      .filter((r) => (r.shareholder ?? '').trim())
      .map((r) => ({
        label: r.shareholder.trim(),
        dividend_amount: num(r.dividendAmount),
        unpaid_reason: r.unpaidReason || '',
      }))
    if (overdueData.length > 0) {
      overdueData.push({
        label: '合计',
        dividend_amount: overdueData.reduce((s, r) => s + num(r.dividend_amount), 0),
        unpaid_reason: '',
        ...({ is_total: true } as any),
      })
      sub[M1_LISTED_SUBTABLES.dividendOverdue] = overdueData
    }
  }

  return {
    wp_id: wpId,
    sheet_name: M1_DISCLOSURE_SHEET_NAME[variant],
    section_id: M1_NOTE_SECTION[variant],
    current_standard: isListed ? 'listed_standalone' : 'soe_standalone',
    sub_table_data: sub,
    columns: isListed ? buildM1ListedColumns() : buildM1SoeColumns(),
  }
}
