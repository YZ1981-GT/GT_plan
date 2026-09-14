/**
 * useD2AccountsReceivable — legacy re-export barrel
 *
 * 生产代码已迁移至 GtD2AccountsReceivable + 各 Tab composable。
 * 本文件仅保留测试向后兼容的常量/纯函数 re-export。
 */
export {
  TAB_NAMES,
  PROCEDURE_STEPS_CONFIG,
  AGING_BANDS_CONFIG,
  ADJUDICATION_ROWS_CONFIG,
  getTabStatusFromResponses,
  type TabStatus,
} from './d2Constants'

export {
  getAuditedAmount,
  getChangeRate,
  calculateProvision,
  calculateDifference,
  calculatePledgeRatio,
  determineCutoff,
  calculateExpectedLossRate,
  calculateTurnoverRate,
  calculateTurnoverDays,
  sumifLegacy as sumif,
} from './useD2FormulaEngine'
