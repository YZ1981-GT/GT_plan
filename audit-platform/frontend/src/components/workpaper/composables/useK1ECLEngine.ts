/**
 * K1 其他应收款 — ECL三阶段引擎（纯函数）
 *
 * ECL（Expected Credit Loss）阶段判定逻辑：
 * - Stage 3：已发生信用减值（isImpaired = true）→ 按整个存续期ECL
 * - Stage 2：信用风险显著增加（significantIncrease = true）→ 按整个存续期ECL
 * - Stage 1：正常（其他情况）→ 按12个月ECL
 *
 * ADR-1: isImpaired 优先于 significantIncrease（阶段冲突场景：已减值+未显著增加 → Stage 3）
 *
 * Spec: .kiro/specs/k1-other-receivables/ Requirements 5.2, 12.1
 */

/**
 * 阶段判定：已减值→3；显著增加→2；否则→1
 *
 * @param isImpaired - 是否已发生信用减值
 * @param significantIncrease - 信用风险是否显著增加
 * @returns 1 | 2 | 3
 */
export function determineStage(isImpaired: boolean, significantIncrease: boolean): 1 | 2 | 3 {
  if (isImpaired) return 3
  if (significantIncrease) return 2
  return 1
}

/**
 * 含较低信用风险豁免的阶段判定（对齐 K1-7 Excel / CAS 22）：
 * - 已减值 → Stage 3
 * - 显著增加且不满足低风险豁免 → Stage 2
 * - 其余（含显著增加但满足低风险豁免）→ Stage 1
 */
export function determineStageWithExemption(
  hasCreditImpairment: boolean,
  hasSignificantIncrease: boolean,
  hasLowCreditRisk: boolean,
): 1 | 2 | 3 {
  if (hasCreditImpairment) return 3
  if (hasSignificantIncrease && !hasLowCreditRisk) return 2
  return 1
}
