/**
 * G7-15 内部交易抵销 — 纯函数行模型（供 UI 与单测共用）
 */
import {
  calcEliminationAmount,
  calcUnrealizedProfit,
  parseNum,
} from '../../composables/useG7EquityMethodFormulaEngine'
import type { InternalTransactionRow } from '../../composables/useG7EquityMethodFormData'

function toBool(raw: unknown): boolean {
  if (typeof raw === 'boolean') return raw
  return ['是', 'true', '1', 'yes', 'y'].includes(String(raw ?? '').trim().toLowerCase())
}

export function createEmptyInternalTransactionRow(
  seq: number,
  investeeName = '',
  investeeId = '',
): InternalTransactionRow {
  return {
    id: `g15-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    investeeId: investeeId || undefined,
    investeeName,
    transactionType: '' as InternalTransactionRow['transactionType'],
    transactionContent: '',
    transactionAmount: 0,
    grossMargin: 0,
    unrealizedProfit: 0,
    unrealizedProfitManual: false,
    investmentRatio: 0,
    eliminationAmount: 0,
    priorElimination: 0,
    currentChange: 0,
    eliminationEntry: '',
    isRelatedParty: false,
    auditConclusion: '' as InternalTransactionRow['auditConclusion'],
    indexRef: '',
    remark: '',
  }
}

/** 重算未实现利润 / 应抵销 / 本年变动 */
export function recalcInternalTransactionRow(row: InternalTransactionRow): void {
  if (!row.unrealizedProfitManual) {
    row.unrealizedProfit = calcUnrealizedProfit(row.transactionAmount, row.grossMargin)
  }

  if (row.transactionType === '顺流') {
    row.eliminationAmount = calcEliminationAmount(
      'downstream',
      row.unrealizedProfit,
      row.investmentRatio,
    )
  } else if (row.transactionType === '逆流') {
    row.eliminationAmount = calcEliminationAmount(
      'upstream',
      row.unrealizedProfit,
      row.investmentRatio,
    )
  } else {
    row.eliminationAmount = 0
  }

  if (row.transactionType) {
    row.currentChange = Math.round(
      (row.eliminationAmount - parseNum(row.priorElimination)) * 100,
    ) / 100
  } else {
    row.currentChange = 0
  }
}

/** 清除手工覆盖，按 金额×毛利率 重算未实现利润 */
export function clearUnrealizedProfitManual(row: InternalTransactionRow): void {
  row.unrealizedProfitManual = false
  recalcInternalTransactionRow(row)
}

/** 从 checklist / Excel 导入行水合；毛利率缺失或为 0 时保住已填未实现利润 */
export function hydrateInternalTransactionRow(
  raw: Record<string, any>,
  seq: number,
): InternalTransactionRow {
  const margin = parseNum(raw.grossMargin ?? raw.gross_margin)
  const profit = parseNum(raw.unrealizedProfit ?? raw.unrealized_profit)
  let manual = toBool(raw.unrealizedProfitManual ?? raw.unrealized_profit_manual)
  // 毛利率缺失/为 0 且已有未实现利润 → 视为手工，避免公式清零
  if (!manual && Math.abs(margin) < 1e-12 && Math.abs(profit) > 0.005) {
    manual = true
  }

  const row: InternalTransactionRow = {
    ...createEmptyInternalTransactionRow(seq),
    ...raw,
    seq,
    id: raw.id || `g15-${Date.now()}-${seq}`,
    investeeId: String(raw.investeeId ?? raw.investee_id ?? '').trim() || undefined,
    investeeName: String(raw.investeeName ?? raw.investee_name ?? '').trim(),
    grossMargin: margin,
    unrealizedProfit: profit,
    unrealizedProfitManual: manual,
    investmentRatio: parseNum(raw.investmentRatio ?? raw.investment_ratio),
    transactionAmount: parseNum(raw.transactionAmount ?? raw.transaction_amount),
    priorElimination: parseNum(raw.priorElimination ?? raw.prior_elimination),
    isRelatedParty: toBool(raw.isRelatedParty ?? raw.is_related_party),
    transactionType: (raw.transactionType || raw.transaction_type || '') as InternalTransactionRow['transactionType'],
    auditConclusion: (raw.auditConclusion || raw.audit_conclusion || '') as InternalTransactionRow['auditConclusion'],
  }
  recalcInternalTransactionRow(row)
  return row
}

export function hydrateInternalTransactionRows(raw: unknown): InternalTransactionRow[] {
  const list = Array.isArray(raw)
    ? raw
    : (raw && typeof raw === 'object' && Array.isArray((raw as any).rows)
      ? (raw as any).rows
      : null)
  if (!list?.length) return []
  return list.map((r: any, idx: number) => hydrateInternalTransactionRow(r || {}, idx + 1))
}
