/**
 * m3NoteSectionMap — M3 库存股 披露→附注映射
 *
 * 章节：五、56（仅上市；`variant_matrix.ku_cun_gu.soe_standalone=null`）
 * 源 xlsx：`backend/wp_templates/M/M3 库存股.xlsx` 的「附注披露信息（上市公司）」
 *   R6 项目|期初余额|本期增加|本期减少|期末余额（5 列 flat 变动表 + 动态可扩行）
 *   R11~R16 说明文本 6 段
 *
 * 表名权威 = `note_template_listed.json` §五、56 `tables[0].name = '库存股'`
 */

import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

// ─── 章节号 ─────────────────────────────────────────────────────────────────

export const M3_NOTE_SECTION = {
  listed: '五、56',
} as const

export const M3_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
} as const

export const M3_SUBTABLE = {
  main: '库存股',
} as const

// ─── 列定义（5 列 flat，逐字对齐模板 headers） ─────────────────────────────

export function buildM3Columns(): Record<string, ColumnDef[]> {
  return {
    [M3_SUBTABLE.main]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'begin_amount', label: '期初余额', format: 'amount', align: 'right' },
      { key: 'increase', label: '本期增加', format: 'amount', align: 'right' },
      { key: 'decrease', label: '本期减少', format: 'amount', align: 'right' },
      { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
    ]),
  }
}

// ─── 行模型 ─────────────────────────────────────────────────────────────────

export interface M3DisclosureRow {
  label: string
  begin: number
  increase: number
  decrease: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 期末（库存股=权益备抵借方）= 期初 + 增加 − 减少 */
export function m3EndAmount(r: M3DisclosureRow): number {
  return num(r.begin) + num(r.increase) - num(r.decrease)
}

// ─── 载荷构建 ───────────────────────────────────────────────────────────────

export interface M3SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns: Record<string, ColumnDef[]>
}

export function buildM3SyncPayload(
  wpId: string,
  rows: readonly M3DisclosureRow[],
  noteTexts?: { purpose?: string; execution?: string; equityImpact?: string },
): M3SyncPayload | null {
  if (!wpId) return null

  const dataRows: Record<string, unknown>[] = rows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      begin_amount: num(r.begin),
      increase: num(r.increase),
      decrease: num(r.decrease),
      end_amount: m3EndAmount(r),
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
    [M3_SUBTABLE.main]: dataRows,
  }

  // _note_texts（源模板 6 段说明）
  const texts: Array<{ section: string; title: string; text: string }> = []
  if (noteTexts?.purpose?.trim()) {
    texts.push({ section: 'm3-listed-purpose', title: '库存股变动情况及原因', text: noteTexts.purpose.trim() })
  }
  if (noteTexts?.execution?.trim()) {
    texts.push({ section: 'm3-listed-execution', title: '库存股注销/转让说明', text: noteTexts.execution.trim() })
  }
  if (noteTexts?.equityImpact?.trim()) {
    texts.push({ section: 'm3-listed-equity-impact', title: '股权激励回购比例', text: noteTexts.equityImpact.trim() })
  }
  if (texts.length > 0) {
    ;(sub as any)._note_texts = texts
  }

  return {
    wp_id: wpId,
    sheet_name: M3_DISCLOSURE_SHEET_NAME.listed,
    section_id: M3_NOTE_SECTION.listed,
    current_standard: 'listed_standalone',
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: buildM3Columns(),
  }
}
