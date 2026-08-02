/**
 * I4 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、29（本期减少=摊销+其他减少）
 * - 国企：note_template_soe §八、30（摊销/其他减少分列 + 原因）
 */
import {
  I4_DISCLOSURE_SHEET_NAME,
  I4_LISTED_SUBTABLE,
  I4_NOTE_SECTION,
  I4_SOE_SUBTABLE,
  isI4DisclosureApplicable,
  resolveI4CurrentStandard,
  type I4DisclosureVariant,
} from './i4NoteSectionMap'
import {
  calcI4DisclosureEnd,
  summarizeI4Disclosure,
  type I4DisclosureRow,
} from './i4DisclosureModel'
import type { ColumnDef } from './disclosureColumnDefs'

export interface I4SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 note_template §五、29/§八、30 变动表列 */
  columns?: Record<string, ColumnDef[]>
}

// 上市变动表列头 — 两级表头：「本期减少」下辖「本期摊销」/「其他减少」
const I4_LISTED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true },
  { key: '期初余额', label: '期初数', format: 'amount' },
  { key: '本期增加', label: '本期增加', format: 'amount' },
  { key: '本期摊销', label: '本期摊销', group: '本期减少', format: 'amount' },
  { key: '其他减少', label: '其他减少', group: '本期减少', format: 'amount' },
  { key: '期末余额', label: '期末数', format: 'amount' },
]

// 国企变动表列头（7 列 flat：摊销/其他减少分列 + 原因）
const I4_SOE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: '期初余额', label: '期初余额', format: 'amount', flat: true },
  { key: '本期增加额', label: '本期增加额', format: 'amount', flat: true },
  { key: '本期摊销额', label: '本期摊销额', format: 'amount', flat: true },
  { key: '其他减少额', label: '其他减少额', format: 'amount', flat: true },
  { key: '期末余额', label: '期末余额', format: 'amount', flat: true },
  { key: '其他减少的原因', label: '其他减少的原因', flat: true },
]

export interface I4DisclosureSyncSnapshot {
  rows: I4DisclosureRow[]
  currentPortion?: number
  otherNote?: string
  footnote?: string
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _fmtAmt(n: number): string {
  if (!n) return '0.00'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function buildI4ListedFootnote(currentPortion: number): string {
  return `说明：1年内到期的长期待摊费用 ${_fmtAmt(currentPortion)} 元。按准则提示，摊销期限不足一年的部分仍在长期待摊费用中列报，不转入「一年内到期的非流动资产」。`
}

export function buildI4ListedSubTableData(state: I4DisclosureSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const dataRows = (state.rows || [])
    .filter((r) => r.item || Math.abs(_num(r.beginBalance) + _num(r.increase) + _num(r.amortization) + _num(r.otherDecrease)) > 0.005)
    .map((r) => {
      const end = calcI4DisclosureEnd(r)
      return {
        label: r.item || '（未命名）',
        期初余额: _num(r.beginBalance),
        本期增加: _num(r.increase),
        本期摊销: _num(r.amortization),
        其他减少: _num(r.otherDecrease),
        期末余额: end,
        is_total: false,
      }
    })

  const totals = summarizeI4Disclosure(state.rows || [])
  dataRows.push({
    label: '合计',
    期初余额: totals.beginBalance,
    本期增加: totals.increase,
    本期摊销: totals.amortization,
    其他减少: totals.otherDecrease,
    期末余额: totals.endBalance,
    is_total: true,
  })

  const notes = [
    { section: 'listed-current-portion', title: '一年内到期部分说明', text: (state.footnote || buildI4ListedFootnote(state.currentPortion ?? 0)).trim() },
    { section: 'listed-other', title: '长期待摊费用补充说明', text: (state.otherNote || '').trim() },
  ].filter((n) => n.text)

  return {
    [I4_LISTED_SUBTABLE.movement]: dataRows,
    ...(notes.length ? { _note_texts: notes as unknown as Record<string, unknown>[] } : {}),
  }
}

export function buildI4SoeSubTableData(state: I4DisclosureSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const dataRows = (state.rows || [])
    .filter((r) => r.item || Math.abs(_num(r.beginBalance) + _num(r.increase) + _num(r.amortization) + _num(r.otherDecrease)) > 0.005)
    .map((r) => {
      const end = calcI4DisclosureEnd(r)
      return {
        label: r.item || '（未命名）',
        期初余额: _num(r.beginBalance),
        本期增加额: _num(r.increase),
        本期摊销额: _num(r.amortization),
        其他减少额: _num(r.otherDecrease),
        期末余额: end,
        其他减少的原因: r.otherDecreaseReason || '',
        is_total: false,
      }
    })

  const totals = summarizeI4Disclosure(state.rows || [])
  dataRows.push({
    label: '合计',
    期初余额: totals.beginBalance,
    本期增加额: totals.increase,
    本期摊销额: totals.amortization,
    其他减少额: totals.otherDecrease,
    期末余额: totals.endBalance,
    其他减少的原因: '',
    is_total: true,
  })

  const notes = [
    { section: 'soe-other', title: '长期待摊费用补充说明', text: (state.otherNote || '').trim() },
  ].filter((n) => n.text)

  return {
    [I4_SOE_SUBTABLE.movement]: dataRows,
    ...(notes.length ? { _note_texts: notes as unknown as Record<string, unknown>[] } : {}),
  }
}

export function buildI4ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: I4DisclosureSyncSnapshot,
): I4SyncFromWorkpaperPayload[] {
  const variant: I4DisclosureVariant = 'listed'
  if (!isI4DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I4_DISCLOSURE_SHEET_NAME.listed,
    section_id: I4_NOTE_SECTION.listed,
    current_standard: resolveI4CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI4ListedSubTableData(state),
    columns: { [I4_LISTED_SUBTABLE.movement]: I4_LISTED_COLUMNS },
  }]
}

export function buildI4SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: I4DisclosureSyncSnapshot,
): I4SyncFromWorkpaperPayload[] {
  const variant: I4DisclosureVariant = 'soe'
  if (!isI4DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I4_DISCLOSURE_SHEET_NAME.soe,
    section_id: I4_NOTE_SECTION.soe,
    current_standard: resolveI4CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI4SoeSubTableData(state),
    columns: { [I4_SOE_SUBTABLE.movement]: I4_SOE_COLUMNS },
  }]
}
