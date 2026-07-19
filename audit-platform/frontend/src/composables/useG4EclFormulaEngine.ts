/**
 * G4 债权投资(ECL组) — 公式引擎
 *
 * 纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 * 所有数值结果保留2位小数（Math.round(x * 100) / 100）。
 *
 * 核心公式链（G4-10减值测算）：
 * - Stage1/2（损失率法）：③ = ① × ②；目标审定减值 = (①+⑤)×②A
 * - Stage3（现值法）：③ = max(0, ① − PV)；目标审定减值 = max(0, (①+⑤) − PV审定)
 * - ⑥ 减值准备调整 = 目标审定减值 − ③（恒等倒挤，可负）
 * - ⑦ = ① + ⑤；⑧ = ③ + ⑥；⑨ = ⑦ − ⑧
 *
 * 展开式（仅当③=①×②时与恒等式等价）：⑥ = ⑤×②A + ①×(②A−②)
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/ Requirements 8.1~8.15
 */

// ═══ parseNum: 安全数值转换（null/undefined/NaN/空串 → 0）═══

export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ═══ P1: 损失率法减值准备 ③ = ① 账面余额 × ② 信用损失率 ═══

export function calcImpairmentProvision(bookBalance: number, creditLossRate: number): number {
  return round2(parseNum(bookBalance) * parseNum(creditLossRate))
}

// ═══ Stage3 现值法：减值 = max(0, 账面余额 − 预计未来现金流量现值) ═══

export function calcImpairmentFromPv(bookBalance: number, pvFutureCashFlow: number): number {
  return round2(Math.max(0, parseNum(bookBalance) - parseNum(pvFutureCashFlow)))
}

// ═══ P2: 账面价值 ④ = ① - ③ ═══

export function calcBookValue(bookBalance: number, impairmentProvision: number): number {
  return round2(parseNum(bookBalance) - parseNum(impairmentProvision))
}

// ═══ 目标审定减值（损失率法）：(①+⑤)×②A ═══

export function calcTargetAuditedImpairmentByRate(
  origBalance: number,
  balanceAdj: number,
  adjRate: number,
): number {
  return round2((parseNum(origBalance) + parseNum(balanceAdj)) * parseNum(adjRate))
}

// ═══ ⑥ 恒等倒挤：目标审定减值 − 未审减值 ═══

export function calcImpairmentAdjustmentIdentity(
  targetAuditedImpairment: number,
  unauditedImpairment: number,
): number {
  return round2(parseNum(targetAuditedImpairment) - parseNum(unauditedImpairment))
}

/**
 * 损失率路径减值准备调整（主路径：恒等倒挤）。
 * ⑥ = (①+⑤)×②A − ③；当未传入 unauditedImpairment 时退回展开式（兼容旧调用）。
 */
export function calcImpairmentAdjustment(
  balanceAdj: number,
  adjRate: number,
  origBalance: number,
  origRate: number,
  unauditedImpairment?: number,
): number {
  if (unauditedImpairment !== undefined) {
    const target = calcTargetAuditedImpairmentByRate(origBalance, balanceAdj, adjRate)
    return calcImpairmentAdjustmentIdentity(target, unauditedImpairment)
  }
  return calcImpairmentAdjustmentExpanded(balanceAdj, adjRate, origBalance, origRate)
}

/** 展开式：⑥ = ⑤×②A + ①×(②A−②)，仅当③=①×②时与恒等式等价 */
export function calcImpairmentAdjustmentExpanded(
  balanceAdj: number,
  adjRate: number,
  origBalance: number,
  origRate: number,
): number {
  const ba = parseNum(balanceAdj)
  const ar = parseNum(adjRate)
  const ob = parseNum(origBalance)
  const or_ = parseNum(origRate)
  return round2(ba * ar + ob * (ar - or_))
}

/** ②A 解析：未显式覆盖时回落为②（caller 传入 resolved 后的有效率亦可） */
export function resolveEffectiveRate(
  adjRate: number | null | undefined,
  origRate: number,
  adjRateTouched: boolean,
): number {
  if (adjRateTouched) return parseNum(adjRate)
  return parseNum(origRate)
}

// ═══ P4: 审定账面余额 ⑦ = ① + ⑤ ═══

export function calcAdjustedBalance(origBalance: number, balanceAdj: number): number {
  return round2(parseNum(origBalance) + parseNum(balanceAdj))
}

// ═══ P5: 审定减值准备 ⑧ = ③ + ⑥ ═══

export function calcAdjustedImpairment(origImpairment: number, impairmentAdj: number): number {
  return round2(parseNum(origImpairment) + parseNum(impairmentAdj))
}

// ═══ P6: 审定账面价值 ⑨ = ⑦ - ⑧ ═══

export function calcAdjustedBookValue(adjBalance: number, adjImpairment: number): number {
  return round2(parseNum(adjBalance) - parseNum(adjImpairment))
}

// ═══ P7: 三阶段划分（已减值 > SICR且无低风险豁免 > Stage1）═══

export function determineStage(
  hasSignificantIncrease: boolean, hasLowCreditRisk: boolean, hasCreditImpairment: boolean
): 'Stage1' | 'Stage2' | 'Stage3' {
  if (hasCreditImpairment) return 'Stage3'
  // 较低信用风险豁免：即使存在 SICR 信号，也可假定未显著增加 → Stage1
  if (hasSignificantIncrease && !hasLowCreditRisk) return 'Stage2'
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
  return round2(sumD - sumC)
}

// ═══ P12: 凭证异常判定（6项全true→正常）═══

export function isVoucherNormal(checks: boolean[]): boolean {
  return checks.length === 6 && checks.every(c => c === true)
}

// ═══ P13: 数组求和（空数组→0）═══

export function calcSumColumn(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}

// ═══ P14: 剩余期限折算 PD（年化 PD → 剩余月数）═══
// PD_t = 1 − (1 − PD_annual)^(months/12)

export function calcTermAdjustedPd(annualPd: number, remainingMonths: number): number {
  const pd = Math.min(1, Math.max(0, parseNum(annualPd)))
  const months = parseNum(remainingMonths)
  if (months <= 0 || pd <= 0) return 0
  if (pd >= 1) return 1
  const result = 1 - Math.pow(1 - pd, months / 12)
  return Math.round(result * 1e6) / 1e6
}

// ═══ P15: PD/LGD 法预期信用损失率 = PD × LGD ═══

export function calcEclRateFromPdLgd(pd: number, lgd: number): number {
  const rate = parseNum(pd) * parseNum(lgd)
  return Math.round(Math.min(1, Math.max(0, rate)) * 1e6) / 1e6
}

// ═══ P16: 损失率法预期信用损失率 = 基础损失率 + 前瞻性调整 ═══

export function calcEclRateFromLossRate(baseLossRate: number, forwardLookingAdj: number): number {
  const rate = parseNum(baseLossRate) + parseNum(forwardLookingAdj)
  return Math.round(Math.min(1, Math.max(0, rate)) * 1e6) / 1e6
}

// ═══ P17: 与上期历史损失率差异（绝对值）═══

export function calcLossRateVariance(eclRate: number, priorHistoricalLossRate: number): number {
  return Math.round(Math.abs(parseNum(eclRate) - parseNum(priorHistoricalLossRate)) * 1e6) / 1e6
}
