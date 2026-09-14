/**
 * H1 披露 → disclosure_notes sync payload
 * - 国企：note_template_soe §八、22
 * - 上市：note_template_listed / 源 xlsx「15、固定资产」→ 五、15
 */
import {
  H1_DISCLOSURE_SHEET_NAME,
  H1_LISTED_SUBTABLE,
  H1_NOTE_SECTION,
  H1_SOE_SUBTABLE,
  isH1DisclosureApplicable,
  resolveH1CurrentStandard,
  resolveH1NoteSectionTarget,
  type H1DisclosureVariant,
} from './h1NoteSectionMap'
import {
  H1_SOE_CATEGORIES,
  H1_SOE_LAYER_META,
  flattenSoeMovement,
  idleSubtotal,
  layerTotal,
  type H1SoeClearingRow,
  type H1SoeDisclosureState,
  type H1SoeIdleRow,
  type H1SoeTitleRow,
} from './h1SoeDisclosureModel'
import {
  cellValue,
  formatGovSubsidyLine,
  idleBookValue,
  num,
  summaryTotal,
  sumClearing,
  sumIdle,
  sumLease,
  totalCellValue,
  type ClearingRow,
  type GovSubsidyState,
  type H1ListedCategory,
  type IdleRow,
  type LeaseOutRow,
  type MovementCellMap,
  type MovementRowDef,
  type SummaryRow,
  type TitleCertRow,
  H1_LISTED_MOVEMENT_ROWS,
} from './h1ListedDisclosureModel'

import type { ColumnDef } from './disclosureColumnDefs'

export interface H1SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 H1TabDisclosure el-table-column */
  columns?: Record<string, ColumnDef[]>
}

/**
 * SOE 子表列头（取自 H1TabDisclosureSoe，逐字对齐 note_template_soe §八、22 headers）。
 * 标签列 label 必须等于附注 `headers[0]`，否则附注 TAB 首列名漂移。
 */
export const H1_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  [H1_SOE_SUBTABLE.summary]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_carrying', label: '期末账面价值', format: 'amount' },
    { key: 'begin_carrying', label: '期初账面价值', format: 'amount' },
  ],
  [H1_SOE_SUBTABLE.movement]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'begin', label: '期初余额', format: 'amount' },
    { key: 'increase', label: '本期增加', format: 'amount' },
    { key: 'decrease', label: '本期减少', format: 'amount' },
    { key: 'end', label: '期末余额', format: 'amount' },
  ],
  [H1_SOE_SUBTABLE.idle]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'original_cost', label: '账面原值', format: 'amount' },
    { key: 'accum_dep', label: '累计折旧', format: 'amount' },
    { key: 'impairment', label: '减值准备', format: 'amount' },
    { key: 'carrying', label: '账面价值', format: 'amount' },
    { key: 'remark', label: '备注' },
  ],
  [H1_SOE_SUBTABLE.titleCert]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'carrying', label: '账面价值', format: 'amount' },
    { key: 'reason', label: '未办妥产权证书原因' },
  ],
  [H1_SOE_SUBTABLE.clearing]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_carrying', label: '期末账面价值', format: 'amount' },
    { key: 'begin_carrying', label: '期初账面价值', format: 'amount' },
    { key: 'reason', label: '转入清理的原因' },
  ],
}

