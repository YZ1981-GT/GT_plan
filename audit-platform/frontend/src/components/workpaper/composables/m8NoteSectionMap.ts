/**
 * m8NoteSectionMap — M8 一般风险准备 披露→附注映射
 *
 * 章节：五、60（上市）/ 八、94（国企，新建）
 * 源 xlsx：`backend/wp_templates/M/M8 一般风险准备.xlsx`
 *   两版结构完全相同：5 列 flat 变动表（项目|期初余额|本期增加|本期减少|期末余额）
 *   动态插行区 + 合计行 + 1 段说明
 *
 * 表名权威 = `note_template_{listed,soe}.json` 对应章节 tables[0].name = '一般风险准备'
 */

import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type M8Variant = 'listed' | 'soe'

export const M8_NOTE_SECTION = {
  listed: '五、60',
  soe: '八、94',
} as const

export const M8_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const

export const M8_SUBTABLE = {
  main: '一般风险准备',
} as const

// ─── 列定义（5 列 flat，两版同构） ──────────────────────────────────────────

export function buildM8Columns(): Record<string, ColumnDef[]> {
  return {
    [M8_SUBTABLE.main]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'begin_amount', label: '期初余额', format: 'amount', align: 'right' },
      { key: 'increase', label: '本期增加', format: 'amount', align: 'right' },
      { key: 'decrease', label: '本期减少', format: 'amount', align: 'right' },
      { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
    ]),
  }
}

// ─── 行模型 ─────────────────────────────────────────────────────────────────

export interface M8DisclosureRow {
  label: string
  begin: number
  increase: number
  decrease: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 期末 = 期初 + 增加 − 减少（权益类贷方） */
export function m8EndAmount(r: M8DisclosureRow): number {
  return num(r.begin) + num(r.increase) - num(r.decrease)
}

// ─── 载荷构建 ───────────────────────────────────────────────────────────────

export interface M8SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns: Record<string, ColumnDef[]>
}

export function buildM8SyncPayload(
  wpId: string,
  variant: M8Variant,
  rows: readonly M8DisclosureRow[],
  noteText?: string,
): M8SyncPayload | null {
  if (!wpId) return null

  const dataRows: Record<string, unknown>[] = rows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      begin_amount: num(r.begin),
      increase: num(r.increase),
      decrease: num(r.decrease),
      end_amount: m8EndAmount(r),
    }))

  // 合计行
  const total: Record<string, unknown> = {
    label: '合计',
    begin_amount: dataRows.reduce((s, r) => s + num(r.begin_amount), 0),
    increase: dataRows.reduce((s, r) => s + num(r.increase), 0),
    decrease: dataRows.reduce((s, r) => s + num(r.decrease), 0),
    end_amount: dataRows.reduce((s, r) => s + num(r.end_amount), 0),
    is_total: true,
  }
  dataRows.push(total)

  const sub: Record<string, unknown> = {
    [M8_SUBTABLE.main]: dataRows,
  }

  if (noteText?.trim()) {
    ;(sub as any)._note_texts = [{
      section: `m8-${variant}-note`,
      title: '一般风险准备说明',
      text: noteText.trim(),
    }]
  }

  return {
    wp_id: wpId,
    sheet_name: M8_DISCLOSURE_SHEET_NAME[variant],
    section_id: M8_NOTE_SECTION[variant],
    current_standard: variant === 'listed' ? 'listed_standalone' : 'soe_standalone',
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: buildM8Columns(),
  }
}
