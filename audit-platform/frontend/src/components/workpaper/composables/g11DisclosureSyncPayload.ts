/**

 * G11 披露 → disclosure_notes sync payload

 * 子表名对齐 note_template §五、69（上市）/ §八、70（国企）

 */

import { parseNum, calcSubtotal } from './useG11FormulaEngine'

import {

  G11_DISCLOSURE_TOTAL_LABEL,

  G11_LISTED_TRADING_DISPOSE_ROWS,

  G11_SOE_REPATRIATION_PLACEHOLDER,

  G11_TRADING_DISPOSE_SUFFIXES,

  isG11DisclosureLeaf,

} from './g11SchemaRows'

import {

  sumG11DisclosureLeafCurrent,

  sumG11DisclosureLeafPrior,

  sumG11TradingDisposeCurrent,

  type G11DiscStoreV2,

  type G11TradingDisposeMap,

} from './g11DisclosureFromAdj'

import {

  G11_DISCLOSURE_SHEET_NAME,

  G11_NOTE_SECTION,

  isG11DisclosureApplicable,

  resolveG11CurrentStandard,

  type G11DisclosureVariant,

} from './g11NoteSectionMap'



import type { ColumnDef } from './disclosureColumnDefs'

export interface G11SyncFromWorkpaperPayload {

  wp_id: string

  sheet_name: string

  section_id: string

  current_standard: string

  sub_table_data: Record<string, Record<string, unknown>[]>

  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 G11_DISCLOSURE_COL_LABELS/组件 */

  columns?: Record<string, ColumnDef[]>

}

// 投资收益列头：项目/本期发生额/上期发生额/备注（对齐 G11_DISCLOSURE_COL_LABELS + 组件）

const G11_MAIN_COLUMNS: ColumnDef[] = [

  { key: 'label', label: '项目', is_label: true },

  { key: 'current_amount', label: '本期发生额', format: 'amount' },

  { key: 'prior_amount', label: '上期发生额', format: 'amount' },

  { key: 'remark', label: '备注' },

]

const G11_TRADING_COLUMNS: ColumnDef[] = [

  { key: 'label', label: '项目', is_label: true },

  { key: 'current_amount', label: '本期发生额', format: 'amount' },

  { key: 'prior_amount', label: '上期发生额', format: 'amount' },

]



export interface G11SyncSnapshot {

  store: G11DiscStoreV2

  noteText: string

  auditNote: string

  auditConclusion: string

}



/** 主表子表键 — 对齐 note_template tables[].name */

export const G11_MAIN_SUBTABLE = '投资收益'

/** 上市处置交易性明细 — 对齐 note_template 第二表「项  目」 */

export const G11_LISTED_TRADING_SUBTABLE = '项  目'



