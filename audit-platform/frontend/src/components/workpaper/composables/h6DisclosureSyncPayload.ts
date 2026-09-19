/**
 * H6 披露 → disclosure_notes sync payload
 *
 * 仅推送「固定资产清理」子表 + 超1年进展说明，并浅合并刷新汇总表「固定资产」中的清理行。
 * 不覆盖 H1 已推送的固定资产变动/闲置等其他子表（与 H4→H2 工程物资模式一致）。
 */
import {
  H6_CLEARING_SUBTABLE,
  H6_DISCLOSURE_SHEET_NAME,
  H6_NOTE_SECTION,
  H6_SUMMARY_SUBTABLE,
  isH6DisclosureApplicable,
  resolveH6CurrentStandard,
  type H6DisclosureVariant,
} from './h6NoteSectionMap'
import {
  n,
  sumClearing,
  type H6ClearingRow,
  type H6DisclosureState,
} from './h6DisclosureModel'
import type { ColumnDef } from './disclosureColumnDefs'

export interface H6SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 H6TabDisclosure el-table-column（清理表） */
  columns?: Record<string, ColumnDef[]>
}

// 固定资产清理表列头（英文键 → 源对齐；listed 期末/上年年末余额、soe 期末/期初账面价值）
const H6_LISTED_CLEARING_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
  { key: 'prior_balance', label: '上年年末余额', format: 'amount' },
  { key: 'reason', label: '转入清理的原因' },
]
const H6_SOE_CLEARING_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_carrying', label: '期末账面价值', format: 'amount' },
  { key: 'begin_carrying', label: '期初账面价值', format: 'amount' },
  { key: 'reason', label: '转入清理的原因' },
]

function amt(v: number): number {
  return Math.round(n(v) * 100) / 100
}

