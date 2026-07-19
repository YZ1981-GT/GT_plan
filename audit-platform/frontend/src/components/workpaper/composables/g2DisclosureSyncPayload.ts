/**
 * G2 披露 → disclosure_notes sync payload
 * 子表名对齐 note_template：应收利息分类 / 重要逾期利息 / 坏账准备计提情况
 *   国企 §八、9 · 上市 §五、8
 */
import type { G2DisclosureVariant } from './g2NoteSectionMap'
import {
  G2_DISCLOSURE_SHEET_NAME,
  G2_NOTE_SECTION,
  isG2DisclosureApplicable,
  resolveG2CurrentStandard,
} from './g2NoteSectionMap'
import {
  eclRowTotal,
  overdueTotal,
  recomputeClassDerived,
  recomputeEclClosing,
  type G2SoeClassRow,
  type G2SoeEclRow,
  type G2SoeOverdueRow,
} from './g2SoeDisclosureRows'

export interface G2SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
}

export interface G2SoeSyncSnapshot {
  classRows: G2SoeClassRow[]
  overdueRows: G2SoeOverdueRow[]
  eclRows: G2SoeEclRow[]
  auditNote: string
}

export function buildG2SoeSubTableData(
  snap: G2SoeSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const classRows = recomputeClassDerived(snap.classRows)
  const eclRows = recomputeEclClosing(snap.eclRows)
  const overdueRows = snap.overdueRows.filter((r) => r.borrower || r.endAmount)

  return {
    应收利息分类: classRows.map((r) => ({
      label: r.label,
      end_balance: r.endAmount,
      prior_balance: r.priorAmount,
      row_key: r.rowKey,
      row_type: r.kind,
      is_total: r.kind === 'total' || r.kind === 'subtotal',
    })),
    重要逾期利息: [
      ...overdueRows.map((r) => ({
        borrower: r.borrower || '（未命名）',
        end_balance: r.endAmount,
        overdue_months: r.overdueMonths === '' ? null : r.overdueMonths,
        overdue_reason: r.overdueReason,
        impairment_basis: r.impairmentBasis,
      })),
      {
        label: '合计',
        end_balance: overdueTotal(overdueRows),
        is_total: true,
      },
    ],
    坏账准备计提情况: eclRows
      .filter((r) => r.kind !== 'header')
      .map((r) => ({
        label: r.label,
        stage1: r.stage1,
        stage2: r.stage2,
        stage3: r.stage3,
        total: eclRowTotal(r),
        row_key: r.rowKey,
        is_closing: r.rowKey === 'closing',
      })),
    _note_texts: [{ section: 'soe-audit-note', text: snap.auditNote }],
  }
}

export function buildG2SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: G2SoeSyncSnapshot,
): G2SyncFromWorkpaperPayload[] {
  const variant: G2DisclosureVariant = 'soe'
  if (!isG2DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: G2_DISCLOSURE_SHEET_NAME.soe,
      section_id: G2_NOTE_SECTION.soe,
      current_standard: resolveG2CurrentStandard(variant, applicableStandards),
      sub_table_data: buildG2SoeSubTableData(snap),
    },
  ]
}

/** 上市：子表结构与国企相同，章节/标准不同；备注 section 标记 listed */
export function buildG2ListedSubTableData(
  snap: G2SoeSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const data = buildG2SoeSubTableData(snap)
  return {
    ...data,
    _note_texts: [{ section: 'listed-audit-note', text: snap.auditNote }],
  }
}

export function buildG2ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: G2SoeSyncSnapshot,
): G2SyncFromWorkpaperPayload[] {
  const variant: G2DisclosureVariant = 'listed'
  if (!isG2DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: G2_DISCLOSURE_SHEET_NAME.listed,
      section_id: G2_NOTE_SECTION.listed,
      current_standard: resolveG2CurrentStandard(variant, applicableStandards),
      sub_table_data: buildG2ListedSubTableData(snap),
    },
  ]
}
