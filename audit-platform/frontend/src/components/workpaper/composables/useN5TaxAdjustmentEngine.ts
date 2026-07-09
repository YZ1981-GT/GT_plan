/**
 * useN5TaxAdjustmentEngine — N5 纳税调整引擎（纯函数）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 纳税调整相关计算逻辑，覆盖 N5-5/N5-7 两表。
 *
 * 核心公式：
 * - 纳税调整净额 = Σ调增 - Σ调减（P8）
 * - 财产损失纳税调整额 = 账面损失 - 税前扣除额（P10）
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 2.3
 * Requirements: 4.3, 7.2, 13.5
 */

import { parseNum } from './useN5FormulaEngine'

// ─── 1. 纳税调整净额（Property P8） ────────────────────────

/**
 * 计算纳税调整净额（Property P8）
 *
 * 纳税调整净额 = Σ调增 - Σ调减
 *
 * 来源：N5-5 纳税调整明细表（107行大表）
 * - addBacks：各项纳税调增金额（收入类/扣除类/资产类/特殊事项/其他）
 * - deducts：各项纳税调减金额（同上分类）
 *
 * 结果回填N5-4当期所得税计算表（应纳税所得额=会计利润+净额）
 *
 * @param addBacks - 纳税调增金额数组
 * @param deducts - 纳税调减金额数组
 * @returns 纳税调整净额
 */
export function calcNetAdjustment(addBacks: number[], deducts: number[]): number {
  const sumAdd = addBacks.reduce((s, v) => s + parseNum(v), 0)
  const sumDed = deducts.reduce((s, v) => s + parseNum(v), 0)
  return sumAdd - sumDed
}

// ─── 2. 财产损失纳税调整额（Property P10） ─────────────────

/**
 * 计算财产损失纳税调整额（Property P10）
 *
 * 财产损失纳税调整额 = 账面损失 - 税前扣除额
 *
 * 来源：N5-7 财产损失明细表
 * - bookLoss：账面损失金额
 * - deductibleLoss：税前扣除额（已核准扣除额）
 *
 * 正值 = 未核准部分需纳税调增（回填N5-5调增项）
 * 零值 = 账面损失全部取得核准，无税会差异
 * 负值 = 理论上不应出现（税前扣除不应超过账面损失）
 *
 * @param bookLoss - 账面损失金额
 * @param deductibleLoss - 税前扣除额（已核准）
 * @returns 财产损失纳税调整额
 */
export function calcPropertyLossAdjustment(bookLoss: number, deductibleLoss: number): number {
  return parseNum(bookLoss) - parseNum(deductibleLoss)
}
