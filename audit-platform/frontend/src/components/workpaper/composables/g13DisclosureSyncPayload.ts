/**
 * G13 披露 → disclosure_notes sync payload
 * 子表名对齐 note_template「产生公允价值变动收益的来源」
 * 空行不推送；「其中」备忘有数才推送且标记 of_which，合计排除其中。
 */
import { parseNum } from './useG13FormulaEngine'
import {
  G13_DISCLOSURE_LISTED_ROWS,
  G13_DISCLOSURE_SOE_ROWS,
  type G13DisclosureRowDef,
} from './g13Constants'
import {
  filterG13DisclosureRows,
  type G13DisclosureAmountRow,
} from './g13DisclosureVisibility'
import { buildG13NoteTextFromRows } from './g13NoteText'
import {
  G13_DISCLOSURE_SHEET_NAME,
  G13_MAIN_SUBTABLE,
  G13_NOTE_SECTION,
  isG13DisclosureApplicable,
  resolveG13CurrentStandard,
  type G13DisclosureVariant,
} from './g13NoteSectionMap'

import type { ColumnDef } from './disclosureColumnDefs'

export interface G13SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 G13TabDisclosure el-table-column */
  columns?: Record<string, ColumnDef[]>
}

// 公允价值变动收益列头：逐字取自 G13TabDisclosureListed/SOE
const G13_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '产生公允价值变动收益的来源', is_label: true },
  { key: 'current_amount', label: '本期发生额', format: 'amount' },
  { key: 'prior_amount', label: '上期发生额', format: 'amount' },
  { key: 'remark', label: '备注' },
]

export interface G13SyncRow extends G13DisclosureAmountRow {
  label: string
  remark?: string
}

export interface G13SyncSnapshot {
  rows: G13SyncRow[]
  noteText: string
  adjudicatedAmount?: number | null
}

/** 附注模板行标签（与 note_template_listed/soe 一致） */
export const G13_NOTE_TEMPLATE_LABEL: Record<string, { listed?: string; soe?: string }> = {
  trading_assets: { listed: '交易性金融资产（注1）', soe: '交易性金融资产' },
  designated_fv_assets: {
    listed: '其中：指定为以公允价值计量且其变动计入当期损益的金融资产',
  },
  derivatives: { listed: '衍生金融工具产生的公允价值变动收益' },
  derivative_assets: { soe: '衍生金融资产' },
  trading_liabilities: { listed: '交易性金融负债', soe: '交易性金融负债' },
  designated_fv_liabilities: {
    listed: '其中：指定为以公允价值计量且其变动计入当期损益的金融负债',
  },
  other_noncurrent: { listed: '其他非流动金融资产', soe: '其他非流动金融资产' },
  designated_fv_other: {
    listed: '其中：指定为以公允价值计量且其变动计入当期损益的金融资产计入当期损益的金融资产',
  },
  derivative_liabilities: { soe: '衍生金融负债' },
  investment_property: {
    listed: '按公允价值计量的投资性房地产',
    soe: '按公允价值计量的投资性房地产',
  },
  other: { listed: '其他', soe: '其他' },
}

function defsFor(variant: G13DisclosureVariant): readonly G13DisclosureRowDef[] {
  return variant === 'listed' ? G13_DISCLOSURE_LISTED_ROWS : G13_DISCLOSURE_SOE_ROWS
}

export function resolveG13NoteTemplateLabel(
  rowKey: string,
  variant: G13DisclosureVariant,
  fallbackLabel?: string,
): string {
  const mapped = G13_NOTE_TEMPLATE_LABEL[rowKey]?.[variant]
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

export function buildG13MainSubTableRows(
  rows: readonly G13SyncRow[],
  variant: G13DisclosureVariant,
): Record<string, unknown>[] {
  const defs = defsFor(variant)
  const defByKey = new Map(defs.map((d) => [d.rowKey, d]))
  const visible = filterG13DisclosureRows(rows, defs, { includeEmpty: false })

  const dataRows = visible.map((r) => {
    const def = defByKey.get(r.rowKey)
    const label = resolveG13NoteTemplateLabel(r.rowKey, variant, r.label)
    return mapAmountRow(
      label,
      r.rowKey,
      parseNum(r.currentAmount),
      parseNum(r.priorAmount),
      {
        of_which: Boolean(def?.ofWhich),
        ...(r.remark?.trim() ? { remark: r.remark.trim() } : {}),
      },
    )
  })

  let currentTotal = 0
  let priorTotal = 0
  for (const r of rows) {
    const def = defByKey.get(r.rowKey)
    if (def?.ofWhich) continue
    currentTotal += parseNum(r.currentAmount)
    priorTotal += parseNum(r.priorAmount)
  }

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
  snap: G13SyncSnapshot,
  variant: G13DisclosureVariant,
): Array<Record<string, string>> {
  const texts: Array<Record<string, string>> = []
  const note = snap.noteText.trim()
  if (note) {
    texts.push({ section: 'disclosure-note', text: note })
  } else {
    const auto = buildG13NoteTextFromRows(snap.rows, variant, {
      adjudicatedAmount: snap.adjudicatedAmount,
    })
    if (auto) texts.push({ section: 'disclosure-note', text: auto })
  }
  return texts
}

export function buildG13SubTableData(
  snap: G13SyncSnapshot,
  variant: G13DisclosureVariant,
): Record<string, Record<string, unknown>[]> {
  const result: Record<string, Record<string, unknown>[]> = {
    [G13_MAIN_SUBTABLE]: buildG13MainSubTableRows(snap.rows, variant),
  }
  const noteTexts = buildNoteTexts(snap, variant)
  if (noteTexts.length) result._note_texts = noteTexts
  return result
}

export function buildG13SyncPayloads(
  wpId: string,
  variant: G13DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
  snap: G13SyncSnapshot,
): G13SyncFromWorkpaperPayload[] {
  if (!isG13DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: G13_DISCLOSURE_SHEET_NAME[variant],
    section_id: G13_NOTE_SECTION[variant],
    current_standard: resolveG13CurrentStandard(variant, applicableStandards),
    sub_table_data: buildG13SubTableData(snap, variant),
    columns: { [G13_MAIN_SUBTABLE]: G13_COLUMNS },
  }]
}
