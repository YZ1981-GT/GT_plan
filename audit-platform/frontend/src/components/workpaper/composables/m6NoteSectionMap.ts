/**
 * m6NoteSectionMap — M6 未分配利润 披露→附注映射
 *
 * 章节：五、61（上市）/ 八、63（国企）
 * 源 xlsx：`backend/wp_templates/M/M6 未分配利润.xlsx`
 *   上市 R6~R20：4 列（项目 / 本期发生额 / 上期发生额 / 提取或分配比例）14 行固定
 *   国企 R6~R19：3 列（项目 / 本期金额 / 上期金额）15 行固定
 *
 * 表名权威 = `note_template_{listed,soe}.json` 对应章节 `tables[0].name = '未分配利润'`
 */

import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

// ─── 章节号 ─────────────────────────────────────────────────────────────────

export const M6_NOTE_SECTION = {
  listed: '五、61',
  soe: '八、63',
} as const

export const M6_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const

export const M6_SUBTABLE = {
  main: '未分配利润',
} as const

export type M6Variant = 'listed' | 'soe'

// ─── 列定义 ─────────────────────────────────────────────────────────────────

export function buildM6ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [M6_SUBTABLE.main]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'current', label: '本期发生额', format: 'amount', align: 'right' },
      { key: 'prior', label: '上期发生额', format: 'amount', align: 'right' },
      { key: 'ratio', label: '提取或分配比例', format: 'text' },
    ]),
  }
}

export function buildM6SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [M6_SUBTABLE.main]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'current', label: '本期金额', format: 'amount', align: 'right' },
      { key: 'prior', label: '上期金额', format: 'amount', align: 'right' },
    ]),
  }
}

// ─── 行模型 ─────────────────────────────────────────────────────────────────

export interface M6DisclosureRow {
  label: string
  current: number
  prior: number
  ratio?: string  // 仅上市版
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── 载荷构建 ───────────────────────────────────────────────────────────────

export interface M6SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns: Record<string, ColumnDef[]>
}

export function buildM6SyncPayload(
  wpId: string,
  variant: M6Variant,
  rows: readonly M6DisclosureRow[],
  noteText?: string,
): M6SyncPayload | null {
  if (!wpId) return null

  const isListed = variant === 'listed'
  const dataRows: Record<string, unknown>[] = rows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => {
      const row: Record<string, unknown> = {
        label: r.label.trim(),
        current: num(r.current),
        prior: num(r.prior),
      }
      if (isListed) {
        row.ratio = r.ratio || ''
      }
      return row
    })

  const sub: Record<string, unknown> = {
    [M6_SUBTABLE.main]: dataRows,
  }

  if (noteText?.trim()) {
    ;(sub as any)._note_texts = [{
      section: `m6-${variant}-note`,
      title: '未分配利润说明',
      text: noteText.trim(),
    }]
  }

  return {
    wp_id: wpId,
    sheet_name: M6_DISCLOSURE_SHEET_NAME[variant],
    section_id: M6_NOTE_SECTION[variant],
    current_standard: isListed ? 'listed_standalone' : 'soe_standalone',
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: isListed ? buildM6ListedColumns() : buildM6SoeColumns(),
  }
}
