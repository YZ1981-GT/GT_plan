/**
 * useD1NotesReceivable — legacy re-export barrel
 *
 * 生产代码已迁移至 GtD1NotesReceivable + 各 Tab composable。
 * 本文件仅保留测试向后兼容的常量/纯函数 re-export。
 */
export {
  TAB_NAMES,
  PROCEDURE_STEPS_CONFIG,
  ADJUDICATION_ROWS_CONFIG,
  AGING_BANDS_CONFIG,
  type TabStatus,
} from './d1Constants'

export { getTabStatusFromResponses } from './useD1Procedure'

export {
  parseNum,
  calcAuditedAmount,
  calcChangeRate,
  calcExpectedLossRate,
  calcProvision,
  calcDifference,
} from './useD1FormulaEngine'

/** @deprecated Use calcAuditedAmount from useD1FormulaEngine (3-param net version) */
export function getAuditedAmount(
  currentUnadjusted: number,
  ajeDebit: number,
  ajeCredit: number,
  rjeDebit: number,
  rjeCredit: number,
): number {
  return currentUnadjusted + ajeDebit - ajeCredit + rjeDebit - rjeCredit
}

/** @deprecated Use calcChangeRate from useD1FormulaEngine */
export function getChangeRate(priorPeriod: number, auditedAmount: number): number | '' {
  if (priorPeriod === 0 && auditedAmount === 0) return ''
  if (priorPeriod === 0) return 1
  return (auditedAmount - priorPeriod) / priorPeriod
}

/** @deprecated Use calcExpectedLossRate from useD1FormulaEngine */
export function calculateExpectedLossRate(migrationRates: number[]): number {
  if (migrationRates.length === 0) return 0
  return migrationRates.reduce((acc, rate) => acc * rate, 1)
}

/** @deprecated Use calcProvision from useD1FormulaEngine */
export function calculateProvision(balance: number, lossRate: number): number {
  return balance * lossRate
}

/** @deprecated Use calcDifference from useD1FormulaEngine */
export function calculateDifference(actualProvision: number, shouldProvision: number): number {
  return actualProvision - shouldProvision
}

/** 贴息 = P × R × D / 360 */
export function calculateInterest(p: number, r: number, d: number): number {
  return p * r * d / 360
}

/** 监盘倒推：资产负债表日余额 = 盘点日余额 + 期间增加 - 期间减少 */
export function calculateBSDateBalance(countBalance: number, additions: number, deductions: number): number {
  return countBalance + additions - deductions
}

export default {}
