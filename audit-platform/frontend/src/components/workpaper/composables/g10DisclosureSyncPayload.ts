/**
 * G10 披露 → disclosure_notes sync payload
 *
 * 子表名 / 列键逐字对齐 note_template §五、34 / §五、35 / §八、34（守卫 g10NoteSubtableContract.spec.ts）：
 * - 表名取 `G10_SUBTABLE` / `G10_DERIVATIVE_SUBTABLE` 常量，不按审计年度拼；旧载荷按年度拼的公允价值变动表名随
 *   `_removed_table_keys` 清掉
 * - 标签列头 / 合计行名用模板字面量（「项目」「合计」），与披露页的「项  目」「合  计」视觉写法解耦
 * - 主表带父行（「交易性金融负债」「指定为…金融负债」= 其下各行之和，与底稿、披露页同口径），合计 = 末级行之和
 * - 每张表显式 `flat`：源模板单级表头，不标时后端会把「本期增加 / 本期减少」反猜出凭空的「本期」父表头
 * （R8.4 批 9b-2，2026-10-24）
 */
import type { G10DiscListedStore, G10DiscSoeStore } from './g10DisclosureFromAdj'
import {
  G10_DERIVATIVE_SUBTABLE,
  G10_DISCLOSURE_SHEET_NAME,
  G10_NOTE_SECTION,
  G10_SUBTABLE,
  g10LegacyFvCreditTableNames,
  isG10DisclosureApplicable,
  resolveG10CurrentStandard,
  type G10DisclosureVariant,
} from './g10NoteSectionMap'
import {
  G10_DISCLOSURE_COL_LABELS,
  G10_LISTED_MOVEMENT_ROWS,
  G10_SOE_BALANCE_ROWS,
  g10ChildKeys,
} from './g10SchemaRows'
import { calcSubtotal } from './useG10FormulaEngine'
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export interface G10SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  /** 子表行 + `_note_texts` / `_removed_table_keys` 两个保留键（与 L1 / L4 载荷同形） */
  sub_table_data: Record<string, any>
  /** 列头元数据（disclosure-table-sync-convergence）：数据列 label 取自 G10_DISCLOSURE_COL_LABELS（源对齐） */
  columns?: Record<string, ColumnDef[]>
}

/** 模板 headers[0]（标签列头）与合计行名：附注字面量；披露页显示的是「项  目」「合  计」 */
export const G10_NOTE_ITEM_LABEL = '项目'
export const G10_NOTE_TOTAL_LABEL = '合计'

const FV_KEYS = ['fv_change_amount', 'credit_risk_current', 'credit_risk_cumulative'] as const

function labelColumn(): ColumnDef {
  return { key: 'label', label: G10_NOTE_ITEM_LABEL, is_label: true, flat: true }
}

function fvCreditColumns(fv: { fvChange: string; creditCurrent: string; creditCumulative: string }): ColumnDef[] {
  return defineColumns([
    labelColumn(),
    { key: 'fv_change_amount', label: fv.fvChange, format: 'amount' },
    { key: 'credit_risk_current', label: fv.creditCurrent, format: 'amount' },
    { key: 'credit_risk_cumulative', label: fv.creditCumulative, format: 'amount' },
  ])
}

// ── 各子表列头：键 = 模板列键（note_template §五、34 / §五、35 / §八、34），数据列 label 取自 G10_DISCLOSURE_COL_LABELS ──
export function buildG10ListedColumns(year: number | null): Record<string, ColumnDef[]> {
  const L = G10_DISCLOSURE_COL_LABELS.listed
  const S = G10_SUBTABLE.listed
  return {
    [S.trading]: defineColumns([
      labelColumn(),
      { key: 'begin_balance', label: L.movement.opening, format: 'amount' },
      { key: 'current_increase', label: L.movement.increase, format: 'amount' },
      { key: 'current_decrease', label: L.movement.decrease, format: 'amount' },
      { key: 'end_balance', label: L.movement.closing, format: 'amount' },
    ]),
    [S.designated]: defineColumns([
      labelColumn(),
      { key: 'begin_balance', label: L.designated.opening, format: 'amount' },
      { key: 'end_balance', label: L.designated.closing, format: 'amount' },
      { key: 'designation_reason', label: L.designated.reason, format: 'text' },
    ]),
    [S.fvCredit]: fvCreditColumns(L.fvCredit(year)),
  }
}

