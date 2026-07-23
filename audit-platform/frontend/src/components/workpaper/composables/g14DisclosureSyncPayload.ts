/**
 * G14 披露 → disclosure_notes sync payload
 * 子表名对齐 note_template「项  目」(上市) / 「信用减值损失」(国企)
 * 空行不推送。
 */
import { parseNum } from './useG14FormulaEngine'
import {
  G14_DISCLOSURE_LISTED_ROWS,
  G14_DISCLOSURE_SOE_ROWS,
} from './g14Constants'
import {
  filterG14DisclosureRows,
  type G14DisclosureAmountRow,
} from './g14DisclosureVisibility'
import { buildG14NoteTextFromRows } from './g14NoteText'
import {
  G14_DISCLOSURE_SHEET_NAME,
  G14_MAIN_SUBTABLE,
  G14_NOTE_SECTION,
  isG14DisclosureApplicable,
  resolveG14CurrentStandard,
  type G14DisclosureVariant,
} from './g14NoteSectionMap'

import type { ColumnDef } from './disclosureColumnDefs'

export interface G14SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 G14TabDisclosure el-table-column */
  columns?: Record<string, ColumnDef[]>
}

// 信用减值损失列头：逐字取自 G14TabDisclosureListed/SOE（项目/本期发生额/上期发生额/备注）
const G14_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'current_amount', label: '本期发生额', format: 'amount' },
  { key: 'prior_amount', label: '上期发生额', format: 'amount' },
  { key: 'remark', label: '备注' },
]

export interface G14SyncRow extends G14DisclosureAmountRow {
  label: string
  remark?: string
}

export interface G14SyncSnapshot {
  rows: G14SyncRow[]
  noteText: string
  adjudicatedAmount?: number | null
}

/** 附注模板行标签（与 note_template_listed/soe 一致） */
export const G14_NOTE_TEMPLATE_LABEL: Record<string, { listed?: string; soe?: string }> = {
  notes: { listed: '应收票据坏账损失' },
  ar: { listed: '应收账款坏账损失' },
  rfin: { listed: '应收款项融资坏账损失' },
  othar: { listed: '其他应收款坏账损失' },
  debt: { listed: '债权投资减值损失', soe: '债权投资减值损失' },
  othdebt: { listed: '其他债权投资减值损失', soe: '其他债权投资减值损失' },
  ltar: { listed: '长期应收款坏账损失' },
  ca: { listed: '合同资产减值损失' },
  guarantee: { listed: '财务担保预计损失' },
  other: { listed: '其他', soe: '其他' },
  bad_debt: { soe: '坏账损失' },
}

function defsFor(variant: G14DisclosureVariant) {
  return variant === 'listed' ? G14_DISCLOSURE_LISTED_ROWS : G14_DISCLOSURE_SOE_ROWS
}

export function resolveG14NoteTemplateLabel(
  rowKey: string,
  variant: G14DisclosureVariant,
  fallbackLabel?: string,
): string {
  const mapped = G14_NOTE_TEMPLATE_LABEL[rowKey]?.[variant]
  if (mapped) return mapped
  return String(fallbackLabel ?? rowKey).replace(/^\s+/, '').trim()
}

function mapAmountRow(
  label: string,
  rowKey: string,
  currentAmount: number,
  priorAmount: number,
  extra?: Record<string, unknown>,
): Record<string, unknown> {
  return {
    label: label.trim(),
    row_key: rowKey,
    current_amount: currentAmount,
    prior_amount: priorAmount,
    row_type: 'data',
    ...extra,
  }
}

export function buildG14MainSubTableRows(
  rows: readonly G14SyncRow[],
  variant: G14DisclosureVariant,
): Record<string, unknown>[] {
  const visible = filterG14DisclosureRows(rows, { includeEmpty: false })

  const dataRows = visible.map((r) => {
    const label = resolveG14NoteTemplateLabel(r.rowKey, variant, r.label)
    return mapAmountRow(
      label,
      r.rowKey,
      parseNum(r.currentAmount),
      parseNum(r.priorAmount),
      {
        ...(r.remark?.trim() ? { remark: r.remark.trim() } : {}),
      },
    )
  })

  const currentTotal = rows.reduce((s, r) => s + parseNum(r.currentAmount), 0)
  const priorTotal = rows.reduce((s, r) => s + parseNum(r.priorAmount), 0)

  return [
    ...dataRows,
    {
      label: '合计',
      current_amount: currentTotal,
      prior_amount: priorTotal,
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

function buildNoteTexts(
  snap: G14SyncSnapshot,
  variant: G14DisclosureVariant,
): Array<Record<string, string>> {
  const texts: Array<Record<string, string>> = []
  const note = snap.noteText.trim()
  if (note) {
    texts.push({ section: 'disclosure-note', text: note })
  } else {
    const auto = buildG14NoteTextFromRows(snap.rows, variant, {
      adjudicatedAmount: snap.adjudicatedAmount,
    })
    if (auto) texts.push({ section: 'disclosure-note', text: auto })
  }
  return texts
}

export function buildG14SubTableData(
  snap: G14SyncSnapshot,
  variant: G14DisclosureVariant,
): Record<string, Record<string, unknown>[]> {
  const result: Record<string, Record<string, unknown>[]> = {
    [G14_MAIN_SUBTABLE[variant]]: buildG14MainSubTableRows(snap.rows, variant),
  }
  const noteTexts = buildNoteTexts(snap, variant)
  if (noteTexts.length) result._note_texts = noteTexts
  return result
}

export function buildG14SyncPayloads(
  wpId: string,
  variant: G14DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
  snap: G14SyncSnapshot,
): G14SyncFromWorkpaperPayload[] {
  if (!isG14DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: G14_DISCLOSURE_SHEET_NAME[variant],
    section_id: G14_NOTE_SECTION[variant],
    current_standard: resolveG14CurrentStandard(variant, applicableStandards),
    sub_table_data: buildG14SubTableData(snap, variant),
    columns: { [G14_MAIN_SUBTABLE[variant]]: G14_COLUMNS },
  }]
}

/** 供测试：确认 defs 与模板标签覆盖 */
export function g14DisclosureDefKeys(variant: G14DisclosureVariant): string[] {
  return defsFor(variant).map((d) => d.rowKey)
}
