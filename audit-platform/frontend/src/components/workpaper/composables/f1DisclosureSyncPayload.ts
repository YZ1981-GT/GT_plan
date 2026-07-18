/**
 * F1 披露 → disclosure_notes sync payload
 * 子表名对齐 note_template_listed §五、7 / note_template_soe §八、7
 */
import type { F1DisclosureVariant } from './f1NoteSectionMap'
import {
  F1_DISCLOSURE_SHEET_NAME,
  F1_NOTE_SECTION,
  isF1DisclosureApplicable,
  resolveF1CurrentStandard,
} from './f1NoteSectionMap'

export interface F1SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
}

export interface F1ListedSyncSnapshot {
  agingRows: Array<{
    label: string
    endAmount: number
    endPct: number
    priorAmount: number
    priorPct: number
  }>
  agingTotal: {
    label: string
    endAmount: number
    endPct: number
    priorAmount: number
    priorPct: number
  }
  impairmentProvision: number
  agingNet: {
    label: string
    endAmount: number
    priorAmount: number
  }
  over1YearRows: Array<{
    debtorName: string
    endBalance: number
    proportionPct: number
    impairment: number
    reason: string
  }>
  over1YearTotal: {
    endBalance: number
    proportionPct: number
    impairment: number
  }
  top5Rows: Array<{
    entityName: string
    endBalance: number
    proportionPct: number
  }>
  top5Total: {
    endBalance: number
    proportionPct: number
  }
  top5SummaryText: string
  noteAging: string
  noteOver1Year: string
  noteTop5: string
}

export function buildF1ListedSubTableData(
  snap: F1ListedSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  return {
    预付款项按账龄披露: [
      ...snap.agingRows.map((r) => ({
        label: r.label,
        end_amount: r.endAmount,
        end_pct: r.endPct,
        prior_amount: r.priorAmount,
        prior_pct: r.priorPct,
      })),
      {
        label: '小计',
        end_amount: snap.agingTotal.endAmount,
        end_pct: snap.agingTotal.endPct,
        prior_amount: snap.agingTotal.priorAmount,
        prior_pct: snap.agingTotal.priorPct,
        is_total: true,
      },
      {
        label: '减：减值准备',
        end_amount: snap.impairmentProvision,
        prior_amount: 0,
      },
      {
        label: snap.agingNet.label || '合计',
        end_amount: snap.agingNet.endAmount,
        prior_amount: snap.agingNet.priorAmount,
        is_total: true,
      },
    ],
    账龄超过1年的重要预付款项: [
      ...snap.over1YearRows.map((r) => ({
        label: r.debtorName,
        balance: r.endBalance,
        proportion_pct: r.proportionPct,
        impairment: r.impairment,
        reason: r.reason,
      })),
      {
        label: '合计',
        balance: snap.over1YearTotal.endBalance,
        proportion_pct: snap.over1YearTotal.proportionPct,
        impairment: snap.over1YearTotal.impairment,
        is_total: true,
      },
    ],
    单位名称: [
      ...snap.top5Rows.map((r) => ({
        label: r.entityName,
        end_amount: r.endBalance,
        proportion_pct: r.proportionPct,
      })),
      {
        label: '合计',
        end_amount: snap.top5Total.endBalance,
        proportion_pct: snap.top5Total.proportionPct,
        is_total: true,
      },
    ],
    _note_texts: [
      { section: 'listed-note-aging', text: snap.noteAging },
      { section: 'listed-note-over1', text: snap.noteOver1Year },
      { section: 'listed-note-top5', text: snap.noteTop5 },
      { section: 'listed-top5-summary', text: snap.top5SummaryText },
    ],
  }
}

export interface F1SoeSyncSnapshot {
  agingRows: Array<{
    label: string
    endAmount: number
    endPct: number
    endBadDebt: number
    priorAmount: number
    priorPct: number
    priorBadDebt: number
  }>
  agingTotal: {
    label: string
    endAmount: number
    endPct: number
    endBadDebt: number
    priorAmount: number
    priorPct: number
    priorBadDebt: number
  }
  over1YearRows: Array<{
    creditorUnit: string
    debtorUnit: string
    endBalance: number
    agingLabel: string
    reason: string
  }>
  over1YearTotal: { endBalance: number }
  top5Rows: Array<{
    debtorName: string
    endBalance: number
    proportionPct: number
    badDebt: number
  }>
  top5Total: {
    endBalance: number
    proportionPct: number
    badDebt: number
  }
  noteAging: string
  noteOver1Year: string
  noteTop5: string
}

export function buildF1SoeSubTableData(
  snap: F1SoeSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  return {
    预付款项按账龄列示: [
      ...snap.agingRows.map((r) => ({
        label: r.label,
        end_amount: r.endAmount,
        end_pct: r.endPct,
        end_bad_debt: r.endBadDebt,
        prior_amount: r.priorAmount,
        prior_pct: r.priorPct,
        prior_bad_debt: r.priorBadDebt,
      })),
      {
        label: snap.agingTotal.label || '合计',
        end_amount: snap.agingTotal.endAmount,
        end_pct: snap.agingTotal.endPct,
        end_bad_debt: snap.agingTotal.endBadDebt,
        prior_amount: snap.agingTotal.priorAmount,
        prior_pct: snap.agingTotal.priorPct,
        prior_bad_debt: snap.agingTotal.priorBadDebt,
        is_total: true,
      },
    ],
    账龄超过1年的大额预付款项: [
      ...snap.over1YearRows.map((r) => ({
        creditor_unit: r.creditorUnit,
        debtor_unit: r.debtorUnit,
        end_balance: r.endBalance,
        aging: r.agingLabel,
        reason: r.reason,
      })),
      {
        label: '合计',
        end_balance: snap.over1YearTotal.endBalance,
        is_total: true,
      },
    ],
    按欠款方归集的期末余额前五名的预付款项: [
      ...snap.top5Rows.map((r) => ({
        label: r.debtorName,
        end_amount: r.endBalance,
        proportion_pct: r.proportionPct,
        bad_debt: r.badDebt,
      })),
      {
        label: '合计',
        end_amount: snap.top5Total.endBalance,
        proportion_pct: snap.top5Total.proportionPct,
        bad_debt: snap.top5Total.badDebt,
        is_total: true,
      },
    ],
    _note_texts: [
      { section: 'soe-note-aging', text: snap.noteAging },
      { section: 'soe-note-over1', text: snap.noteOver1Year },
      { section: 'soe-note-top5', text: snap.noteTop5 },
    ],
  }
}

export function buildF1SyncPayload(
  variant: F1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  subTableData: Record<string, Record<string, unknown>[]>,
): F1SyncFromWorkpaperPayload | null {
  if (!isF1DisclosureApplicable(variant, applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: F1_DISCLOSURE_SHEET_NAME[variant],
    section_id: F1_NOTE_SECTION[variant],
    current_standard: resolveF1CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
  }
}