export function buildG10ListedDerivativeColumns(): Record<string, ColumnDef[]> {
  const D = G10_DISCLOSURE_COL_LABELS.listed.derivative
  return {
    [G10_DERIVATIVE_SUBTABLE.listed]: defineColumns([
      labelColumn(),
      { key: 'end_balance', label: D.current, format: 'amount' },
      { key: 'prior_balance', label: D.prior, format: 'amount' },
    ]),
  }
}

export function buildG10SoeColumns(year: number | null): Record<string, ColumnDef[]> {
  const B = G10_DISCLOSURE_COL_LABELS.soe.balance
  const S = G10_SUBTABLE.soe
  return {
    [S.trading]: defineColumns([
      labelColumn(),
      { key: 'end_fv', label: B.current, format: 'amount' },
      { key: 'begin_fv', label: B.prior, format: 'amount' },
    ]),
    [S.fvCredit]: fvCreditColumns(G10_DISCLOSURE_COL_LABELS.soe.fvCredit(year)),
  }
}

export interface G10ListedSyncSnapshot {
  store: G10DiscListedStore
  auditNote: string
  auditYear: number | null
}

export interface G10SoeSyncSnapshot {
  store: G10DiscSoeStore
  auditNote: string
  auditYear: number | null
}

type Row = Record<string, unknown>

/** 合计行：金额键 = 给定行之和（只传末级行，父行不重复计）；文字键留空 */
function totalRow(rows: readonly Row[], amountKeys: readonly string[], textKeys: readonly string[] = []): Row {
  const out: Row = { label: G10_NOTE_TOTAL_LABEL }
  for (const k of amountKeys) out[k] = calcSubtotal(rows.map((r) => Number(r[k]) || 0))
  for (const k of textKeys) out[k] = ''
  return { ...out, is_total: true, row_type: 'total' }
}

function hasDerivativeListedData(store: G10DiscListedStore): boolean {
  const mv = store.movement.mv_derivative
  const fromMovement = Math.abs(mv?.closingAmount ?? 0) > 0.005
    || Math.abs(mv?.openingAmount ?? 0) > 0.005
  const fromRows = store.derivativeRows.some(
    (r) => Math.abs(r.currentAmount) > 0.005 || Math.abs(r.priorAmount) > 0.005,
  )
  return fromMovement || fromRows || Boolean(store.derivativeNote?.trim())
}

const MOVEMENT_KEYS = ['begin_balance', 'current_increase', 'current_decrease', 'end_balance'] as const
const ZERO_MOVEMENT = { openingAmount: 0, increaseAmount: 0, decreaseAmount: 0, closingAmount: 0 }

type FvCreditStore = Record<string, {
  label?: string
  fvChangeAmount: number
  creditRiskCurrent: number
  creditRiskCumulative: number
}>

function fvCreditRows(src: FvCreditStore): Row[] {
  return Object.entries(src).map(([rowKey, row]) => ({
    label: row.label?.trim() || '（未命名）',
    row_key: rowKey,
    fv_change_amount: row.fvChangeAmount,
    credit_risk_current: row.creditRiskCurrent,
    credit_risk_cumulative: row.creditRiskCumulative,
    row_type: 'data',
  }))
}

/** 只在有旧名可清时才带 `_removed_table_keys`（与 L4 载荷同） */
function withRemoved(data: Record<string, any>, removed: readonly string[]): Record<string, any> {
  const pushed = new Set(Object.keys(data))
  const keys = removed.filter((name) => !pushed.has(name))
  return keys.length ? { ...data, _removed_table_keys: keys } : data
}

