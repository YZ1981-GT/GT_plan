/**
 * G9 其他非流动金融资产披露 → `disclosure_notes` 同步载荷
 *
 * 子表名与列头逐字对齐 `note_template_listed.json §五、20` /
 * `note_template_soe.json §八、20`（由
 * `backend/scripts/fix/fix_note_g_cycle_structure.py` 对齐源模板后固定）。
 *
 * 🔴 标签列 label 用**模板 headers[0]**（`种类` / `项目`，无全角空格），
 *    而非组件 `el-table-column` 的视觉写法（`种  类` / `项  目`）。
 *    不一致会导致同步后表头错位（P5）。合计行 label 同理用模板的 `合计`。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.5
 */
import type { ColumnDef } from './disclosureColumnDefs'
import { defineColumns } from './disclosureColumnDefs'
import {
  G9_DISCLOSURE_SHEET_NAME,
  G9_MAIN_SUBTABLE,
  G9_NOTE_SECTION,
  isG9DisclosureApplicable,
  resolveG9CurrentStandard,
  type G9DisclosureVariant,
} from './g9NoteSectionMap'

/** 子表名映射（供契约测试 P1 参数化） */
export const G9_SUBTABLE = {
  listed: { main: G9_MAIN_SUBTABLE.listed },
  soe: { main: G9_MAIN_SUBTABLE.soe },
} as const satisfies Record<G9DisclosureVariant, Record<string, string>>

/** 列头 = 模板 headers（上市：种类/期末余额/上年年末余额；国企：项目/期末公允价值/期初公允价值） */
export const G9_TEMPLATE_HEADERS = {
  listed: { item: '种类', current: '期末余额', prior: '上年年末余额' },
  soe: { item: '项目', current: '期末公允价值', prior: '期初公允价值' },
} as const satisfies Record<G9DisclosureVariant, Record<string, string>>

/** 合计行 label —— 用模板字面量（`合计`，无全角空格） */
export const G9_TOTAL_LABEL = '合计'

export function g9ColumnsFor(variant: G9DisclosureVariant): Record<string, ColumnDef[]> {
  const h = G9_TEMPLATE_HEADERS[variant]
  return {
    [G9_MAIN_SUBTABLE[variant]]: defineColumns([
      { key: 'label', label: h.item, is_label: true, flat: true },
      { key: variant === 'listed' ? 'end_balance' : 'end_fair_value', label: h.current, format: 'amount', align: 'right' },
      { key: variant === 'listed' ? 'prior_balance' : 'opening_fair_value', label: h.prior, format: 'amount', align: 'right' },
    ]),
  }
}

export const buildG9ListedColumns = (): Record<string, ColumnDef[]> => g9ColumnsFor('listed')
export const buildG9SoeColumns = (): Record<string, ColumnDef[]> => g9ColumnsFor('soe')

export interface G9SyncRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
}

export interface G9SyncSnapshot {
  /** 明细行（不含合计；合计在此求和，与底稿 disclosureCurrentSum 同口径） */
  rows: readonly G9SyncRow[]
  noteText: string
}

export interface G9SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns: Record<string, ColumnDef[]>
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function buildG9MainSubTableRows(
  variant: G9DisclosureVariant,
  rows: readonly G9SyncRow[],
): Record<string, unknown>[] {
  const currentKey = variant === 'listed' ? 'end_balance' : 'end_fair_value'
  const priorKey = variant === 'listed' ? 'prior_balance' : 'opening_fair_value'
  const data = rows.map((r) => ({
    label: String(r.label ?? '').trim(),
    row_key: r.rowKey,
    [currentKey]: num(r.currentAmount),
    [priorKey]: num(r.priorAmount),
    row_type: 'data',
  }))
  return [
    ...data,
    {
      label: G9_TOTAL_LABEL,
      [currentKey]: data.reduce((s, r) => s + num(r[currentKey]), 0),
      [priorKey]: data.reduce((s, r) => s + num(r[priorKey]), 0),
      is_total: true,
      row_type: 'total',
    },
  ]
}

export function buildG9SubTableData(
  variant: G9DisclosureVariant,
  snap: G9SyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [G9_MAIN_SUBTABLE[variant]]: buildG9MainSubTableRows(variant, snap.rows),
  }
  const text = String(snap.noteText ?? '').trim()
  if (text) out._note_texts = [{ section: `${variant}-disclosure-note`, text }]
  return out
}

/** @returns null=该变体不适用 / 缺 wpId */
export function buildG9SyncPayload(
  wpId: string,
  variant: G9DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
  snap: G9SyncSnapshot,
): G9SyncFromWorkpaperPayload | null {
  if (!wpId || !isG9DisclosureApplicable(variant, applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: G9_DISCLOSURE_SHEET_NAME[variant],
    section_id: G9_NOTE_SECTION[variant],
    current_standard: resolveG9CurrentStandard(variant, applicableStandards),
    sub_table_data: buildG9SubTableData(variant, snap),
    columns: g9ColumnsFor(variant),
  }
}
