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

import type { ColumnDef } from './disclosureColumnDefs'

export interface F1SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  /**
   * 审计年度（显式传入，不依赖后端兜底）。
   * 后端 `_resolve_target_year` 优先用 payload.year，其次 projects.audit_year，
   * 最后才是服务器自然年 —— 显式传 year 可避免跨年场景写到错误年度的附注。
   */
  year?: number
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 F1TabDisclosure el-table-column（多级表头扁平合并） */
  columns?: Record<string, ColumnDef[]>
}

// F1 子表英文键 → 源对齐中文列头（键与 buildF1*SubTableData 行键逐字一致）
const F1_LISTED_COLUMNS: Record<string, ColumnDef[]> = {
  预付款项按账龄披露: [
    { key: 'label', label: '账龄', is_label: true },
    { key: 'end_amount', label: '期末数-金额', format: 'amount' },
    { key: 'end_pct', label: '期末数-比例%' },
    { key: 'prior_amount', label: '上年年末数-金额', format: 'amount' },
    { key: 'prior_pct', label: '上年年末数-比例%' },
  ],
  账龄超过1年的重要预付款项: [
    { key: 'label', label: '债务人名称', is_label: true },
    { key: 'balance', label: '期末余额', format: 'amount' },
    { key: 'proportion_pct', label: '占预付款项合计的比例(%)' },
    { key: 'reason', label: '未偿还原因' },
  ],
  单位名称: [
    { key: 'label', label: '单位名称', is_label: true },
    { key: 'end_amount', label: '预付款项期末余额', format: 'amount' },
    { key: 'proportion_pct', label: '占预付款项期末余额合计数的比例%' },
  ],
}

const F1_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  预付款项按账龄列示: [
    { key: 'label', label: '账龄', is_label: true },
    { key: 'end_amount', label: '期末数-账面余额金额', format: 'amount' },
    { key: 'end_pct', label: '期末数-账面余额比例%' },
    { key: 'end_bad_debt', label: '期末数-坏账准备', format: 'amount' },
    { key: 'prior_amount', label: '期初数-账面余额金额', format: 'amount' },
    { key: 'prior_pct', label: '期初数-账面余额比例%' },
    { key: 'prior_bad_debt', label: '期初数-坏账准备', format: 'amount' },
  ],
  账龄超过1年的大额预付款项: [
    { key: 'creditor_unit', label: '债权单位', is_label: true },
    { key: 'debtor_unit', label: '债务单位' },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
    { key: 'aging', label: '账龄' },
    { key: 'reason', label: '未结算的原因' },
  ],
  按欠款方归集的期末余额前五名的预付款项: [
    { key: 'label', label: '债务人名称', is_label: true },
    { key: 'end_amount', label: '账面余额', format: 'amount' },
    { key: 'proportion_pct', label: '占预付款项合计的比例(%)' },
    { key: 'bad_debt', label: '坏账准备', format: 'amount' },
  ],
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
  year?: number | null,
): F1SyncFromWorkpaperPayload | null {
  if (!isF1DisclosureApplicable(variant, applicableStandards)) return null
  const payload: F1SyncFromWorkpaperPayload = {
    wp_id: wpId,
    sheet_name: F1_DISCLOSURE_SHEET_NAME[variant],
    section_id: F1_NOTE_SECTION[variant],
    current_standard: resolveF1CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
    columns: variant === 'listed' ? F1_LISTED_COLUMNS : F1_SOE_COLUMNS,
  }
  const y = Number(year ?? 0)
  if (y > 0) payload.year = y
  return payload
}
