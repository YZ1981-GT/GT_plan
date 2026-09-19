/**
 * useN1DeferredTaxEngine — N1 递延所得税测算引擎（纯函数，核心）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 复用 useN1FormulaEngine 的 parseNum 做安全数值解析。
 *
 * ─── 递延所得税核心逻辑 ───
 * 暂时性差异 = 账面价值 - 计税基础
 *   资产项: 账面 > 计税基础 → 应纳税暂时性差异 → 递延所得税负债(N3)
 *           账面 < 计税基础 → 可抵扣暂时性差异 → 递延所得税资产(N1)
 * 递延所得税 = 暂时性差异 × 适用税率
 * ──────────────────────────
 *
 * 本引擎覆盖（对应 N1-4 测算表 63×15，21公式）：
 * - 暂时性差异计算（账面-计税基础）
 * - 可抵扣暂时性差异（IF 差异<0 取绝对值，否则0）
 * - 应纳税暂时性差异（IF 差异>0 取差异，否则0）
 * - 递延所得税资产计算（可抵扣差异×税率，含零值保护）
 * - 递延所得税负债计算（应纳税差异×税率，含零值保护）
 * - 应确认与账面差异（shouldBe - actual）
 * - 加权平均税率
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/ Task 2.2
 * Requirements: 3.2, 4.2, 4.3
 */

import { parseNum } from './useN1FormulaEngine'

// ─── 1. 暂时性差异 ──────────────────────────────────────────

/**
 * 计算暂时性差异（Property P3）
 *
 * 暂时性差异 = 账面价值 - 计税基础
 *
 * 结果含义：
 * - 正数（账面 > 计税基础）→ 应纳税暂时性差异（对资产项目）
 * - 负数（账面 < 计税基础）→ 可抵扣暂时性差异（对资产项目）
 * - 0 → 无暂时性差异
 *
 * 来源：N1-4 测算表第一步
 *
 * @param bookValue - 账面价值
 * @param taxBase - 计税基础
 * @returns 暂时性差异（bookValue - taxBase）
 */
export function calcTemporaryDifference(bookValue: number, taxBase: number): number {
  return parseNum(bookValue) - parseNum(taxBase)
}

// ─── 2. 递延所得税 ──────────────────────────────────────────

/**
 * 计算递延所得税（Property P4）
 *
 * 递延所得税 = 暂时性差异 × 适用税率
 *
 * 注：税率应在 [0, 1] 范围内（如25%传0.25）。
 * 本函数不 throw，超范围税率仍按传入值计算。
 * 调用方应在 UI 层对超范围(0~25%)做红色校验提示。
 *
 * 来源：N1-4 测算表核心公式
 *
 * @param tempDiff - 暂时性差异金额
 * @param taxRate - 适用税率（小数，如0.25表示25%）
 * @returns 递延所得税金额
 */
export function calcDeferredTax(tempDiff: number, taxRate: number): number {
  return parseNum(tempDiff) * parseNum(taxRate)
}

// ─── 3. 可抵扣暂时性差异 ────────────────────────────────────

/**
 * 计算可抵扣暂时性差异
 *
 * N1-4 xlsx 公式模式：
 *   IF(账面-计税<0, 计税-账面, 0)
 *   即：差异为负时取绝对值（可抵扣），否则为0
 *
 * 可抵扣暂时性差异 → 确认递延所得税资产(N1)
 *
 * @param bookValue - 账面价值
 * @param taxBase - 计税基础
 * @returns 可抵扣暂时性差异（≥0），无可抵扣时返回0
 */
export function calcDeductibleDiff(bookValue: number, taxBase: number): number {
  const bv = parseNum(bookValue)
  const tb = parseNum(taxBase)
  const diff = bv - tb
  return diff < 0 ? tb - bv : 0
}

// ─── 4. 应纳税暂时性差异 ────────────────────────────────────

