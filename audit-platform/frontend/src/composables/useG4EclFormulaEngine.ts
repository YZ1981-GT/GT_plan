/**
 * G4 债权投资(ECL组) — 公式引擎
 *
 * 15个纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 * 所有数值结果保留2位小数（Math.round(x * 100) / 100）。
 *
 * 核心公式链（G4-10减值测算）：
 * - ③ 减值准备 = ① 账面余额 × ② 信用损失率
 * - ④ 账面价值 = ① - ③
 * - ⑥ 减值准备调整 = ⑤×②A + ①×(②A-②)（可负）
 * - ⑦ 审定账面余额 = ① + ⑤
 * - ⑧ 审定减值准备 = ③ + ⑥
 * - ⑨ 审定账面价值 = ⑦ - ⑧
 *
 * 辅助判定：
 * - 三阶段划分（creditImpaired优先级最高）
 * - 阶段一致性 / 转回有效性 / 借贷平衡 / 凭证异常
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/ Requirements 8.1~8.15
 */

// ═══ parseNum: 安全数值转换（null/undefined/NaN/空串 → 0）═══

export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ═══ P1: 减值准备 ③ = ① 账面余额 × ② 信用损失率 ═══

export function calcImpairmentProvision(bookBalance: number, creditLossRate: number): number {
  return Math.round(parseNum(bookBalance) * parseNum(creditLossRate) * 100) / 100
}

// ═══ P2: 账面价值 ④ = ① - ③ ═══

export function calcBookValue(bookBalance: number, impairmentProvision: number): number {
  return Math.round((parseNum(bookBalance) - parseNum(impairmentProvision)) * 100) / 100
}

// ═══ P3: 减值准备调整 ⑥ = ⑤×②A + ①×(②A-②)（可负）═══

export function calcImpairmentAdjustment(
  balanceAdj: number, adjRate: number, origBalance: number, origRate: number
): number {
  const ba = parseNum(balanceAdj)
  const ar = parseNum(adjRate)
  const ob = parseNum(origBalance)
  const or_ = parseNum(origRate)
  return Math.round((ba * ar + ob * (ar - or_)) * 100) / 100
}

// ═══ P4: 审定账面余额 ⑦ = ① + ⑤ ═══

export function calcAdjustedBalance(origBalance: number, balanceAdj: number): number {
  return Math.round((parseNum(origBalance) + parseNum(balanceAdj)) * 100) / 100
}

// ═══ P5: 审定减值准备 ⑧ = ③ + ⑥ ═══

export function calcAdjustedImpairment(origImpairment: number, impairmentAdj: number): number {
  return Math.round((parseNum(origImpairment) + parseNum(impairmentAdj)) * 100) / 100
}

// ═══ P6: 审定账面价值 ⑨ = ⑦ - ⑧ ═══

export function calcAdjustedBookValue(adjBalance: number, adjImpairment: number): number {
  return Math.round((parseNum(adjBalance) - parseNum(adjImpairment)) * 100) / 100
}

// ═══ P7: 三阶段划分（creditImpaired优先级最高）═══

export function determineStage(
  hasSignificantIncrease: boolean, hasLowCreditRisk: boolean, hasCreditImpairment: boolean
): 'Stage1' | 'Stage2' | 'Stage3' {
  if (hasCreditImpairment) return 'Stage3'
  if (hasSignificantIncrease) return 'Stage2'
  return 'Stage1'
}

// ═══ P8: 阶段一致性判定 ═══

export function isStageConsistent(companyStage: string, auditStage: string): boolean {
  return companyStage === auditStage
}

// ═══ P9: 转回有效性（转回 ≤ 累计计提）═══

export function isReversalValid(reversalAmount: number, accumulatedProvision: number): boolean {
  return parseNum(reversalAmount) <= parseNum(accumulatedProvision)
}

// ═══ P10: 借贷平衡判断 — |SUM(debits) - SUM(credits)| < 0.01 ═══

export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}

// ═══ P11: 借贷差额 = SUM(debits) - SUM(credits)，保留2位小数 ═══

export function calcDebitCreditDifference(debits: number[], credits: number[]): number {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.round((sumD - sumC) * 100) / 100
}

// ═══ P12: 凭证异常判定（6项全true→正常）═══

export function isVoucherNormal(checks: boolean[]): boolean {
  return checks.length === 6 && checks.every(c => c === true)
}

// ═══ P13: 数组求和（空数组→0）═══

export function calcSumColumn(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}
