/**
 * G8 其他权益工具投资披露 → `disclosure_notes` 同步载荷（两张表）
 *
 * 子表名与列头逐字对齐 `note_template_listed.json §五、19` /
 * `note_template_soe.json §八、19`（由
 * `backend/scripts/fix/fix_note_g_cycle_structure.py` 对齐源模板后固定）：
 *
 * | 表 | 上市 | 国企 |
 * |----|------|------|
 * | ① 余额表 | `其他权益工具投资` | `其他权益工具投资情况` |
 * | ② 逐项目 OCI/股利/终止确认 | `期末其他权益工具投资情况` | 同左 |
 *
 * 🔴 两版第 2 张表**列头文案不同**（上市「利得和损失」+「因终止确认转入留存收益…」；
 *    国企「利得或损失」+「其他综合收益转入留存收益…」），且列序不同（上市把股利放第 3 列，
 *    国企放第 1 列）→ 不得共用一套 ColumnDef。
 *
 * 🔴 上市第 2 张表源模板**无合计行**（附注模版 md 只有 3 个空行），国企有 → 合计行按变体决定。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.4
 */
import type { ColumnDef } from './disclosureColumnDefs'
import { defineColumns } from './disclosureColumnDefs'
import {
  G8_DETAIL_SUBTABLE,
  G8_DISCLOSURE_SHEET_NAME,
  G8_MAIN_SUBTABLE,
  G8_NOTE_SECTION,
  isG8DisclosureApplicable,
  resolveG8CurrentStandard,
  type G8DisclosureVariant,
} from './g8NoteSectionMap'

export const G8_SUBTABLE = {
  listed: { main: G8_MAIN_SUBTABLE.listed, detail: G8_DETAIL_SUBTABLE },
  soe: { main: G8_MAIN_SUBTABLE.soe, detail: G8_DETAIL_SUBTABLE },
} as const satisfies Record<G8DisclosureVariant, Record<string, string>>

/** 余额表列头（= 模板 headers；上市对上年年末、国企对期初） */
export const G8_BALANCE_HEADERS = {
  listed: { item: '项目', closing: '期末余额', prior: '上年年末余额' },
  soe: { item: '项目', closing: '期末余额', prior: '期初余额' },
} as const satisfies Record<G8DisclosureVariant, Record<string, string>>

export const G8_TOTAL_LABEL = '合计'

function balanceColumns(variant: G8DisclosureVariant): ColumnDef[] {
  const h = G8_BALANCE_HEADERS[variant]
  return defineColumns([
    { key: 'label', label: h.item, is_label: true, flat: true },
    { key: 'end_balance', label: h.closing, format: 'amount', align: 'right' },
    {
      key: variant === 'listed' ? 'prior_balance' : 'opening_balance',
      label: h.prior,
      format: 'amount',
      align: 'right',
    },
  ])
}

/** 上市第 2 张表：项目 / OCI本期 / OCI累计 / 股利 / 终止确认转入留存收益 / 终止确认原因 */
function listedDetailColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'oci_current', label: '本期计入其他综合收益的利得和损失', format: 'amount', align: 'right' },
    { key: 'oci_cumulative', label: '本期末累计计入其他综合收益的利得和损失', format: 'amount', align: 'right' },
    { key: 'dividend_income', label: '本期确认的股利收入', format: 'amount', align: 'right' },
    { key: 'derecognition_to_re', label: '因终止确认转入留存收益的累计利得和损失', format: 'amount', align: 'right' },
    { key: 'derecognition_reason', label: '终止确认的原因' },
  ])
}

/** 国企第 2 张表：项目名称 / 股利 / OCI本期 / OCI累计 / OCI转入留存收益 / 转入原因 */
function soeDetailColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目名称', is_label: true, flat: true },
    { key: 'dividend_income', label: '本期确认的股利收入', format: 'amount', align: 'right' },
    { key: 'oci_current', label: '本期计入其他综合收益的利得或损失', format: 'amount', align: 'right' },
    { key: 'oci_cumulative', label: '截至期末累计计入其他综合收益的利得或损失', format: 'amount', align: 'right' },
    { key: 'oci_to_re', label: '其他综合收益转入留存收益的金额', format: 'amount', align: 'right' },
    { key: 'oci_to_re_reason', label: '其他综合收益转入留存收益的原因' },
  ])
}

export function g8ColumnsFor(variant: G8DisclosureVariant): Record<string, ColumnDef[]> {
  return {
    [G8_MAIN_SUBTABLE[variant]]: balanceColumns(variant),
    [G8_DETAIL_SUBTABLE]: variant === 'listed' ? listedDetailColumns() : soeDetailColumns(),
  }
}

export const buildG8ListedColumns = (): Record<string, ColumnDef[]> => g8ColumnsFor('listed')
export const buildG8SoeColumns = (): Record<string, ColumnDef[]> => g8ColumnsFor('soe')

