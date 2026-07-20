/**
 * G7-11 处置（非一揽子）— 纯函数行模型
 */
import { calcDisposalGain, parseNum } from '../../composables/useG7SubFormulaEngine'

export interface G7DisposalSingleRow {
  id: string
  seq: number
  investeeId?: string
  investeeName: string
  disposalDate: string
  /** 小数 0~1 */
  disposalRatio: number
  disposalPrice: number
  disposalDateBookValue: number
  disposalDateDividend: number
  /** 备查：处置前 OCI 累计（不进个别损益公式） */
  priorOCICumulative: number
  /** 入账：可转损益 OCI */
  transferableOCI: number
  individualGain: number
  consolidationAdjustment: number
  consolidatedNetAssetShare: number
  consolidatedGain: number
  /** true=合并处置损益手工覆盖，不再用公式重算 */
  consolidatedGainManual?: boolean
  auditConclusion: string
  indexRef: string
}

export function createEmptyDisposalSingleRow(
  seq: number,
  investeeName = '',
  investeeId = '',
): G7DisposalSingleRow {
  return {
    id: `g11-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    investeeId: investeeId || undefined,
    investeeName,
    disposalDate: '',
    disposalRatio: 0,
    disposalPrice: 0,
    disposalDateBookValue: 0,
    disposalDateDividend: 0,
    priorOCICumulative: 0,
    transferableOCI: 0,
    individualGain: 0,
    consolidationAdjustment: 0,
    consolidatedNetAssetShare: 0,
    consolidatedGain: 0,
    consolidatedGainManual: false,
    auditConclusion: '',
    indexRef: '',
  }
}

/** 百分数→小数：|v|>1 视为百分数（如 30→0.3） */
export function normalizeDisposalRatio(raw: unknown): number {
  const v = parseNum(raw)
  if (Math.abs(v) > 1.0000001) return Math.round((v / 100) * 1e8) / 1e8
  return v
}

/** 处置比例：0~1（含端点）；>1 或 <0 无效（须先 normalize） */
export function validateDisposalRatio(ratio: unknown): { valid: boolean; message?: string } {
  const r = parseNum(ratio)
  if (r < 0) return { valid: false, message: '处置比例不能为负数' }
  if (r > 1) return { valid: false, message: '处置比例不能超过100%' }
  return { valid: true }
}

export function calcConsolidatedDisposalGain(
  individualGain: number,
  consolidationAdjustment: number,
  consolidatedNetAssetShare: number,
): number {
  return Math.round(
    (parseNum(individualGain)
      + parseNum(consolidationAdjustment)
      - parseNum(consolidatedNetAssetShare)) * 100,
  ) / 100
}

export function recalcDisposalSingleRow(row: G7DisposalSingleRow): void {
  row.individualGain = calcDisposalGain(
    parseNum(row.disposalPrice),
    parseNum(row.disposalDateBookValue),
    parseNum(row.disposalDateDividend),
    parseNum(row.transferableOCI),
  )
  if (!row.consolidatedGainManual) {
    row.consolidatedGain = calcConsolidatedDisposalGain(
      row.individualGain,
      row.consolidationAdjustment,
      row.consolidatedNetAssetShare,
    )
  }
}

export function clearConsolidatedGainManual(row: G7DisposalSingleRow): void {
  row.consolidatedGainManual = false
  recalcDisposalSingleRow(row)
}

function toBool(raw: unknown): boolean {
  if (typeof raw === 'boolean') return raw
  return ['是', 'true', '1', 'yes', 'y'].includes(String(raw ?? '').trim().toLowerCase())
}

export function hydrateDisposalSingleRow(
  raw: Record<string, any>,
  seq: number,
): G7DisposalSingleRow {
  const row: G7DisposalSingleRow = {
    ...createEmptyDisposalSingleRow(seq),
    seq,
    id: raw.id || `g11-${Date.now()}-${seq}`,
    investeeId: String(raw.investeeId ?? raw.investee_id ?? '').trim() || undefined,
    investeeName: String(raw.investeeName ?? raw.investee_name ?? '').trim(),
    disposalDate: String(raw.disposalDate ?? raw.disposal_date ?? ''),
    disposalRatio: normalizeDisposalRatio(raw.disposalRatio ?? raw.disposal_ratio),
    disposalPrice: parseNum(raw.disposalPrice ?? raw.disposal_price),
    disposalDateBookValue: parseNum(
      raw.disposalDateBookValue
      ?? raw.disposal_date_book_value
      ?? raw.bookValueDisposed
      ?? raw.book_value_disposed,
    ),
    disposalDateDividend: parseNum(
      raw.disposalDateDividend
      ?? raw.disposal_date_dividend
      ?? raw.dividendReceivable
      ?? raw.dividend_receivable,
    ),
    priorOCICumulative: parseNum(raw.priorOCICumulative ?? raw.prior_oci_cumulative),
    transferableOCI: parseNum(raw.transferableOCI ?? raw.transferable_oci),
    consolidationAdjustment: parseNum(
      raw.consolidationAdjustment
      ?? raw.consolidation_adjustment
      ?? raw.consolAdjustment
      ?? raw.consol_adjustment,
    ),
    consolidatedNetAssetShare: parseNum(
      raw.consolidatedNetAssetShare
      ?? raw.consolidated_net_asset_share
      ?? raw.netAssetShare
      ?? raw.net_asset_share,
    ),
    consolidatedGain: parseNum(raw.consolidatedGain ?? raw.consolidated_gain),
    consolidatedGainManual: toBool(
      raw.consolidatedGainManual ?? raw.consolidated_gain_manual,
    ),
    auditConclusion: String(raw.auditConclusion ?? raw.audit_conclusion ?? ''),
    indexRef: String(raw.indexRef ?? raw.index_ref ?? ''),
    individualGain: 0,
  }
  recalcDisposalSingleRow(row)
  return row
}

/** 设置合并处置损益手工覆盖 */
export function setConsolidatedGainManual(row: G7DisposalSingleRow, value: number): void {
  row.consolidatedGainManual = true
  row.consolidatedGain = parseNum(value)
}

export function hydrateDisposalSingleRows(raw: unknown): G7DisposalSingleRow[] {
  const list = Array.isArray(raw)
    ? raw
    : (raw && typeof raw === 'object' && Array.isArray((raw as any).rows)
      ? (raw as any).rows
      : null)
  if (!list?.length) return []
  return list.map((r: any, idx: number) => hydrateDisposalSingleRow(r || {}, idx + 1))
}

/** 不丧失控制权处置后剩余账面 = ① × (1 − ③/②) */
export function calcRemainingBookAfterPartialDisposal(row: Record<string, any>): number | null {
  const book = parseNum(row.bookValueAtDisposal ?? row.book_value_at_disposal)
  if (!book) return null
  const original = parseNum(row.originalRatio ?? row.original_ratio)
  const reduced = parseNum(row.reducedRatio ?? row.reduced_ratio)
  if (original > 0 && reduced >= 0) {
    const remainRatio = 1 - reduced / original
    if (Number.isFinite(remainRatio) && remainRatio >= 0) {
      return Math.round(book * remainRatio * 100) / 100
    }
  }
  return book
}

/**
 * 从 G7-10 行取处置后账面（优先 partialDisposal 剩余账面）。
 * 匹配 investeeId / companyName / investeeName。
 */
export function pickBookValueFromG710(
  g710Raw: unknown,
  investeeName: string,
  investeeId?: string,
): number | null {
  const parsed = typeof g710Raw === 'string'
    ? (() => { try { return JSON.parse(g710Raw) } catch { return null } })()
    : g710Raw
  const list = Array.isArray(parsed)
    ? parsed
    : (parsed && typeof parsed === 'object' && Array.isArray((parsed as any).rows)
      ? (parsed as any).rows
      : null)
  if (!list?.length) return null
  const name = investeeName.trim()
  const id = String(investeeId ?? '').trim()
  const match = (r: any) => {
    const rid = String(r.investeeId ?? r.investee_id ?? '').trim()
    const rname = String(
      r.companyName ?? r.company_name ?? r.investeeName ?? r.investee_name ?? '',
    ).trim()
    if (id && rid && id === rid) return true
    return !!name && rname === name
  }
  const partial = list.find(
    (r: any) => match(r) && String(r.section || '') === 'partialDisposal',
  )
  if (partial) {
    const remaining = calcRemainingBookAfterPartialDisposal(partial)
    if (remaining) return remaining
  }
  const any = list.find(match)
  if (!any) return null
  if (String(any.section || '') === 'partialDisposal') {
    const remaining = calcRemainingBookAfterPartialDisposal(any)
    if (remaining) return remaining
  }
  const candidates = [
    any.bookValueAtDisposal,
    any.book_value_at_disposal,
    any.priorCarryingAmount,
    any.prior_carrying_amount,
    any.closingBalance,
    any.closing_balance,
    any.carryingAmount,
  ]
  for (const c of candidates) {
    const v = parseNum(c)
    if (v) return v
  }
  return null
}
