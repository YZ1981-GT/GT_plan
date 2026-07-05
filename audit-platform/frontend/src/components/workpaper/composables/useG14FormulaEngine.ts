/**
 * G14 信用减值损失 — 公式引擎（纯函数）
 * Spec: .kiro/specs/g14-credit-impairment-loss/
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 审定数 = 未审 + 调整 */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number {
  return unadjusted + adjustment
}

/** 净信用减值损失（计入损益）= 本期计提 - 本期转回（转回按正数录入） */
export function calcNetImpairmentLoss(provision: number, reversal: number): number {
  return provision - reversal
}

/**
 * 模板公式 K=G+H：转回常以负数录入，与 calcNetImpairmentLoss 等价
 */
export function calcProfitLossFromSheet(provision: number, reversalSigned: number): number {
  return provision + reversalSigned
}

/**
 * 坏账准备滚动：期末 = 期初 + 计提 + 转回(带符号) - 转销
 * 与 xlsx 一致：转回常以负数录入（K=计提+转回，J=期初+计提+转回-转销）
 */
export function calcProvisionRollForward(
  opening: number,
  provision: number,
  reversalSigned: number,
  writeoff: number,
): number {
  return opening + provision + reversalSigned - writeoff
}

/** 变动额 = 本期审定 - 上期审定 */
export function calcChangeAmount(currentAudited: number, priorAudited: number): number {
  return currentAudited - priorAudited
}

/** 变动率 = (本期 - 上期) / |上期|；上期为 0 时 null */
export function calcChangeRate(priorAudited: number, currentAudited: number): number | null {
  if (priorAudited === 0) return null
  return (currentAudited - priorAudited) / Math.abs(priorAudited)
}

export function isChangeRateExceeding(rate: number | null, threshold: number): boolean {
  if (rate === null) return false
  return Math.abs(rate) > threshold
}

/** 借贷平衡 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + parseNum(v), 0)
  const c = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(d - c) < 0.01
}

export function calcVariance(computed: number, actual: number): number {
  return computed - actual
}

export function isRollForwardBalanced(
  opening: number,
  provision: number,
  reversal: number,
  writeoff: number,
  closingActual: number,
  tolerance = 0.01,
): boolean {
  return Math.abs(calcProvisionRollForward(opening, provision, reversal, writeoff) - closingActual) <= tolerance
}

export function isReconciled(audited: number, profitLoss: number, tolerance = 0.01): boolean {
  return Math.abs(audited - profitLoss) <= tolerance
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}
