/**
 * G7-17 减值测试 — 纯函数模型（结论自动对齐 / 双零告警 / stale / 勾稽 / 可收回覆盖）
 */
import {
  calcImpairmentAmount,
  calcRecoverableAmount,
  parseNum,
} from '../../composables/useG7EquityMethodFormulaEngine'

/** consol / G7-14 / 披露：G7-17 行落库后广播 */
export const G7_IMPAIRMENT_UPDATED_EVENT = 'g7:impairment-updated'

export type ImpairmentAuditConclusion = '无需计提' | '需计提' | '已充分计提' | ''

/** 可被公式自动改写的结论（「已充分计提」视为人工锁定） */
export const AUTO_AUDIT_CONCLUSIONS = new Set<string>(['', '无需计提', '需计提'])

export interface ImpairmentCalcInput {
  hasImpairmentSign: boolean
  bookValue: number
  fvLessDisposalCost: number
  valueInUse: number
  recoverableManual?: boolean
  recoverableAmount?: number
}

export interface ImpairmentReconResult {
  g717Total: number
  g714Total: number
  g72Total: number
  diff714: number
  diff72: number
  matched714: boolean
  matched72: boolean
}

const EPS = 0.01

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

/** 迹象=是 且 公允净额、使用价值均为 0 → 可收回=0 易误提全额减值 */
export function hasMissingRecoverableInputs(row: {
  hasImpairmentSign: boolean
  fvLessDisposalCost: number
  valueInUse: number
  recoverableManual?: boolean
}): boolean {
  if (!row.hasImpairmentSign) return false
  if (row.recoverableManual) return false
  return parseNum(row.fvLessDisposalCost) <= 0 && parseNum(row.valueInUse) <= 0
}

/**
 * 建议行结论：
 * - 已充分计提 → 不覆盖
 * - 无迹象 / 有迹象但减值=0 → 无需计提
 * - 减值>0 → 需计提
 */
export function suggestAuditConclusion(row: {
  hasImpairmentSign: boolean
  impairmentAmount: number
  auditConclusion?: string | null
}): ImpairmentAuditConclusion | null {
  const current = String(row.auditConclusion ?? '').trim()
  if (current === '已充分计提') return null

  if (!row.hasImpairmentSign) return '无需计提'
  if (parseNum(row.impairmentAmount) > 0) return '需计提'
  return '无需计提'
}

/** 仅当当前结论为空或属自动值时写入建议 */
export function applyAutoAuditConclusion<T extends {
  hasImpairmentSign: boolean
  impairmentAmount: number
  auditConclusion: string
}>(row: T): T {
  const suggested = suggestAuditConclusion(row)
  if (suggested == null) return row
  const current = String(row.auditConclusion ?? '').trim()
  if (!AUTO_AUDIT_CONCLUSIONS.has(current)) return row
  row.auditConclusion = suggested
  return row
}

/** 账面是否相对 G7-14 源值过期 */
export function isBookValueStale(
  rowBookValue: number,
  sourceBookValue: number | null | undefined,
  currentG714Book: number | null | undefined,
): boolean {
  if (currentG714Book == null || !Number.isFinite(Number(currentG714Book))) return false
  const src = sourceBookValue != null && Number.isFinite(Number(sourceBookValue))
    ? parseNum(sourceBookValue)
    : parseNum(rowBookValue)
  return Math.abs(src - parseNum(currentG714Book)) > EPS
    || Math.abs(parseNum(rowBookValue) - parseNum(currentG714Book)) > EPS
}

/** 解析可收回金额：手工覆盖优先，否则 MAX(公允, 使用价值) */
export function resolveRecoverableAmount(row: ImpairmentCalcInput): number {
  if (!row.hasImpairmentSign) return 0
  if (row.recoverableManual) return parseNum(row.recoverableAmount)
  return calcRecoverableAmount(row.fvLessDisposalCost, row.valueInUse)
}

/** 重算可收回 + 减值（尊重手工覆盖） */
export function recalcImpairmentAmounts<T extends ImpairmentCalcInput & {
  recoverableAmount: number
  impairmentAmount: number
}>(row: T): T {
  if (!row.hasImpairmentSign) {
    row.recoverableAmount = 0
    row.impairmentAmount = 0
    return row
  }
  row.recoverableAmount = resolveRecoverableAmount(row)
  row.impairmentAmount = calcImpairmentAmount(row.bookValue, row.recoverableAmount)
  return row
}

export function sumImpairmentAmounts(rows: Array<{ impairmentAmount?: number }>): number {
  return round2(rows.reduce((s, r) => s + parseNum(r.impairmentAmount), 0))
}

/** ∑G7-14.impairment（权益法测算表减值准备列） */
export function sumG714Impairment(rows: Array<{ impairment?: number }> | null | undefined): number {
  if (!rows?.length) return 0
  return round2(rows.reduce((s, r) => s + parseNum(r.impairment), 0))
}

/** ∑G7-2 减值段期末（优先审定期末） */
export function sumG72ImpairmentClosing(
  impairmentRows: Array<{ auditedClosingAmount?: number; closingAmount?: number }> | null | undefined,
): number {
  if (!impairmentRows?.length) return 0
  return round2(impairmentRows.reduce((s, r) => {
    const audited = parseNum(r.auditedClosingAmount)
    if (audited !== 0 || r.auditedClosingAmount != null) return s + audited
    return s + parseNum(r.closingAmount)
  }, 0))
}

export function calcImpairmentRecon(
  g717Total: number,
  g714Total: number,
  g72Total: number,
): ImpairmentReconResult {
  const a = round2(parseNum(g717Total))
  const b = round2(parseNum(g714Total))
  const c = round2(parseNum(g72Total))
  const diff714 = round2(a - b)
  const diff72 = round2(a - c)
  return {
    g717Total: a,
    g714Total: b,
    g72Total: c,
    diff714,
    diff72,
    matched714: Math.abs(diff714) <= EPS,
    matched72: Math.abs(diff72) <= EPS,
  }
}

export function extractG714Book(row: Record<string, unknown> | null | undefined): number {
  if (!row) return 0
  return parseNum(
    row.lteiBookBalance
    ?? row.closingBalance
    ?? row.bookValue,
  )
}
