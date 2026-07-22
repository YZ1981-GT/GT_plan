/**
 * G10 披露 → disclosure_notes sync payload
 * 子表名对齐 note_template §五、34 / §八、34（及衍生 §五、35 / §八、35）
 */
import type { G10DiscListedStore, G10DiscSoeStore } from './g10DisclosureFromAdj'
import {
  G10_DISCLOSURE_SHEET_NAME,
  G10_NOTE_SECTION,
  isG10DisclosureApplicable,
  resolveG10CurrentStandard,
  type G10DisclosureVariant,
} from './g10NoteSectionMap'
import {
  G10_DISCLOSURE_TOTAL_LABEL,
  G10_LISTED_MOVEMENT_ROWS,
  G10_SOE_BALANCE_ROWS,
} from './g10SchemaRows'
import { calcSubtotal } from './useG10FormulaEngine'

export interface G10SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
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

const LISTED_DESIGNATED_TABLE =
  '1、对于指定为以公允价值计量且其变动计入当期损益的金融负债，应单独列示期初余额、期末余额，并披露指定的理由和依据。'

function listedFvCreditTableName(year: number | null): string {
  const y = year ?? new Date().getFullYear()
  return `对于指定为以公允价值计量且其变动计入当期损益的金融负债，${y}年公允价值的变动情况如下表所示：`
}

