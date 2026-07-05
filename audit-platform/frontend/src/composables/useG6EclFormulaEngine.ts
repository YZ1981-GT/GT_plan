/**
 * G6 其他债权投资(ECL组) — 公式引擎
 *
 * 8个纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 * 所有数值结果保留2位小数（Math.round(x * 100) / 100）。
 *
 * 核心公式链（G6-12减值准备测算）：
 * - ③ 坏账准备 = ① 摊余成本余额 × ② 预期信用损失率
 * - ⑥ 坏账调整 = ⑤×②A + ①×(②A-②)（可负）
 * - ⑦ 审定余额 = ① + ⑤
 * - ⑧ 审定坏账 = ③ + ⑥
 * - ⑨ 审定账面价值 = ⑦ - ⑧
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

// ═══ P1: 坏账准备 ③ = ① 摊余成本余额 × ② 预期信用损失率 ═══

export function calcImpairmentProvision(amortizedCost: number, creditLossRate: number): number {
  return Math.round(parseNum(amortizedCost) * parseNum(creditLossRate) * 100) / 100
}

// ═══ P2: 坏账调整 ⑥ = ⑤×②A + ①×(②A-②)（可负）═══

export function calcImpairmentAdjustment(
  balanceAdj: number, adjRate: number, origBalance: number, origRate: number
): number {
  const ba = parseNum(balanceAdj)
  const ar = parseNum(adjRate)
  const ob = parseNum(origBalance)
  const or_ = parseNum(origRate)
  return Math.round((ba * ar + ob * (ar - or_)) * 100) / 100
}

// ═══ P3: 审定余额 ⑦ = ① + ⑤ ═══

export function calcAdjustedBalance(origBalance: number, balanceAdj: number): number {
  return Math.round((parseNum(origBalance) + parseNum(balanceAdj)) * 100) / 100
}

// ═══ P4: 审定坏账 ⑧ = ③ + ⑥ ═══

export function calcAdjustedImpairment(origImpairment: number, impairmentAdj: number): number {
  return Math.round((parseNum(origImpairment) + parseNum(impairmentAdj)) * 100) / 100
}

// ═══ P5: 审定账面价值 ⑨ = ⑦ - ⑧ ═══

export function calcAdjustedBookValue(adjBalance: number, adjImpairment: number): number {
  return Math.round((parseNum(adjBalance) - parseNum(adjImpairment)) * 100) / 100
}

// ═══ P6: 三阶段划分（hasCreditImpairment优先级最高）═══

export function determineStage(
  hasSignificantIncrease: boolean, hasLowCreditRisk: boolean, hasCreditImpairment: boolean
): 'Stage1' | 'Stage2' | 'Stage3' {
  if (hasCreditImpairment) return 'Stage3'
  if (hasSignificantIncrease) return 'Stage2'
  return 'Stage1'
}

// ═══ P7: 借贷平衡判断 — |SUM(debits) - SUM(credits)| < 0.01 ═══

export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}