/** 上市子表列头：变动表随类别动态，其余静态源对齐（取自 H1TabDisclosureListed） */
export function buildH1ListedColumns(snap: H1ListedSyncSnapshot): Record<string, ColumnDef[]> {
  const cats = snap.categories || []
  const movement: ColumnDef[] = [
    { key: 'label', label: '项目', is_label: true },
    ...cats.map((c) => ({ key: c.label, label: c.label, format: 'amount' as const })),
    { key: '合计', label: '合计', format: 'amount' },
  ]
  return {
    [H1_LISTED_SUBTABLE.summary]: [
      { key: 'label', label: '项目', is_label: true },
      { key: 'end_balance', label: '期末余额', format: 'amount' },
      { key: 'prior_balance', label: '上年年末余额', format: 'amount' },
    ],
    [H1_LISTED_SUBTABLE.movement]: movement,
    [H1_LISTED_SUBTABLE.idle]: [
      { key: 'label', label: '项目', is_label: true },
      { key: 'cost', label: '账面原值', format: 'amount' },
      { key: 'dep', label: '累计折旧', format: 'amount' },
      { key: 'impairment', label: '减值准备', format: 'amount' },
      { key: 'book_value', label: '账面价值', format: 'amount' },
      { key: 'remark', label: '备注' },
    ],
    [H1_LISTED_SUBTABLE.leaseOut]: [
      { key: 'label', label: '项目', is_label: true },
      { key: 'book_value', label: '账面价值', format: 'amount' },
    ],
    [H1_LISTED_SUBTABLE.titleCert]: [
      { key: 'label', label: '项目', is_label: true },
      { key: 'book_value', label: '账面价值', format: 'amount' },
      { key: 'reason', label: '未办妥产权证书原因' },
    ],
    [H1_LISTED_SUBTABLE.clearing]: [
      { key: 'label', label: '项目', is_label: true },
      { key: 'end_balance', label: '期末余额', format: 'amount' },
      { key: 'prior_balance', label: '上年年末余额', format: 'amount' },
      { key: 'reason', label: '转入清理的原因' },
    ],
  }
}

export function buildH1SoeSubTableData(state: H1SoeDisclosureState): Record<string, Record<string, unknown>[]> {
  const carrying = state.layers.find((l) => l.layer === 'carrying')
  const fa = carrying ? layerTotal(carrying) : { begin: 0, increase: 0, decrease: 0, end: 0 }
  const clearingEnd = Number(state.summary.clearingEnd) || 0
  const clearingBegin = Number(state.summary.clearingBegin) || 0

  const summaryRows: Record<string, unknown>[] = [
    { label: '固定资产', end_carrying: fa.end, begin_carrying: fa.begin },
    { label: '固定资产清理', end_carrying: clearingEnd, begin_carrying: clearingBegin },
    {
      label: '合计',
      end_carrying: fa.end + clearingEnd,
      begin_carrying: fa.begin + clearingBegin,
      is_total: true,
    },
  ]

  const movementRows: Record<string, unknown>[] = []
  for (const flat of flattenSoeMovement(state.layers)) {
    const meta = H1_SOE_LAYER_META[flat.layer]
    movementRows.push({
      label: flat.label,
      begin: flat.begin,
      increase: meta.movementNa || flat.allNa ? null : flat.increase,
      decrease: meta.movementNa || flat.allNa ? null : flat.decrease,
      end: flat.end,
      is_total: flat.kind === 'total',
      layer: flat.layer,
    })
  }

  const idleRows = state.idleRows.map((r: H1SoeIdleRow) => ({
    label: r.name,
    original_cost: r.originalCost,
    accum_dep: r.accumDep,
    impairment: r.impairment,
    carrying: r.carrying,
    remark: r.remark,
  }))
  const idleTot = idleSubtotal(state.idleRows)
  idleRows.push({
    label: idleTot.name,
    original_cost: idleTot.originalCost,
    accum_dep: idleTot.accumDep,
    impairment: idleTot.impairment,
    carrying: idleTot.carrying,
    remark: '',
    is_total: true,
  } as Record<string, unknown>)

  const titleRows = state.titleRows.map((r: H1SoeTitleRow) => ({
    label: r.name,
    carrying: r.carrying,
    reason: r.reason,
  }))
  titleRows.push({
    label: '合计',
    carrying: state.titleRows.reduce((s, r) => s + (Number(r.carrying) || 0), 0),
    reason: '',
    is_total: true,
  } as Record<string, unknown>)

  const clearingRows = state.clearingRows.map((r: H1SoeClearingRow) => ({
    label: r.name,
    end_carrying: r.endCarrying,
    begin_carrying: r.beginCarrying,
    reason: r.reason,
  }))
  clearingRows.push({
    label: '合计',
    end_carrying: state.clearingRows.reduce((s, r) => s + (Number(r.endCarrying) || 0), 0),
    begin_carrying: state.clearingRows.reduce((s, r) => s + (Number(r.beginCarrying) || 0), 0),
    reason: '',
    is_total: true,
  } as Record<string, unknown>)

  return {
    [H1_SOE_SUBTABLE.summary]: summaryRows,
    [H1_SOE_SUBTABLE.movement]: movementRows,
    [H1_SOE_SUBTABLE.idle]: idleRows,
    [H1_SOE_SUBTABLE.titleCert]: titleRows,
    [H1_SOE_SUBTABLE.clearing]: clearingRows,
    _note_texts: [
      {
        section: 'soe-clearing-progress',
        text: state.clearingNote || '',
      },
      {
        section: 'soe-categories',
        text: H1_SOE_CATEGORIES.map((c) => c.shortLabel).join('、'),
      },
    ],
  }
}

