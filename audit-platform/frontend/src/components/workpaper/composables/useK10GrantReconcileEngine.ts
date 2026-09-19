/**
 * K10 政府补助核对引擎（纯函数，无副作用）
 *
 * 用于K10-4政府补助核对表：
 * - 核对"直接计入+递延分摊"合计
 * - 与K7递延收益(2401)本期分摊一致性校验
 *
 * 政府补助核对逻辑：
 *   合计计入其他收益 = 直接计入(一次性确认) + 递延分摊计入(分期确认)
 *   递延分摊计入 应与 K7递延收益(2401)本期分摊金额一致
 *   分类依据：与日常活动相关 → 其他收益(6117)；与日常活动无关 → 营业外收入(6301,K12)
 *
 * Spec: .kiro/specs/k10-other-income/
 *
 * Correctness Properties:
 * CP-K10-03: calcTotalRecognized(direct, deferred) === direct + deferred
 * CP-K10-04: isConsistentWithK7(a, b) === (Math.abs(a - b) < 0.01)
 */

import { parseNum } from './useK10FormulaEngine'

/**
 * CP-K10-03: 合计计入其他收益 = 直接计入 + 递延分摊计入
 * 适用：K10-4政府补助核对表合计行
 * - 直接计入：一次性确认为其他收益（如即征即退/财政奖励等）
 * - 递延分摊：递延收益按期分摊计入其他收益（如研发补助/设备补贴等）
 *
 * Validates: Requirements 4.2
 */
export function calcTotalRecognized(direct: number, deferred: number): number {
  return parseNum(direct) + parseNum(deferred)
}

/**
 * CP-K10-04: 与K7递延收益一致性判断
 * K10-4中"递延分摊计入"金额应与K7递延收益(2401)本期分摊金额一致
 * 容差0.01（四舍五入差异，会计准则允许的尾差）
 *
 * @param deferredInK10 K10-4中递延分摊计入金额
 * @param amortInK7 K7递延收益(2401)本期分摊金额
 * @returns true表示一致（差异<0.01），false表示不一致需关注
 *
 * Validates: Requirements 4.3, 7.5
 */
export function isConsistentWithK7(deferredInK10: number, amortInK7: number): boolean {
  return Math.abs(parseNum(deferredInK10) - parseNum(amortInK7)) < 0.01
}
