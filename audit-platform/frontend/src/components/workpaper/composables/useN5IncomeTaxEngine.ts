/**
 * useN5IncomeTaxEngine — N5 所得税计算引擎（核心，纯函数）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 所得税审计核心逻辑，计算链跨 N5-4/N5-5/N5-6/N5-8 多表。
 *
 * 核心公式：
 * - 应纳税所得额 = 会计利润 + 纳税调增 - 纳税调减（P3）
 * - 当期所得税 = 应纳税所得额 × 适用税率（P4）
 * - 所得税费用 = 当期所得税 + 递延所得税费用（P5）
 * - 递延所得税费用 = 递延税负债增加 - 递延税资产增加（P6）
 * - 研发加计扣除额 = 研发费用 × 加计比例（P7）
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 2.2
 * Requirements: 3.2, 3.3, 5.2, 8.2, 13.1-13.4, 13.6
 */

import { parseNum } from './useN5FormulaEngine'

// ─── 1. 应纳税所得额（Property P3） ────────────────────────

/**
 * 计算应纳税所得额（Property P3）
 *
 * 应纳税所得额 = 会计利润总额 + 纳税调增合计 - 纳税调减合计
 *
 * 来源：N5-4 当期所得税费用计算表
 * - 会计利润总额：取自A类利润表（联动）
 * - 纳税调增/调减合计：取自N5-5纳税调整明细
 *
 * @param accountingProfit - 会计利润总额
 * @param addBack - 纳税调增合计（≥0）
 * @param deduct - 纳税调减合计（≥0）
 * @returns 应纳税所得额
 */
export function calcTaxableIncome(accountingProfit: number, addBack: number, deduct: number): number {
  return parseNum(accountingProfit) + parseNum(addBack) - parseNum(deduct)
}

// ─── 2. 当期所得税（Property P4） ──────────────────────────

/**
 * 计算当期所得税（Property P4）
 *
 * 当期所得税 = 应纳税所得额 × 适用税率
 *
 * 常见税率：
 * - 25%：一般企业
 * - 15%：高新技术企业
 * - 20%：小型微利企业
 *
 * 来源：N5-4 当期所得税费用计算表
 *
 * @param taxableIncome - 应纳税所得额
 * @param taxRate - 适用税率（小数，如0.25表示25%）
 * @returns 当期所得税
 */
export function calcCurrentTax(taxableIncome: number, taxRate: number): number {
  return parseNum(taxableIncome) * parseNum(taxRate)
}

// ─── 3. 所得税费用（Property P5） ──────────────────────────

/**
 * 计算所得税费用（Property P5）
 *
 * 所得税费用 = 当期所得税费用 + 递延所得税费用
 *
 * 来源：N5-1 审定表
 * - 当期所得税费用：取自N5-4
 * - 递延所得税费用：取自N5-8
 *
 * @param currentTax - 当期所得税费用
 * @param deferredTax - 递延所得税费用
 * @returns 所得税费用合计
 */
export function calcIncomeTaxExpense(currentTax: number, deferredTax: number): number {
  return parseNum(currentTax) + parseNum(deferredTax)
}

// ─── 4. 递延所得税费用（Property P6） ──────────────────────

/**
 * 计算递延所得税费用（Property P6）
 *
 * 递延所得税费用 = 递延税负债本期增加 - 递延税资产本期增加
 *
 * 来源：N5-8 递延所得税费用核对表
 * - 递延税负债本期增加：subscribe N3（'deferred-tax:liability-updated'）
 * - 递延税资产本期增加：subscribe N1（'deferred-tax:asset-updated'）
 *
 * 正值 = 费用增加；负值 = 费用减少（递延税资产增加>负债增加时，减少所得税费用）
 *
 * @param liabilityIncrease - 递延税负债本期增加
 * @param assetIncrease - 递延税资产本期增加
 * @returns 递延所得税费用
 */
export function calcDeferredTaxExpense(liabilityIncrease: number, assetIncrease: number): number {
  return parseNum(liabilityIncrease) - parseNum(assetIncrease)
}

// ─── 5. 研发费用加计扣除（Property P7） ────────────────────

/**
 * 计算研发费用加计扣除额（Property P7）
 *
 * 加计扣除额 = 研发费用 × 加计比例
 *
 * 来源：N5-6-1 加计扣除研发费用情况明细表
 * - 研发费用：取自I6研发费用/I2开发支出（费用化+资本化）
 * - 加计比例：
 *   - 100%：一般企业（2023年起）
 *   - 120%：集成电路/工业母机等特定行业
 *   - 75%：其他（历史税率）
 *   - 50%：早期政策（已不适用）
 *
 * @param rdExpense - 研发费用合计
 * @param superRate - 加计比例（小数，如1.0表示100%加计）
 * @returns 加计扣除额
 */
export function calcRdSuperDeduction(rdExpense: number, superRate: number): number {
  return parseNum(rdExpense) * parseNum(superRate)
}
