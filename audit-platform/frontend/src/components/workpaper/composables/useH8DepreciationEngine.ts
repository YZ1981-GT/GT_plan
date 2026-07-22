/**
 * H8-8 使用权资产折旧测算引擎（对齐致同 Excel 底稿公式）
 *
 * 复用 H1-12 已验证的日期/期数/减值分段逻辑：
 * - 不含减值：月折旧、本期折旧、累计折旧、月折旧差异、累计差异
 * - 含减值：减值前/后分段月数、减值时累计折旧、减值后月折旧
 *
 * 使用权资产口径补充（CAS21）：
 * - 折旧期 = min(租赁期, 使用寿命)；能合理确定取得所有权时取使用寿命
 * - 残值率实务常为 0（无所有权转移预期时）
 */
export {
  calcStraightLine,
  calcDepreciationWithImpairment,
  calcStraightLineTest,
  calcWithImpairmentTest,
  calcMonthsDepreciated,
  calcPeriodDepMonths,
  calcFullDepreciationDate,
  parseDepDate,
} from './useH1DepreciationEngine'

export type {
  StraightLineTestResult,
  ImpairmentTestResult,
} from './useH1DepreciationEngine'
