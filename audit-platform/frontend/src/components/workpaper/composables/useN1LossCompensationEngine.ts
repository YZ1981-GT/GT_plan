/**
 * useN1LossCompensationEngine — N1 可弥补亏损确认引擎（纯函数）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 对应 N1-5 sheet：可用以后年度税前利润弥补的亏损检查表。
 *
 * ─── 谨慎性原则 ───
 * 只有在"很可能取得用来抵扣的未来应纳税所得额"时，才确认递延所得税资产。
 * 可确认递延税资产 = min(未弥补亏损, 预计未来应纳税所得额) × 适用税率
 * 不足部分不确认（企业会计准则第18号——所得税 第15条）。
 * ──────────────────
 *
 * ─── 弥补期限 ───
 * 一般企业：亏损发生年度起 5 年（税法第18条）
 * 高新技术企业 / 科技型中小企业：亏损发生年度起 10 年（财税[2018]76号/45号）
 * 届满未弥补的亏损不再确认递延税资产。
 * ─────────────────
 *
 * 本引擎覆盖：
 * - 未弥补亏损计算（亏损金额-已弥补金额）
 * - 可确认递延税资产计算（谨慎性上限）
 * - 弥补期限是否届满判断
 * - 剩余弥补年限计算
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/ Task 2.3
 * Requirements: 5.2, 5.3
 */

import { parseNum } from './useN1FormulaEngine'

// ─── 1. 未弥补亏损 ─────────────────────────────────────────

/**
 * 计算未弥补亏损（Property P6）
 *
 * 公式：未弥补亏损 = 亏损金额 - 已弥补金额
 *
 * 来源：N1-5 可用以后年度税前利润弥补的亏损检查表
 * 亏损金额为该年度确认的税务亏损，已弥补金额为历年已用盈利弥补部分。
 *
 * 边界情况：
 * - 负值输入按0处理（亏损金额不可能为负，已弥补不可能为负）
 * - 已弥补 > 亏损金额时，返回0（不允许负的未弥补额）
 *
 * @param lossAmount - 亏损金额（应为非负值）
 * @param recovered - 已弥补金额（应为非负值）
 * @returns 未弥补亏损（≥0）
 */
export function calcUnrecoveredLoss(lossAmount: number, recovered: number): number {
  const loss = Math.max(0, parseNum(lossAmount))
  const rec = Math.max(0, parseNum(recovered))
  return Math.max(0, loss - rec)
}

// ─── 2. 可确认递延税资产 ───────────────────────────────────

/**
 * 计算可确认递延税资产（Property P7）
 *
 * 公式：可确认递延税资产 = min(未弥补亏损, 预计未来应纳税所得额) × 适用税率
 *
 * 来源：N1-5 可用以后年度税前利润弥补的亏损检查表
 *
 * ─── 谨慎性原则（CAS 18 第15条） ───
 * 企业对于能够结转以后年度的可抵扣亏损和税款抵减，
 * 应当以很可能获得用来抵扣的未来应纳税所得额为限，
 * 确认相应的递延所得税资产。
 * ────────────────────────────────────
 *
 * 逻辑：取未弥补亏损与预计未来应纳税所得额中较小值（上限约束），
 *       再乘以适用税率得到可确认的递延税资产金额。
 *
 * 边界情况：
 * - 未弥补亏损≤0 → 返回0（无亏损可弥补）
 * - 预计未来应纳税所得额≤0 → 返回0（未来无法抵扣）
 * - 税率≤0或>1 → 返回0（无效税率不确认）
 *
 * @param unrecovered - 未弥补亏损
 * @param futureTaxableIncome - 预计未来应纳税所得额（弥补期限内）
 * @param taxRate - 适用税率（如0.25表示25%）
 * @returns 可确认递延税资产金额（≥0）
 */
export function calcRecognizableAsset(
  unrecovered: number,
  futureTaxableIncome: number,
  taxRate: number,
): number {
  const u = parseNum(unrecovered)
  const fti = parseNum(futureTaxableIncome)
  const rate = parseNum(taxRate)

  // 边界：任一输入≤0则无法确认
  if (u <= 0 || fti <= 0 || rate <= 0 || rate > 1) return 0

  return Math.min(u, fti) * rate
}

// ─── 3. 弥补期限是否届满 ───────────────────────────────────

/**
 * 判断弥补期限是否届满
 *
 * 规则：
 * - 一般企业：亏损发生年度的次年起连续 5 年（即 lossYear + maxYears < currentYear 则届满）
 * - 高新技术企业 / 科技型中小企业：maxYears = 10
 *
 * ─── 弥补期限说明 ───
 * 亏损发生在 lossYear 年，弥补截止年度 = lossYear + maxYears。
 * 当 currentYear > lossYear + maxYears 时，弥补期限已届满，
 * 该年度亏损不再确认递延所得税资产。
 * ───────────────────
 *
 * @param lossYear - 亏损发生年度（如2020）
 * @param currentYear - 当前审计年度（如2025）
 * @param maxYears - 最长弥补年限（一般5年，高新/科技型中小企业10年）
 * @returns true=已届满（不可确认），false=未届满（仍可弥补）
 */
export function isCompensationExpired(
  lossYear: number,
  currentYear: number,
  maxYears: number,
): boolean {
  const ly = parseNum(lossYear)
  const cy = parseNum(currentYear)
  const my = parseNum(maxYears)

  // 边界：无效年份或年限
  if (ly <= 0 || cy <= 0 || my <= 0) return true

  return cy > ly + my
}

// ─── 4. 剩余弥补年限 ───────────────────────────────────────

/**
 * 计算剩余弥补年限
 *
 * 公式：剩余年限 = lossYear + maxYears - currentYear
 *
 * 用于 N1-5 检查表展示各年度亏损的剩余可弥补时间。
 * 已届满返回0（不返回负数）。
 *
 * @param lossYear - 亏损发生年度（如2020）
 * @param currentYear - 当前审计年度（如2025）
 * @param maxYears - 最长弥补年限（一般5年，高新/科技型中小企业10年）
 * @returns 剩余弥补年限（≥0）
 */
export function calcRemainingYears(
  lossYear: number,
  currentYear: number,
  maxYears: number,
): number {
  const ly = parseNum(lossYear)
  const cy = parseNum(currentYear)
  const my = parseNum(maxYears)

  if (ly <= 0 || cy <= 0 || my <= 0) return 0

  return Math.max(0, ly + my - cy)
}