/** 可选覆盖项：current_standard 以项目 template_type + report_scope 为权威 */
export interface H1SyncOptions {
  currentStandard?: string
}

export function buildH1SoeSyncPayload(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H1SoeDisclosureState,
  opts?: H1SyncOptions,
): H1SyncFromWorkpaperPayload | null {
  const variant: H1DisclosureVariant = 'soe'
  const target = resolveH1NoteSectionTarget(variant, applicableStandards)
  if (!target) return null
  if (target.sectionId !== H1_NOTE_SECTION.soe) return null
  return {
    wp_id: wpId,
    sheet_name: H1_DISCLOSURE_SHEET_NAME.soe,
    section_id: target.sectionId,
    current_standard: opts?.currentStandard || target.currentStandard,
    sub_table_data: buildH1SoeSubTableData(state),
    columns: H1_SOE_COLUMNS,
  }
}

// ─── Listed（上市公司）───────────────────────────────────────────────────────

export interface H1ListedSyncSnapshot {
  summary: SummaryRow[]
  categories: H1ListedCategory[]
  movement: MovementCellMap
  idle: IdleRow[]
  leaseOut: LeaseOutRow[]
  titleCert: TitleCertRow[]
  clearing: ClearingRow[]
  govSubsidy: GovSubsidyState
  noteImpairment: string
  noteMortgage: string
  noteSale: string
  noteClearing: string
}

function amt(v: number): number {
  return Math.round(num(v) * 100) / 100
}