function soeFvCreditTableName(year: number | null): string {
  const y = year ?? new Date().getFullYear()
  return `对于指定为以公允价值计量且其变动计入当期损益的金融负债，${y}年公允价值的变动情况如下表所示：`
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

export function buildG10ListedSubTableData(
  snap: G10ListedSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const { store, auditNote, auditYear } = snap
  const leafRows = G10_LISTED_MOVEMENT_ROWS.filter((r) => !r.isParent)
  const movementRows = leafRows.map((def) => {
    const pair = store.movement[def.rowKey] ?? {
      openingAmount: 0,
      increaseAmount: 0,
      decreaseAmount: 0,
      closingAmount: 0,
    }
    return {
      label: def.label.trim(),
      row_key: def.rowKey,
      opening_balance: pair.openingAmount,
      current_increase: pair.increaseAmount,
      current_decrease: pair.decreaseAmount,
      end_balance: pair.closingAmount,
      row_type: 'data',
    }
  })
  const total = {
    label: G10_DISCLOSURE_TOTAL_LABEL,
    opening_balance: calcSubtotal(movementRows.map((r) => Number(r.opening_balance) || 0)),
    current_increase: calcSubtotal(movementRows.map((r) => Number(r.current_increase) || 0)),
    current_decrease: calcSubtotal(movementRows.map((r) => Number(r.current_decrease) || 0)),
    end_balance: calcSubtotal(movementRows.map((r) => Number(r.end_balance) || 0)),
    is_total: true,
    row_type: 'total',
  }

  const designated = Object.entries(store.designatedDetail).map(([rowKey, row]) => ({
    label: row.label?.trim() || '（未命名）',
    row_key: rowKey,
    opening_balance: row.openingAmount,
    end_balance: row.closingAmount,
    designation_reason: row.designationReason || '',
    row_type: 'data',
  }))
  const designatedTotal = {
    label: G10_DISCLOSURE_TOTAL_LABEL,
    opening_balance: calcSubtotal(designated.map((r) => Number(r.opening_balance) || 0)),
    end_balance: calcSubtotal(designated.map((r) => Number(r.end_balance) || 0)),
    is_total: true,
    row_type: 'total',
  }

  const fvCredit = Object.entries(store.fvCreditRisk).map(([rowKey, row]) => ({
    label: row.label?.trim() || '（未命名）',
    row_key: rowKey,
    fv_change_amount: row.fvChangeAmount,
    credit_risk_current: row.creditRiskCurrent,
    credit_risk_cumulative: row.creditRiskCumulative,
    row_type: 'data',
  }))
  const fvTotal = {
    label: G10_DISCLOSURE_TOTAL_LABEL,
    fv_change_amount: calcSubtotal(fvCredit.map((r) => Number(r.fv_change_amount) || 0)),
    credit_risk_current: calcSubtotal(fvCredit.map((r) => Number(r.credit_risk_current) || 0)),
    credit_risk_cumulative: calcSubtotal(fvCredit.map((r) => Number(r.credit_risk_cumulative) || 0)),
    is_total: true,
    row_type: 'total',
  }

  return {
    交易性金融负债: [...movementRows, total],
    [LISTED_DESIGNATED_TABLE]: designated.length ? [...designated, designatedTotal] : [designatedTotal],
    [listedFvCreditTableName(auditYear)]: fvCredit.length ? [...fvCredit, fvTotal] : [fvTotal],
    _note_texts: [
      { section: 'listed-derivative-note', text: store.derivativeNote },
      { section: 'listed-maturity-diff', text: store.maturityDiffNote },
      { section: 'listed-audit-note', text: auditNote },
    ],
  }
}

export function buildG10ListedDerivativeSubTableData(
  snap: G10ListedSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const { store } = snap
  const rows = store.derivativeRows.map((r) => ({
    label: r.label?.trim() || '（未命名）',
    row_key: r.rowKey,
    end_balance: r.currentAmount,
    prior_balance: r.priorAmount,
    row_type: 'data',
  }))
  const total = {
    label: G10_DISCLOSURE_TOTAL_LABEL,
    end_balance: calcSubtotal(rows.map((r) => Number(r.end_balance) || 0)),
    prior_balance: calcSubtotal(rows.map((r) => Number(r.prior_balance) || 0)),
    is_total: true,
    row_type: 'total',
  }
  return {
    衍生金融负债: rows.length ? [...rows, total] : [total],
    _note_texts: [{ section: 'listed-derivative-note', text: store.derivativeNote }],
  }
}

export function buildG10SoeSubTableData(
  snap: G10SoeSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const { store, auditNote, auditYear } = snap
  const leafRows = G10_SOE_BALANCE_ROWS.filter((r) => !r.isParent)
  const balanceRows = leafRows.map((def) => {
    const pair = store.balance[def.rowKey] ?? { currentAmount: 0, priorAmount: 0 }
    return {
      label: def.label.trim(),
      row_key: def.rowKey,
      end_fair_value: pair.currentAmount,
      prior_fair_value: pair.priorAmount,
      row_type: 'data',
    }
  })
  const total = {
    label: G10_DISCLOSURE_TOTAL_LABEL,
    end_fair_value: calcSubtotal(balanceRows.map((r) => Number(r.end_fair_value) || 0)),
    prior_fair_value: calcSubtotal(balanceRows.map((r) => Number(r.prior_fair_value) || 0)),
    is_total: true,
    row_type: 'total',
  }

  const fvCredit = Object.entries(store.fvCreditRisk).map(([rowKey, row]) => ({
    label: row.label?.trim() || '（未命名）',
    row_key: rowKey,
    fv_change_amount: row.fvChangeAmount,
    credit_risk_current: row.creditRiskCurrent,
    credit_risk_cumulative: row.creditRiskCumulative,
    row_type: 'data',
  }))
  const fvTotal = {
    label: G10_DISCLOSURE_TOTAL_LABEL,
    fv_change_amount: calcSubtotal(fvCredit.map((r) => Number(r.fv_change_amount) || 0)),
    credit_risk_current: calcSubtotal(fvCredit.map((r) => Number(r.credit_risk_current) || 0)),
    credit_risk_cumulative: calcSubtotal(fvCredit.map((r) => Number(r.credit_risk_cumulative) || 0)),
    is_total: true,
    row_type: 'total',
  }

  return {
    交易性金融负债: [...balanceRows, total],
    [soeFvCreditTableName(auditYear)]: fvCredit.length ? [...fvCredit, fvTotal] : [fvTotal],
    _note_texts: [
      { section: 'soe-maturity-diff', text: store.maturityDiffNote },
      { section: 'soe-audit-note', text: auditNote },
    ],
  }
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
    },
  ]
  if (hasDerivativeListedData(snap.store)) {
    payloads.push({
      wp_id: wpId,
      sheet_name: sheet,
      section_id: G10_NOTE_SECTION.listed.derivative,
      current_standard: standard,
      sub_table_data: buildG10ListedDerivativeSubTableData(snap),
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
    },
  ]
}
