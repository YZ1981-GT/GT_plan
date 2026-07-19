/**
 * G6 其他债权投资(ECL组) — 公式引擎
 *
 * 8个纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 * 所有数值结果保留2位小数（Math.round(x * 100) / 100）。
 *
 * 核心公式链（G6-12减值准备测算）：
 * - Stage1/2：③ = ①账面余额 × ②损失率；⑥ = ⑤×②A + ①×(②A−②)
 * - Stage3：③ = max(0, ① − 现值)；⑥ = 目标审定减值 − ③
 * - ⑦ = ① + ⑤；⑧ = ③ + ⑥；⑨ = ⑦ − ⑧（审定摊余成本）
 *
 * 辅助判定：
 * - 三阶段划分（hasCreditImpairment优先级最高）
 * - 借贷平衡
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/ Requirements 6.1, 3.2
 */

// ═══ parseNum: 安全数值转换（null/undefined/NaN/空串 → 0）═══

export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ═══ P1: 减值准备 ③ = ① 账面余额 × ② 预期信用损失率（Stage1/2）═══

export function calcImpairmentProvision(bookBalance: number, creditLossRate: number): number {
  return round2(parseNum(bookBalance) * parseNum(creditLossRate))
}

/**
 * Stage3 现值法：减值准备 = max(0, 账面余额 − 预计未来现金流量现值)
 */
export function calcImpairmentFromPv(bookBalance: number, pvFutureCashFlow: number): number {
  return round2(Math.max(0, parseNum(bookBalance) - parseNum(pvFutureCashFlow)))
}

/**
 * 由现值反推隐含损失率 = ③ / ①（①=0 时返回 0）
 */
export function calcImpliedLossRate(bookBalance: number, impairment: number): number {
  const bal = parseNum(bookBalance)
  if (bal === 0) return 0
  return Math.round((parseNum(impairment) / bal) * 1e6) / 1e6
}

/**
 * ⑥ 恒等倒挤 = 目标审定减值 − ③（Stage3 现值法）
 */
export function calcImpairmentAdjustmentIdentity(
  targetAuditedImpairment: number,
  unadjImpairment: number,
): number {
  return round2(parseNum(targetAuditedImpairment) - parseNum(unadjImpairment))
}

// ═══ P2: 坏账调整 ⑥ = ⑤×②A + ①×(②A-②)（可负）═══

export function calcImpairmentAdjustment(
  balanceAdj: number, adjRate: number, origBalance: number, origRate: number
): number {
  const ba = parseNum(balanceAdj)
  const ar = parseNum(adjRate)
  const ob = parseNum(origBalance)
  const or_ = parseNum(origRate)
  return round2(ba * ar + ob * (ar - or_))
}

// ═══ P3: 审定账面余额 ⑦ = ① + ⑤ ═══

export function calcAdjustedBalance(origBalance: number, balanceAdj: number): number {
  return round2(parseNum(origBalance) + parseNum(balanceAdj))
}

// ═══ P4: 审定减值准备 ⑧ = ③ + ⑥ ═══

export function calcAdjustedImpairment(origImpairment: number, impairmentAdj: number): number {
  return round2(parseNum(origImpairment) + parseNum(impairmentAdj))
}

// ═══ P5: 审定摊余成本 ⑨ = ⑦ - ⑧ ═══

export function calcAdjustedBookValue(adjBalance: number, adjImpairment: number): number {
  return round2(parseNum(adjBalance) - parseNum(adjImpairment))
}

// ═══ P6: 三阶段划分（已减值 > SICR且无低风险豁免 > Stage1）═══

export function determineStage(
  hasSignificantIncrease: boolean, hasLowCreditRisk: boolean, hasCreditImpairment: boolean
): 'Stage1' | 'Stage2' | 'Stage3' {
  if (hasCreditImpairment) return 'Stage3'
  // 较低信用风险豁免：即使存在 SICR 信号，也可假定未显著增加 → Stage1（对齐 G4 / CAS22）
  if (hasSignificantIncrease && !hasLowCreditRisk) return 'Stage2'
  return 'Stage1'
}

// ═══ P7: 借贷平衡判断 — |SUM(debits) - SUM(credits)| < 0.01 ═══

export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}

// ═══ G6-13: 期限折算 PD / ECL 率 / 与上期差异 ═══

/**
 * 按阶段确定 PD 展望期月数：
 * Stage1 → min(剩余月数, 12)；Stage2/3 / 未填阶段 → 剩余存续期。
 */
export function effectivePdHorizonMonths(
  stage: string | null | undefined,
  remainingMonths: number,
): number {
  const months = Math.max(0, parseNum(remainingMonths))
  const normalized = String(stage || '').trim().toLowerCase().replace(/\s+/g, '')
  if (normalized === 'stage1' || normalized === '1' || normalized.includes('一阶段')) {
    return Math.min(months, 12)
  }
  return months
}

/** 一年期边际 PD → 期限折算 PD；传入 stage 时 Stage1 自动封顶 12 个月 */
export function calcTermAdjustedPd(
  annualPd: number,
  remainingMonths: number,
  stage?: string | null,
): number {
  const pd = Math.min(1, Math.max(0, parseNum(annualPd)))
  const months = stage != null && String(stage).trim() !== ''
    ? effectivePdHorizonMonths(stage, remainingMonths)
    : parseNum(remainingMonths)
  if (months <= 0 || pd <= 0) return 0
  if (pd >= 1) return 1
  const result = 1 - Math.pow(1 - pd, months / 12)
  return Math.round(result * 1e6) / 1e6
}

/** PD/LGD 法：ECL率 = PD × LGD（夹到 [0,1]） */
export function calcEclRateFromPdLgd(pd: number, lgd: number): number {
  const rate = parseNum(pd) * parseNum(lgd)
  return Math.round(Math.min(1, Math.max(0, rate)) * 1e6) / 1e6
}

/** 损失率法：ECL率 = 基础损失率 + 前瞻性调整（夹到 [0,1]） */
export function calcEclRateFromLossRate(baseLossRate: number, forwardLookingAdj: number): number {
  const rate = parseNum(baseLossRate) + parseNum(forwardLookingAdj)
  return Math.round(Math.min(1, Math.max(0, rate)) * 1e6) / 1e6
}

/** 与上期历史损失率绝对差异 */
export function calcLossRateVariance(eclRate: number, priorHistoricalLossRate: number): number {
  return Math.round(Math.abs(parseNum(eclRate) - parseNum(priorHistoricalLossRate)) * 1e6) / 1e6
}

// ═══ G6-14: 转回校验 / 列合计 ═══

/** 转回金额 ≤ 累计已计提减值准备（允许相等） */
export function isReversalValid(reversalAmount: number, accumulatedProvision: number): boolean {
  return parseNum(reversalAmount) <= parseNum(accumulatedProvision) + 0.005
}

export function calcSumColumn(values: number[]): number {
  const total = values.reduce((s, v) => s + parseNum(v), 0)
  return Math.round(total * 100) / 100
}
