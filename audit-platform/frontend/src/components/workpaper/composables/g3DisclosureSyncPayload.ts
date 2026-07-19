/**
 * G3 应收股利披露 → disclosure_notes sync payload
 * 子表「应收股利」对齐 note_template_listed/soe §五、8 / §八、9
 */
import type { G3DisclosureVariant } from './g3NoteSectionMap'
import {
  G3_DISCLOSURE_SHEET_NAME,
  G3_NOTE_SECTION,
  isG3DisclosureApplicable,
  resolveG3CurrentStandard,
} from './g3NoteSectionMap'

export interface G3SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
}

export interface G3ListedRowSnap {
  investeeName: string
  openingBalance: number
  currentIncrease: number
  currentDecrease: number
  remark?: string
}

export interface G3SoeRowSnap {
  investeeName: string
  openingBalance: number
  currentChange: number
  remark?: string
}

function closingListed(r: G3ListedRowSnap): number {
  return (Number(r.openingBalance) || 0)
    + (Number(r.currentIncrease) || 0)
    - (Number(r.currentDecrease) || 0)
}

function closingSoe(r: G3SoeRowSnap): number {
  return (Number(r.openingBalance) || 0) + (Number(r.currentChange) || 0)
}

export function buildG3ListedSubTableData(
  rows: G3ListedRowSnap[],
  auditNote: string,
): Record<string, Record<string, unknown>[]> {
  const dataRows = rows.filter((r) => r.investeeName || closingListed(r))
  const endTotal = dataRows.reduce((s, r) => s + closingListed(r), 0)
  const priorTotal = dataRows.reduce((s, r) => s + (Number(r.openingBalance) || 0), 0)

  return {
    应收股利: [
      ...dataRows.map((r) => ({
        label: r.investeeName || '（未命名）',
        end_balance: closingListed(r),
        prior_balance: Number(r.openingBalance) || 0,
        current_increase: Number(r.currentIncrease) || 0,
        current_decrease: Number(r.currentDecrease) || 0,
        remark: r.remark || '',
        row_type: 'data',
      })),
      {
        label: '小计',
        end_balance: endTotal,
        prior_balance: priorTotal,
        is_total: true,
        row_type: 'subtotal',
      },
    ],
    _note_texts: [{ section: 'listed-audit-note', text: auditNote }],
  }
}

export function buildG3SoeSubTableData(
  rows: G3SoeRowSnap[],
  auditNote: string,
): Record<string, Record<string, unknown>[]> {
  const dataRows = rows.filter((r) => r.investeeName || closingSoe(r))
  const endTotal = dataRows.reduce((s, r) => s + closingSoe(r), 0)
  const priorTotal = dataRows.reduce((s, r) => s + (Number(r.openingBalance) || 0), 0)

  return {
    应收股利: [
      ...dataRows.map((r) => ({
        label: r.investeeName || '（未命名）',
        end_balance: closingSoe(r),
        prior_balance: Number(r.openingBalance) || 0,
        current_change: Number(r.currentChange) || 0,
        remark: r.remark || '',
        row_type: 'data',
      })),
      {
        label: '小计',
        end_balance: endTotal,
        prior_balance: priorTotal,
        is_total: true,
        row_type: 'subtotal',
      },
    ],
    _note_texts: [{ section: 'soe-audit-note', text: auditNote }],
  }
}

export function buildG3ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  rows: G3ListedRowSnap[],
  auditNote: string,
): G3SyncFromWorkpaperPayload[] {
  const variant: G3DisclosureVariant = 'listed'
  if (!isG3DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: G3_DISCLOSURE_SHEET_NAME.listed,
      section_id: G3_NOTE_SECTION.listed,
      current_standard: resolveG3CurrentStandard(variant, applicableStandards),
      sub_table_data: buildG3ListedSubTableData(rows, auditNote),
    },
  ]
}

export function buildG3SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  rows: G3SoeRowSnap[],
  auditNote: string,
): G3SyncFromWorkpaperPayload[] {
  const variant: G3DisclosureVariant = 'soe'
  if (!isG3DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: G3_DISCLOSURE_SHEET_NAME.soe,
      section_id: G3_NOTE_SECTION.soe,
      current_standard: resolveG3CurrentStandard(variant, applicableStandards),
      sub_table_data: buildG3SoeSubTableData(rows, auditNote),
    },
  ]
}
