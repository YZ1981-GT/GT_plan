/**
 * H3-7 投资性房地产折旧测算引擎（对齐致同 Excel 底稿公式）
 *
 * 复用 H1-12 已验证的日期/期数/减值分段逻辑，保证：
 * - 不含减值：月折旧、本期折旧、累计折旧、月折旧差异、累计差异
 * - 含减值：减值前/后分段月数、减值时累计折旧、减值后月折旧
 */
export {
  calcStraightLine,
  calcDepreciationWithImpairment,
  calcStraightLineTest,
  calcWithImpairmentTest,
  calcMultiImpairmentTest,
  calcMonthsDepreciated,
  calcPeriodDepMonths,
  calcFullDepreciationDate,
  parseDepDate,
} from './useH1DepreciationEngine'

export type {
  StraightLineTestResult,
  ImpairmentTestResult,
  MultiImpairmentEventInput,
} from './useH1DepreciationEngine'