export function buildG10ListedSubTableData(snap: G10ListedSyncSnapshot): Record<string, any> {
  const { store, auditNote, auditYear } = snap
  const S = G10_SUBTABLE.listed
  const pairOf = (key: string) => store.movement[key] ?? ZERO_MOVEMENT
  const movement: Row[] = G10_LISTED_MOVEMENT_ROWS.map((def) => {
    const parts = def.isParent ? g10ChildKeys(G10_LISTED_MOVEMENT_ROWS, def.rowKey).map(pairOf) : [pairOf(def.rowKey)]
    const value = (f: keyof typeof ZERO_MOVEMENT) => (def.isParent ? calcSubtotal(parts.map((p) => p[f])) : parts[0][f])
    return {
      label: def.label.trim(),
      row_key: def.rowKey,
      begin_balance: value('openingAmount'),
      current_increase: value('increaseAmount'),
      current_decrease: value('decreaseAmount'),
      end_balance: value('closingAmount'),
      row_type: 'data',
    }
  })
  const leaves = movement.filter((_row, i) => !G10_LISTED_MOVEMENT_ROWS[i].isParent)

  const designated: Row[] = Object.entries(store.designatedDetail).map(([rowKey, row]) => ({
    label: row.label?.trim() || '（未命名）',
    row_key: rowKey,
    begin_balance: row.openingAmount,
    end_balance: row.closingAmount,
    designation_reason: row.designationReason || '',
    row_type: 'data',
  }))
  const fvCredit = fvCreditRows(store.fvCreditRisk)

  return withRemoved({
    [S.trading]: [...movement, totalRow(leaves, MOVEMENT_KEYS)],
    [S.designated]: [...designated, totalRow(designated, ['begin_balance', 'end_balance'], ['designation_reason'])],
    [S.fvCredit]: [...fvCredit, totalRow(fvCredit, FV_KEYS)],
    _note_texts: [
      { section: 'listed-derivative-note', text: store.derivativeNote },
      { section: 'listed-maturity-diff', text: store.maturityDiffNote },
      { section: 'listed-audit-note', text: auditNote },
    ],
  }, g10LegacyFvCreditTableNames(S.fvCredit, auditYear))
}

export function buildG10ListedDerivativeSubTableData(snap: G10ListedSyncSnapshot): Record<string, any> {
  const { store } = snap
  const rows: Row[] = store.derivativeRows.map((r) => ({
    label: r.label?.trim() || '（未命名）',
    row_key: r.rowKey,
    end_balance: r.currentAmount,
    prior_balance: r.priorAmount,
    row_type: 'data',
  }))
  return {
    [G10_DERIVATIVE_SUBTABLE.listed]: [...rows, totalRow(rows, ['end_balance', 'prior_balance'])],
    _note_texts: [{ section: 'listed-derivative-note', text: store.derivativeNote }],
  }
}

export function buildG10SoeSubTableData(snap: G10SoeSyncSnapshot): Record<string, any> {
  const { store, auditNote, auditYear } = snap
  const S = G10_SUBTABLE.soe
  const pairOf = (key: string) => store.balance[key] ?? { currentAmount: 0, priorAmount: 0 }
  const balance: Row[] = G10_SOE_BALANCE_ROWS.map((def) => {
    const parts = def.isParent ? g10ChildKeys(G10_SOE_BALANCE_ROWS, def.rowKey).map(pairOf) : [pairOf(def.rowKey)]
    const value = (f: 'currentAmount' | 'priorAmount') => (def.isParent ? calcSubtotal(parts.map((p) => p[f])) : parts[0][f])
    return {
      label: def.label.trim(),
      row_key: def.rowKey,
      end_fv: value('currentAmount'),
      begin_fv: value('priorAmount'),
      row_type: 'data',
    }
  })
  const leaves = balance.filter((_row, i) => !G10_SOE_BALANCE_ROWS[i].isParent)
  const fvCredit = fvCreditRows(store.fvCreditRisk)

  return withRemoved({
    [S.trading]: [...balance, totalRow(leaves, ['end_fv', 'begin_fv'])],
    [S.fvCredit]: [...fvCredit, totalRow(fvCredit, FV_KEYS)],
    _note_texts: [
      { section: 'soe-maturity-diff', text: store.maturityDiffNote },
      { section: 'soe-audit-note', text: auditNote },
    ],
  }, g10LegacyFvCreditTableNames(S.fvCredit, auditYear))
}