/**
 * 计算应纳税暂时性差异
 *
 * N1-4 xlsx 公式模式：
 *   IF(账面-计税>0, 账面-计税, 0)
 *   即：差异为正时取差异（应纳税），否则为0
 *
 * 应纳税暂时性差异 → 确认递延所得税负债(N3)
 *
 * @param bookValue - 账面价值
 * @param taxBase - 计税基础
 * @returns 应纳税暂时性差异（≥0），无应纳税时返回0
 */
export function calcTaxableDiff(bookValue: number, taxBase: number): number {
  const bv = parseNum(bookValue)
  const tb = parseNum(taxBase)
  const diff = bv - tb
  return diff > 0 ? diff : 0
}

// ─── 5. 递延所得税资产（含零值保护） ────────────────────────

/**
 * 计算递延所得税资产
 *
 * N1-4 xlsx 公式模式：
 *   IF(可抵扣差异=0, 0, 可抵扣差异×适用税率)
 *
 * 零值保护：可抵扣差异为0时直接返回0，避免浮点噪声。
 *
 * @param deductibleDiff - 可抵扣暂时性差异（来自 calcDeductibleDiff）
 * @param taxRate - 适用税率（小数，如0.25）
 * @returns 递延所得税资产金额（≥0）
 */
export function calcDeferredTaxAsset(deductibleDiff: number, taxRate: number): number {
  const diff = parseNum(deductibleDiff)
  if (diff === 0) return 0
  return diff * parseNum(taxRate)
}

// ─── 6. 递延所得税负债（含零值保护） ────────────────────────

/**
 * 计算递延所得税负债
 *
 * N1-4 xlsx 公式模式：
 *   IF(应纳税差异=0, 0, 应纳税差异×适用税率)
 *
 * 零值保护：应纳税差异为0时直接返回0，避免浮点噪声。
 * 负债部分联动 N3 递延所得税负债底稿。
 *
 * @param taxableDiff - 应纳税暂时性差异（来自 calcTaxableDiff）
 * @param taxRate - 适用税率（小数，如0.25）
 * @returns 递延所得税负债金额（≥0）
 */
export function calcDeferredTaxLiability(taxableDiff: number, taxRate: number): number {
  const diff = parseNum(taxableDiff)
  if (diff === 0) return 0
  return diff * parseNum(taxRate)
}

// ─── 7. 应确认与账面差异 ────────────────────────────────────

/**
 * 计算递延所得税应确认与账面的差异
 *
 * 应确认差异 = 应确认金额(shouldBe) - 实际账面金额(actual)
 *
 * 用于：
 * - N1-4 测算表"应调整"列：测算应确认递延税资产 vs 当前账面
 * - 正数 → 需追加确认；负数 → 需转回
 *
 * @param shouldBe - 应确认递延所得税金额（测算结果）
 * @param actual - 实际账面递延所得税金额
 * @returns 差异（正=应追加确认，负=应转回）
 */
export function calcDeferredTaxDiff(shouldBe: number, actual: number): number {
  return parseNum(shouldBe) - parseNum(actual)
}

// ─── 8. 加权平均税率 ────────────────────────────────────────

/**
 * 计算加权平均税率
 *
 * 加权平均税率 = Σ(各项递延税金额) / Σ(各项暂时性差异)
 *
 * 用于：
 * - N1-2 明细表底部"加权平均税率"统计
 * - N1-4 测算表汇总行加权税率
 *
 * 当暂时性差异合计为0时返回0（除零保护）。
 *
 * @param taxAmounts - 各项递延所得税金额数组
 * @param diffs - 各项暂时性差异金额数组（与taxAmounts一一对应）
 * @returns 加权平均税率（小数形式，如0.25表示25%）
 */
export function calcWeightedAvgRate(taxAmounts: number[], diffs: number[]): number {
  if (!Array.isArray(taxAmounts) || !Array.isArray(diffs)) return 0
  let totalTax = 0
  let totalDiff = 0
  for (const t of taxAmounts) {
    totalTax += parseNum(t)
  }
  for (const d of diffs) {
    totalDiff += parseNum(d)
  }
  if (totalDiff === 0) return 0
  return totalTax / totalDiff
}
