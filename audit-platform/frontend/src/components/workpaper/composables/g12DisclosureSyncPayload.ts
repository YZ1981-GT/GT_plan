/**
 * G12 净敞口套期收益披露 → `disclosure_notes` 同步载荷
 *
 * 子表名逐字对齐 `note_template_listed.json §五、70` / `note_template_soe.json §八、71`
 * （由 `backend/scripts/fix/fix_note_g_cycle_structure.py` 对齐源模板后固定）。
 *
 * 🔴 两处硬约束：
 * - `columns` 必须显式标 `flat`（源模板是一行表头）。不标会让 seed 路径被后端
 *   `_infer_groups_from_headers` 按「本期/上期」前缀反猜出凭空父表头。
 * - 标签列 `label` 必须等于模板 `headers[0]`（上市「项目」/ 国企
 *   「产生净敞口套期收益的来源」），否则同步后表头错位。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.8
 */
import type { ColumnDef } from './disclosureColumnDefs'
import { defineColumns } from './disclosureColumnDefs'
import {
  G12_DISCLOSURE_SHEET_NAME,
  G12_NOTE_SECTION,
  isG12DisclosureApplicable,
  resolveG12CurrentStandard,
  type G12DisclosureVariant,
} from './g12NoteSectionMap'

/** 子表名 —— 与 note_template `tables[].name` 逐字一致（两版同名，各在自己的模板文件里） */
export const G12_MAIN_SUBTABLE = '净敞口套期收益'

export const G12_SUBTABLE = {
  listed: { main: G12_MAIN_SUBTABLE },
  soe: { main: G12_MAIN_SUBTABLE },
} as const satisfies Record<G12DisclosureVariant, Record<string, string>>

/** 标签列列头（= 模板 headers[0]，两版不同） */
export const G12_LABEL_HEADER = {
  listed: '项目',
  soe: '产生净敞口套期收益的来源',
} as const satisfies Record<G12DisclosureVariant, string>

export function g12ColumnsFor(variant: G12DisclosureVariant): Record<string, ColumnDef[]> {
  return {
    [G12_MAIN_SUBTABLE]: defineColumns([
      { key: 'label', label: G12_LABEL_HEADER[variant], is_label: true, flat: true },
      { key: 'current_amount', label: '本期发生额', format: 'amount', align: 'right' },
      { key: 'prior_amount', label: '上期发生额', format: 'amount', align: 'right' },
    ]),
  }
}

export const buildG12ListedColumns = (): Record<string, ColumnDef[]> => g12ColumnsFor('listed')
export const buildG12SoeColumns = (): Record<string, ColumnDef[]> => g12ColumnsFor('soe')

export interface G12SyncRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
}

export interface G12SyncSnapshot {
  /** 明细行（不含合计；合计由本模块按行求和，避免双真源） */
  rows: readonly G12SyncRow[]
  noteText: string
}

export interface G12SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns: Record<string, ColumnDef[]>
}

const TOTAL_LABEL = '合计'

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function buildG12MainSubTableRows(
  rows: readonly G12SyncRow[],
): Record<string, unknown>[] {
  const data = rows.map((r) => ({
    label: String(r.label ?? '').trim(),
    row_key: r.rowKey,
    current_amount: num(r.currentAmount),
    prior_amount: num(r.priorAmount),
    row_type: 'data',
  }))
  return [
    ...data,
    {
      label: TOTAL_LABEL,
      current_amount: data.reduce((s, r) => s + num(r.current_amount), 0),
      prior_amount: data.reduce((s, r) => s + num(r.prior_amount), 0),
      is_total: true,
      row_type: 'total',
    },
  ]
}

export function buildG12SubTableData(
  variant: G12DisclosureVariant,
  snap: G12SyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [G12_MAIN_SUBTABLE]: buildG12MainSubTableRows(snap.rows),
  }
  const text = String(snap.noteText ?? '').trim()
  if (text) {
    out._note_texts = [{ section: `${variant}-disclosure-note`, text }]
  }
  return out
}

/** @returns null=该变体不适用（不得同步到不适用章节） */
export function buildG12SyncPayload(
  wpId: string,
  variant: G12DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
  snap: G12SyncSnapshot,
): G12SyncFromWorkpaperPayload | null {
  if (!wpId || !isG12DisclosureApplicable(variant, applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: G12_DISCLOSURE_SHEET_NAME[variant],
    section_id: G12_NOTE_SECTION[variant],
    current_standard: resolveG12CurrentStandard(variant, applicableStandards),
    sub_table_data: buildG12SubTableData(variant, snap),
    columns: g12ColumnsFor(variant),
  }
}