export interface G8BalanceSyncRow {
  label: string
  closing: number
  prior: number
}

/** 逐项目明细行（两版字段同名，列头/列序差异由 ColumnDef 承载） */
export interface G8DetailSyncRow {
  label: string
  ociPeriod: number
  ociCumulative: number
  dividend: number
  /** 上市=因终止确认转入留存收益；国企=其他综合收益转入留存收益 */
  transferAmount: number
  transferReason: string
}

export interface G8SyncSnapshot {
  balanceRows: readonly G8BalanceSyncRow[]
  detailRows: readonly G8DetailSyncRow[]
  /** 指定为 FVOCI 的原因（叙事，进 _note_texts） */
  designationText: string
  noteText: string
}

export interface G8SyncFromWorkpaperPayload {
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

function isBlankRow(r: G8BalanceSyncRow): boolean {
  return !String(r.label ?? '').trim() && num(r.closing) === 0 && num(r.prior) === 0
}

export function buildG8BalanceRows(
  variant: G8DisclosureVariant,
  rows: readonly G8BalanceSyncRow[],
): Record<string, unknown>[] {
  const priorKey = variant === 'listed' ? 'prior_balance' : 'opening_balance'
  const data = rows.filter((r) => !isBlankRow(r)).map((r) => ({
    label: String(r.label ?? '').trim(),
    end_balance: num(r.closing),
    [priorKey]: num(r.prior),
    row_type: 'data',
  }))
  return [
    ...data,
    {
      label: G8_TOTAL_LABEL,
      end_balance: data.reduce((s, r) => s + num(r.end_balance), 0),
      [priorKey]: data.reduce((s, r) => s + num(r[priorKey]), 0),
      is_total: true,
      row_type: 'total',
    },
  ]
}

function detailBlank(r: G8DetailSyncRow): boolean {
  return (
    !String(r.label ?? '').trim()
    && num(r.ociPeriod) === 0
    && num(r.ociCumulative) === 0
    && num(r.dividend) === 0
    && num(r.transferAmount) === 0
    && !String(r.transferReason ?? '').trim()
  )
}

export function buildG8DetailRows(
  variant: G8DisclosureVariant,
  rows: readonly G8DetailSyncRow[],
): Record<string, unknown>[] {
  const reasonKey = variant === 'listed' ? 'derecognition_reason' : 'oci_to_re_reason'
  const transferKey = variant === 'listed' ? 'derecognition_to_re' : 'oci_to_re'
  const data = rows.filter((r) => !detailBlank(r)).map((r) => ({
    label: String(r.label ?? '').trim(),
    oci_current: num(r.ociPeriod),
    oci_cumulative: num(r.ociCumulative),
    dividend_income: num(r.dividend),
    [transferKey]: num(r.transferAmount),
    [reasonKey]: String(r.transferReason ?? '').trim(),
    row_type: 'data',
  }))
  // 上市源模板该表无合计行（附注模版 md 仅 3 个空行）；国企有
  if (variant === 'listed') return data
  return [
    ...data,
    {
      label: G8_TOTAL_LABEL,
      oci_current: data.reduce((s, r) => s + num(r.oci_current), 0),
      oci_cumulative: data.reduce((s, r) => s + num(r.oci_cumulative), 0),
      dividend_income: data.reduce((s, r) => s + num(r.dividend_income), 0),
      [transferKey]: data.reduce((s, r) => s + num(r[transferKey]), 0),
      [reasonKey]: '',
      is_total: true,
      row_type: 'total',
    },
  ]
}

export function buildG8SubTableData(
  variant: G8DisclosureVariant,
  snap: G8SyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [G8_MAIN_SUBTABLE[variant]]: buildG8BalanceRows(variant, snap.balanceRows),
    [G8_DETAIL_SUBTABLE]: buildG8DetailRows(variant, snap.detailRows),
  }
  const texts: Array<Record<string, string>> = []
  const designation = String(snap.designationText ?? '').trim()
  if (designation) texts.push({ section: `${variant}-designation-reason`, text: designation })
  const note = String(snap.noteText ?? '').trim()
  if (note) texts.push({ section: `${variant}-disclosure-note`, text: note })
  if (texts.length) out._note_texts = texts
  return out
}

/** @returns null=该变体不适用 / 缺 wpId */
export function buildG8SyncPayload(
  wpId: string,
  variant: G8DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
  snap: G8SyncSnapshot,
): G8SyncFromWorkpaperPayload | null {
  if (!wpId || !isG8DisclosureApplicable(variant, applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: G8_DISCLOSURE_SHEET_NAME[variant],
    section_id: G8_NOTE_SECTION[variant],
    current_standard: resolveG8CurrentStandard(variant, applicableStandards),
    sub_table_data: buildG8SubTableData(variant, snap),
    columns: g8ColumnsFor(variant),
  }
}