function buildListedSummarySubTable(summary: SummaryRow[]): Record<string, unknown>[] {
  const total = summaryTotal(summary)
  return [
    ...summary.map((r) => ({
      label: r.label,
      end_balance: amt(r.endBalance),
      prior_balance: amt(r.priorBalance),
      row_type: 'data' as const,
    })),
    {
      label: '合计',
      end_balance: amt(total.endBalance),
      prior_balance: amt(total.priorBalance),
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

function buildListedMovementSubTable(
  categories: H1ListedCategory[],
  movement: MovementCellMap,
  defs: readonly MovementRowDef[] = H1_LISTED_MOVEMENT_ROWS,
): Record<string, unknown>[] {
  return defs
    .filter((d) => d.kind !== 'section')
    .map((d) => {
      const row: Record<string, unknown> = {
        label: d.label.trim(),
        row_key: d.key,
        row_type: d.kind === 'calc' || d.kind === 'book' || d.kind === 'subtotal' ? 'calc' : 'data',
        合计: amt(totalCellValue(movement, d, categories)),
      }
      for (const c of categories) {
        row[c.label] = amt(cellValue(movement, d, c.key, defs))
      }
      return row
    })
}

function buildListedIdleSubTable(rows: IdleRow[]): Record<string, unknown>[] {
  const data = rows
    .filter((r) => r.name.trim() && (idleBookValue(r) !== 0 || num(r.cost) !== 0))
    .map((r) => ({
      label: r.name,
      cost: amt(r.cost),
      dep: amt(r.dep),
      impairment: amt(r.impairment),
      book_value: amt(idleBookValue(r)),
      remark: r.remark || '',
      row_type: 'data' as const,
    }))
  const t = sumIdle(rows)
  return [
    ...data,
    {
      label: '合计',
      cost: amt(t.cost),
      dep: amt(t.dep),
      impairment: amt(t.impairment),
      book_value: amt(t.bookValue),
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

function buildListedLeaseSubTable(rows: LeaseOutRow[]): Record<string, unknown>[] {
  const data = rows
    .filter((r) => r.name.trim() && num(r.bookValue) !== 0)
    .map((r) => ({
      label: r.name,
      book_value: amt(r.bookValue),
      row_type: 'data' as const,
    }))
  return [
    ...data,
    {
      label: '合计',
      book_value: amt(sumLease(rows)),
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

function buildListedTitleCertSubTable(rows: TitleCertRow[]): Record<string, unknown>[] {
  return rows
    .filter((r) => r.name.trim() || num(r.bookValue) !== 0 || r.reason.trim())
    .map((r) => ({
      label: r.name,
      book_value: amt(r.bookValue),
      reason: r.reason,
      row_type: 'data' as const,
    }))
}

function buildListedClearingSubTable(rows: ClearingRow[]): Record<string, unknown>[] {
  const data = rows
    .filter((r) => r.name.trim() || num(r.endBalance) !== 0 || num(r.priorBalance) !== 0)
    .map((r) => ({
      label: r.name,
      end_balance: amt(r.endBalance),
      prior_balance: amt(r.priorBalance),
      reason: r.reason,
      row_type: 'data' as const,
    }))
  const t = sumClearing(rows)
  return [
    ...data,
    {
      label: '合计',
      end_balance: amt(t.endBalance),
      prior_balance: amt(t.priorBalance),
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

function buildListedNoteTexts(snap: H1ListedSyncSnapshot): Array<Record<string, string>> {
  const texts: Array<Record<string, string>> = []
  if (snap.noteImpairment.trim()) {
    texts.push({ section: 'impairment-test', text: snap.noteImpairment.trim() })
  }
  if (snap.noteMortgage.trim()) {
    texts.push({ section: 'mortgage-pledge', text: snap.noteMortgage.trim() })
  }
  if (snap.noteSale.trim()) {
    texts.push({ section: 'above-book-sale', text: snap.noteSale.trim() })
  }
  texts.push({
    section: 'gov-subsidy',
    text: formatGovSubsidyLine(snap.govSubsidy.amount, snap.govSubsidy.text),
  })
  if (snap.noteClearing.trim()) {
    texts.push({ section: 'clearing-over-1y', text: snap.noteClearing.trim() })
  }
  return texts
}

export function buildH1ListedSubTableData(
  snap: H1ListedSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const result: Record<string, Record<string, unknown>[]> = {
    [H1_LISTED_SUBTABLE.summary]: buildListedSummarySubTable(snap.summary),
    [H1_LISTED_SUBTABLE.movement]: buildListedMovementSubTable(snap.categories, snap.movement),
    [H1_LISTED_SUBTABLE.idle]: buildListedIdleSubTable(snap.idle),
    [H1_LISTED_SUBTABLE.leaseOut]: buildListedLeaseSubTable(snap.leaseOut),
    [H1_LISTED_SUBTABLE.titleCert]: buildListedTitleCertSubTable(snap.titleCert),
    [H1_LISTED_SUBTABLE.clearing]: buildListedClearingSubTable(snap.clearing),
  }
  const noteTexts = buildListedNoteTexts(snap)
  if (noteTexts.length) result._note_texts = noteTexts
  return result
}

export function buildH1SyncPayload(
  variant: H1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  subTableData: Record<string, Record<string, unknown>[]>,
  opts?: H1SyncOptions,
): H1SyncFromWorkpaperPayload | null {
  if (!isH1DisclosureApplicable(variant, applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: H1_DISCLOSURE_SHEET_NAME[variant],
    section_id: H1_NOTE_SECTION[variant],
    current_standard: opts?.currentStandard || resolveH1CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
  }
}

export function buildH1ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: H1ListedSyncSnapshot,
  opts?: H1SyncOptions,
): H1SyncFromWorkpaperPayload[] {
  const payload = buildH1SyncPayload(
    'listed', wpId, applicableStandards, buildH1ListedSubTableData(snap), opts,
  )
  if (!payload) return []
  payload.columns = buildH1ListedColumns(snap)
  return [payload]
}
