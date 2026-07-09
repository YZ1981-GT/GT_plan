/**
 * K8 销售费用 — 实质性分析引擎（纯函数，无副作用）
 * 科目：6601销售费用（损益类/借方科目）
 *
 * 职责：
 * - 同比变动率计算 calcYoYChange
 * - 占营业收入比计算 calcRatioToRevenue
 * - 异常波动判断 isAbnormalFluctuation
 * - 结构比计算 calcStructureRatio
 *
 * 所有函数为纯函数，便于PBT验证。
 * 除零场景返回null（前端显示为"—"）。
 *
 * Spec: .kiro/specs/k8-selling-expenses/
 * Validates: Requirements 4.2-4.4, 9.3-9.5
 */

import { parseNum } from './useK8FormulaEngine'

/**
 * 同比变动率 = (本期 - 上期) / |上期|
 * 当上期为0时无法计算，返回null（前端显示"—"）
 * 结果为小数形式（非百分比），例如0.5表示50%
 *
 * Validates: Requirements 4.2, 9.3
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
 */
export function calcRatioToRevenue(expense: number, revenue: number): number | null {
  const exp = parseNum(expense)
  const rev = parseNum(revenue)
  if (rev === 0) return null
  return exp / rev
}

/**
 * 异常波动判断：|变动率| > 阈值
 * 用于实质性分析K8-4自动标记异常项目
 * threshold应为正数（例如0.3表示30%阈值）
 *
 * Validates: Requirements 4.4, 9.5
 */
export function isAbnormalFluctuation(changeRate: number, threshold: number): boolean {
  const rate = parseNum(changeRate)
  const th = parseNum(threshold)
  return Math.abs(rate) > th
}

/**
 * 结构比 = 项目金额 / 合计金额
 * 用于实质性分析K8-4各费用项目占费用总额的比例
 * 当合计为0时返回0（无法计算结构比）
 * 结果为小数形式（非百分比）
 */
export function calcStructureRatio(item: number, total: number): number {
  const itemVal = parseNum(item)
  const totalVal = parseNum(total)
  if (totalVal === 0) return 0
  return itemVal / totalVal
}
