/**
 * G14 信用减值损失 — 公式引擎（纯函数）
 * Spec: .kiro/specs/g14-credit-impairment-loss/
 *
 * 对齐致同 xlsx「明细表G14-2」：
 * - 计入损益 K = 本期计提 G − 本期转回 H（转回按正数录入）
 * - 期末余额 J = 期初 F + 计提 G − 转回 H − 转销 I + 其他变动
 * - 核对：审定数 D = 计入损益 K
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

/** 净信用减值损失（计入损益）= 本期计提 − 本期转回（转回按正数录入） */
export function calcNetImpairmentLoss(provision: number, reversal: number): number {
  return provision - reversal
}

/**
 * 计入损益（与 xlsx K 列一致）
 * @deprecated 请优先使用 calcNetImpairmentLoss；保留别名兼容旧调用
 */
export function calcProfitLossFromSheet(provision: number, reversalPositive: number): number {
  return calcNetImpairmentLoss(provision, reversalPositive)
}

/**
 * 坏账/减值准备滚动：期末 = 期初 + 计提 − 转回 − 转销 + 其他变动
 * 与致同 xlsx、D1/G5 等源科目准备变动表同口径（转回为正数减少额）
 */
export function calcProvisionRollForward(
  opening: number,
  provision: number,
  reversal: number,
  writeoff: number,
  otherMovement = 0,
): number {
  return opening + provision - reversal - writeoff + otherMovement
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
  otherMovement = 0,
  tolerance = 0.01,
): boolean {
  return Math.abs(
    calcProvisionRollForward(opening, provision, reversal, writeoff, otherMovement) - closingActual,
  ) <= tolerance
}

export function isReconciled(audited: number, profitLoss: number, tolerance = 0.01): boolean {
  return Math.abs(audited - profitLoss) <= tolerance
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}

/**
 * 旧版「转回带符号（负数）」→ 正数口径迁移。
 * 仅当值为负时取绝对值；已为正数的数据不变。
 */
export function migrateReversalToPositive(reversal: number): number {
  const n = parseNum(reversal)
  return n < 0 ? Math.abs(n) : n
}