export function buildG10ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: G10ListedSyncSnapshot,
): G10SyncFromWorkpaperPayload[] {
  const variant: G10DisclosureVariant = 'listed'
  if (!isG10DisclosureApplicable(variant, applicableStandards)) return []
  const standard = resolveG10CurrentStandard(variant, applicableStandards)
  const sheet = G10_DISCLOSURE_SHEET_NAME.listed
  const payloads: G10SyncFromWorkpaperPayload[] = [
    {
      wp_id: wpId,
      sheet_name: sheet,
      section_id: G10_NOTE_SECTION.listed.trading,
      current_standard: standard,
      sub_table_data: buildG10ListedSubTableData(snap),
      columns: buildG10ListedColumns(snap.auditYear),
    },
  ]
  if (hasDerivativeListedData(snap.store)) {
    payloads.push({
      wp_id: wpId,
      sheet_name: sheet,
      section_id: G10_NOTE_SECTION.listed.derivative,
      current_standard: standard,
      sub_table_data: buildG10ListedDerivativeSubTableData(snap),
      columns: buildG10ListedDerivativeColumns(),
    })
  }
  return payloads
}

export function buildG10SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: G10SoeSyncSnapshot,
): G10SyncFromWorkpaperPayload[] {
  const variant: G10DisclosureVariant = 'soe'
  if (!isG10DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: G10_DISCLOSURE_SHEET_NAME.soe,
      section_id: G10_NOTE_SECTION.soe.trading,
      current_standard: resolveG10CurrentStandard(variant, applicableStandards),
      sub_table_data: buildG10SoeSubTableData(snap),
      columns: buildG10SoeColumns(snap.auditYear),
    },
  ]
}

// ── 披露 Tab 的同步步骤（由 `G10TabDisclosureBase` 原样抽出，Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1）──

/** 披露 Tab 审计说明的条目号（Tab 挂载时读一次进 `auditNote`，同步时写进 `{variant}-audit-note` 说明段） */
export function g10DisclosureAuditNoteKey(variant: G10DisclosureVariant): string {
  return `G10-disclosure-${variant}-audit-note`
}

/** 披露 Tab 挂载时的审计说明 */
export function readG10DisclosureAuditNote(
  responses: ReadonlyMap<string, { remark?: string | null }>,
  variant: G10DisclosureVariant,
): string {
  return responses.get(g10DisclosureAuditNoteKey(variant))?.remark ?? ''
}

/**
 * 披露 Tab「同步到附注」的载荷：`useG10Disclosure.getSyncSnapshot(审计说明)` → 本版本 builder（上市 五、34，有衍生负债数据时
 * 另加 五、35；国企 八、34）。口径不适用回空数组（Tab 据此提示）。
 */
export function buildG10TabSyncPayloads(
  wpId: string,
  variant: G10DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
  dis: { getSyncSnapshot: (auditNote?: string) => G10ListedSyncSnapshot | G10SoeSyncSnapshot },
  auditNote: string,
): G10SyncFromWorkpaperPayload[] {
  const standards = applicableStandards ?? []
  const snap = dis.getSyncSnapshot(auditNote)
  return variant === 'listed'
    ? buildG10ListedSyncPayloads(wpId, standards, snap as G10ListedSyncSnapshot)
    : buildG10SoeSyncPayloads(wpId, standards, snap as G10SoeSyncSnapshot)
}
