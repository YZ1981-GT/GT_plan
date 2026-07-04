/**
 * useF2SpecialFormulaEngine — F2 特殊组纯函数公式引擎
 */
import { calcEndBalance, calcSubtotal } from './useF2InvMaiFormulaEngine'

export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

export function calcRemainingCost(totalCost: number, incurredCost: number): number {
  return totalCost - incurredCost
}

export function calcImpairment(bookValue: number, recoverableAmount: number): number {
  return Math.max(0, bookValue - recoverableAmount)
}

export function calcRecoverableAmount(
  recognizedRevenue: number,
  estimatedTotalRevenue: number,
  estimatedTotalCost: number,
): number {
  if (!estimatedTotalRevenue) return 0
  return (recognizedRevenue / estimatedTotalRevenue) * estimatedTotalCost
}

export function isLossContract(estimatedTotalRevenue: number, estimatedTotalCost: number): boolean {
  return estimatedTotalCost > estimatedTotalRevenue
}

export function calcExpectedLoss(
  estimatedTotalRevenue: number,
  estimatedTotalCost: number,
  completionRate: number,
): number {
  if (!isLossContract(estimatedTotalRevenue, estimatedTotalCost)) return 0
  return (estimatedTotalCost - estimatedTotalRevenue) * (1 - completionRate)
}

export function calcCompletionRate(
  recognizedRevenue: number,
  estimatedTotalRevenue: number,
): number | 'N/A' {
  if (!estimatedTotalRevenue) return 'N/A'
  return recognizedRevenue / estimatedTotalRevenue
}

export function calcCapacityUtilization(actual: number, designed: number): number | 'N/A' {
  if (!designed) return 'N/A'
  return actual / designed
}

export function calcUnitConsumption(totalEnergy: number, output: number): number | '-' {
  if (!output) return '-'
  return totalEnergy / output
}

export function calcPriceDeviation(actualPrice: number, refPrice: number): number | 'N/A' {
  if (!refPrice) return 'N/A'
  return (actualPrice - refPrice) / refPrice
}

export function calcConcentrationRatio(supplierAmount: number, totalAmount: number): number {
  if (!totalAmount) return 0
  return (supplierAmount / totalAmount) * 100
}

export function calcChecklistCompletion(
  completed: number,
  total: number,
  notApplicable: number,
): number {
  const denom = total - notApplicable
  if (!denom) return 0
  return (completed / denom) * 100
}

export function calcSubtotalByCategory(
  equipment: number,
  construction: number,
  labor: number,
  other: number,
): number {
  return equipment + construction + labor + other
}

export { calcEndBalance, calcSubtotal }

export function calcAuditedAmount(endAmount: number, adjustment: number): number {
  return endAmount + adjustment
}

export function calcInputOutputRatio(input: number, output: number): number | '-' {
  if (!output) return '-'
  return input / output
}

export default {
  calcRemainingCost,
  calcImpairment,
  calcRecoverableAmount,
  isLossContract,
  calcExpectedLoss,
  calcCompletionRate,
  calcSubtotalByCategory,
  calcEndBalance,
  calcAuditedAmount,
}