function hasTradingDisposeData(map: G11TradingDisposeMap | undefined): boolean {

  if (!map) return false

  return G11_TRADING_DISPOSE_SUFFIXES.some((key) => {

    const pair = map[key]

    return Math.abs(parseNum(pair?.currentAmount)) > 0.005

      || Math.abs(parseNum(pair?.priorAmount)) > 0.005

  })

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



export function buildG11MainSubTableRows(store: G11DiscStoreV2): Record<string, unknown>[] {

  const dataRows = store.rows

    .filter((r) => isG11DisclosureLeaf(r.rowKey))

    .map((r) => mapAmountRow(

      r.label,

      r.rowKey,

      parseNum(r.currentAmount),

      parseNum(r.priorAmount),

      r.remark ? { remark: r.remark } : undefined,

    ))

  const total = {

    label: G11_DISCLOSURE_TOTAL_LABEL.trim(),

    current_amount: sumG11DisclosureLeafCurrent(store.rows),

    prior_amount: sumG11DisclosureLeafPrior(store.rows),

    is_total: true,

    row_type: 'total',

  }

  return [...dataRows, total]

}



export function buildG11ListedTradingSubTableRows(

  map: G11TradingDisposeMap,

): Record<string, unknown>[] {

  const dataRows = G11_LISTED_TRADING_DISPOSE_ROWS.map((def) => {

    const pair = map[def.rowKey as keyof typeof map]

    return mapAmountRow(

      def.label,

      def.rowKey,

      parseNum(pair?.currentAmount),

      parseNum(pair?.priorAmount),

    )

  })

  const currentTotal = sumG11TradingDisposeCurrent(map)

  const priorTotal = calcSubtotal(

    G11_TRADING_DISPOSE_SUFFIXES.map((k) => parseNum(map[k]?.priorAmount)),

  )

  const total = {

    label: G11_DISCLOSURE_TOTAL_LABEL.trim(),

    current_amount: currentTotal,

    prior_amount: priorTotal,

    is_total: true,

    row_type: 'total',

  }

  return [...dataRows, total]

}



function buildNoteTexts(snap: G11SyncSnapshot, variant: G11DisclosureVariant): Array<Record<string, string>> {

  const texts: Array<Record<string, string>> = []

  if (snap.noteText.trim()) {

    texts.push({ section: 'disclosure-note', text: snap.noteText.trim() })

  }

  if (snap.auditNote.trim()) {

    texts.push({ section: `${variant}-audit-note`, text: snap.auditNote.trim() })

  }

  if (snap.auditConclusion.trim()) {

    texts.push({ section: `${variant}-audit-conclusion`, text: snap.auditConclusion.trim() })

  }

  if (variant === 'soe') {

    const rep = (snap.store.repatriationNote ?? '').trim()

    if (rep && rep !== G11_SOE_REPATRIATION_PLACEHOLDER) {

      texts.push({ section: 'repatriation-note', text: rep })

    }

  }

  return texts

}



export function buildG11ListedSubTableData(

  snap: G11SyncSnapshot,

): Record<string, Record<string, unknown>[]> {

  const result: Record<string, Record<string, unknown>[]> = {

    [G11_MAIN_SUBTABLE]: buildG11MainSubTableRows(snap.store),

  }

  if (hasTradingDisposeData(snap.store.tradingDispose)) {

    result[G11_LISTED_TRADING_SUBTABLE] = buildG11ListedTradingSubTableRows(

      snap.store.tradingDispose!,

    )

  }

  const noteTexts = buildNoteTexts(snap, 'listed')

  if (noteTexts.length) result._note_texts = noteTexts

  return result

}



export function buildG11SoeSubTableData(

  snap: G11SyncSnapshot,

): Record<string, Record<string, unknown>[]> {

  const result: Record<string, Record<string, unknown>[]> = {

    [G11_MAIN_SUBTABLE]: buildG11MainSubTableRows(snap.store),

  }

  const noteTexts = buildNoteTexts(snap, 'soe')

  if (noteTexts.length) result._note_texts = noteTexts

  return result

}



export function buildG11ListedSyncPayloads(

  wpId: string,

  applicableStandards: readonly string[] | null | undefined,

  snap: G11SyncSnapshot,

): G11SyncFromWorkpaperPayload[] {

  const variant: G11DisclosureVariant = 'listed'

  if (!isG11DisclosureApplicable(variant, applicableStandards)) return []

  return [{

    wp_id: wpId,

    sheet_name: G11_DISCLOSURE_SHEET_NAME.listed,

    section_id: G11_NOTE_SECTION.listed,

    current_standard: resolveG11CurrentStandard(variant, applicableStandards),

    sub_table_data: buildG11ListedSubTableData(snap),

    columns: { [G11_MAIN_SUBTABLE]: G11_MAIN_COLUMNS, [G11_LISTED_TRADING_SUBTABLE]: G11_TRADING_COLUMNS },

  }]

}



export function buildG11SoeSyncPayloads(

  wpId: string,

  applicableStandards: readonly string[] | null | undefined,

  snap: G11SyncSnapshot,

): G11SyncFromWorkpaperPayload[] {

  const variant: G11DisclosureVariant = 'soe'

  if (!isG11DisclosureApplicable(variant, applicableStandards)) return []

  return [{

    wp_id: wpId,

    sheet_name: G11_DISCLOSURE_SHEET_NAME.soe,

    section_id: G11_NOTE_SECTION.soe,

    current_standard: resolveG11CurrentStandard(variant, applicableStandards),

    sub_table_data: buildG11SoeSubTableData(snap),

    columns: { [G11_MAIN_SUBTABLE]: G11_MAIN_COLUMNS },

  }]

}



export function buildG11SyncPayloads(

  wpId: string,

  variant: G11DisclosureVariant,

  applicableStandards: readonly string[] | null | undefined,

  snap: G11SyncSnapshot,

): G11SyncFromWorkpaperPayload[] {

  return variant === 'listed'

    ? buildG11ListedSyncPayloads(wpId, applicableStandards, snap)

    : buildG11SoeSyncPayloads(wpId, applicableStandards, snap)

}


