/**
 * K9 管理费用 — 实质性分析引擎（纯函数，无副作用）
 * 科目：6602管理费用（损益类/借方科目）
 *
 * 职责：
 * - 同比变动率计算 calcYoYChange
 * - 占营业收入比计算 calcRatioToRevenue
 * - 异常波动判断 isAbnormalFluctuation
 *
 * 所有函数为纯函数，便于PBT验证。
 * 除零场景返回null（前端显示为"—"）。
 *
 * Spec: .kiro/specs/k9-admin-expenses/
 * Validates: Requirements 4.2-4.4, 9.3-9.5
 */

import { parseNum } from './useK9FormulaEngine'

/**
 * 同比变动率 = (本期 - 上期) / |上期|
 * 当上期为0时无法计算，返回null（前端显示"—"）
 * 结果为小数形式（非百分比），例如0.5表示50%
 *
 * Validates: Requirements 4.2, 9.3
 *
 * @param current 本期发生额
 * @param prior 上期发生额
 * @returns 同比变动率（小数）或null（上期为0无法计算）
 */
export function calcYoYChange(current: number, prior: number): number | null {
  const cur = parseNum(current)
  const pri = parseNum(prior)
  if (pri === 0) return null
  return (cur - pri) / Math.abs(pri)
}

/**
 * 占营业收入比 = 费用 / 营业收入
 * 当营业收入为0时无法计算，返回null（前端显示"—"）
 * 结果为小数形式（非百分比），例如0.1表示10%
 *
 * Validates: Requirements 4.3, 9.4
 *
 * @param expense 管理费用金额
 * @param revenue 营业收入金额
 * @returns 占收入比（小数）或null（营业收入为0无法计算）
 */
export function calcRatioToRevenue(expense: number, revenue: number): number | null {
  const exp = parseNum(expense)
  const rev = parseNum(revenue)
  if (rev === 0) return null
  return exp / rev
}

/**
 * 异常波动判断：|变动率| > 阈值
 * 用于实质性分析K9-4自动标记异常项目
 * threshold应为正数（例如0.3表示30%阈值）
 *
 * Validates: Requirements 4.4, 9.5
 *
 * @param changeRate 变动率（小数形式，如0.5表示50%）
 * @param threshold 异常阈值（正数，如0.3表示30%）
 * @returns true=异常波动（|变动率|>阈值），false=正常
 */
export function isAbnormalFluctuation(changeRate: number, threshold: number): boolean {
  const rate = parseNum(changeRate)
  const th = parseNum(threshold)
  return Math.abs(rate) > th
}