/** 上市：期末余额 / 上年年末余额 */
export function buildH6ListedClearingSubTable(rows: H6ClearingRow[]): Record<string, unknown>[] {
  const data = rows
    .filter((r) => r.name.trim() || n(r.endBalance) !== 0 || n(r.priorBalance) !== 0)
    .map((r) => ({
      label: r.name,
      end_balance: amt(r.endBalance),
      prior_balance: amt(r.priorBalance),
      reason: r.reason || '',
      row_type: 'data' as const,
    }))
  const t = sumClearing(rows)
  return [
    ...data,
    {
      label: '合计',
      end_balance: amt(t.endBalance),
      prior_balance: amt(t.priorBalance),
      reason: '',
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

/** 国企：期末/期初账面价值 */
export function buildH6SoeClearingSubTable(rows: H6ClearingRow[]): Record<string, unknown>[] {
  const data = rows
    .filter((r) => r.name.trim() || n(r.endBalance) !== 0 || n(r.priorBalance) !== 0)
    .map((r) => ({
      label: r.name,
      end_carrying: amt(r.endBalance),
      begin_carrying: amt(r.priorBalance),
      reason: r.reason || '',
      row_type: 'data' as const,
    }))
  const t = sumClearing(rows)
  return [
    ...data,
    {
      label: '合计',
      end_carrying: amt(t.endBalance),
      begin_carrying: amt(t.priorBalance),
      reason: '',
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

/**
 * 若已有「固定资产」汇总表，刷新其中「固定资产清理」行及合计行。
 * FA 行：若本底稿填了 faEnd/faPrior 则一并刷新；否则仅改清理行。
 */
export function patchFaSummaryClearingRow(
  existingSub: Record<string, unknown>,
  state: H6DisclosureState,
  variant: H6DisclosureVariant,
): Record<string, unknown> {
  const key = H6_SUMMARY_SUBTABLE
  const raw = existingSub[key]
  if (!Array.isArray(raw)) return existingSub

  const tot = sumClearing(state.clearingRows)
  const faEnd = n(state.faEnd)
  const faPrior = n(state.faPrior)
  const useFa = faEnd !== 0 || faPrior !== 0

  const next = (raw as any[]).map((row) => {
    const label = String(row?.label ?? row?.name ?? '')
    if (label === '固定资产清理' || (label.includes('固定资产清理') && !label.includes('合计'))) {
      if (variant === 'listed') {
        return { ...row, end_balance: amt(tot.endBalance), prior_balance: amt(tot.priorBalance) }
      }
      return { ...row, end_carrying: amt(tot.endBalance), begin_carrying: amt(tot.priorBalance) }
    }
    if (useFa && (label === '固定资产' || label === '固定资产账面价值')) {
      if (variant === 'listed') {
        return { ...row, end_balance: amt(faEnd), prior_balance: amt(faPrior) }
      }
      return { ...row, end_carrying: amt(faEnd), begin_carrying: amt(faPrior) }
    }
    return row
  })

  // 重算合计行
  let faE = faEnd
  let faP = faPrior
  let clrE = tot.endBalance
  let clrP = tot.priorBalance
  for (const row of next) {
    const label = String(row?.label ?? row?.name ?? '')
    if (label === '固定资产' || label === '固定资产账面价值') {
      faE = variant === 'listed' ? n(row.end_balance) : n(row.end_carrying)
      faP = variant === 'listed' ? n(row.prior_balance) : n(row.begin_carrying)
    }
    if (label.includes('固定资产清理') && !label.includes('合计')) {
      clrE = variant === 'listed' ? n(row.end_balance) : n(row.end_carrying)
      clrP = variant === 'listed' ? n(row.prior_balance) : n(row.begin_carrying)
    }
  }
  const withTotal = next.map((row) => {
    const label = String(row?.label ?? row?.name ?? '')
    if (label === '合计' || row?.is_total) {
      if (variant === 'listed') {
        return { ...row, end_balance: amt(faE + clrE), prior_balance: amt(faP + clrP), is_total: true }
      }
      return { ...row, end_carrying: amt(faE + clrE), begin_carrying: amt(faP + clrP), is_total: true }
    }
    return row
  })

  return { ...existingSub, [key]: withTotal }
}

function buildNoteTexts(state: H6DisclosureState, variant: H6DisclosureVariant): Record<string, unknown>[] {
  if (!state.clearingNote?.trim()) return []
  return [
    {
      section: variant === 'listed' ? 'clearing-over-1y' : 'soe-clearing-progress',
      text: state.clearingNote.trim(),
    },
  ]
}

export function buildH6ListedSubTableData(
  state: H6DisclosureState,
  opts?: { existingSubTableData?: Record<string, unknown> },
): Record<string, Record<string, unknown>[]> {
  let sub: Record<string, unknown> = {
    ...(opts?.existingSubTableData || {}),
    [H6_CLEARING_SUBTABLE]: buildH6ListedClearingSubTable(state.clearingRows),
  }
  sub = patchFaSummaryClearingRow(sub, state, 'listed')
  const notes = buildNoteTexts(state, 'listed')
  if (notes.length) sub._note_texts = notes
  return sub as Record<string, Record<string, unknown>[]>
}

export function buildH6SoeSubTableData(
  state: H6DisclosureState,
  opts?: { existingSubTableData?: Record<string, unknown> },
): Record<string, Record<string, unknown>[]> {
  let sub: Record<string, unknown> = {
    ...(opts?.existingSubTableData || {}),
    [H6_CLEARING_SUBTABLE]: buildH6SoeClearingSubTable(state.clearingRows),
  }
  sub = patchFaSummaryClearingRow(sub, state, 'soe')
  const notes = buildNoteTexts(state, 'soe')
  if (notes.length) sub._note_texts = notes
  return sub as Record<string, Record<string, unknown>[]>
}

export function buildH6ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H6DisclosureState,
  opts?: { existingSubTableData?: Record<string, unknown> },
): H6SyncFromWorkpaperPayload[] {
  if (!isH6DisclosureApplicable('listed', applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: H6_DISCLOSURE_SHEET_NAME.listed,
      section_id: H6_NOTE_SECTION.listed,
      current_standard: resolveH6CurrentStandard('listed', applicableStandards),
      sub_table_data: buildH6ListedSubTableData(state, opts),
      columns: { [H6_CLEARING_SUBTABLE]: H6_LISTED_CLEARING_COLUMNS },
    },
  ]
}

export function buildH6SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H6DisclosureState,
  opts?: { existingSubTableData?: Record<string, unknown> },
): H6SyncFromWorkpaperPayload[] {
  if (!isH6DisclosureApplicable('soe', applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: H6_DISCLOSURE_SHEET_NAME.soe,
      section_id: H6_NOTE_SECTION.soe,
      current_standard: resolveH6CurrentStandard('soe', applicableStandards),
      sub_table_data: buildH6SoeSubTableData(state, opts),
      columns: { [H6_CLEARING_SUBTABLE]: H6_SOE_CLEARING_COLUMNS },
    },
  ]
}
