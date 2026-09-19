/**
 * useN3DeferredTaxEngine — N3 递延所得税负债核心税务引擎（纯函数，与N1同源）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2901 递延所得税负债（**贷方/负债类科目**）
 *
 * ─── 递延所得税测算逻辑（CAS18） ───
 * 暂时性差异 = 账面价值 - 计税基础
 *   资产项：账面 > 计税基础 → 应纳税暂时性差异 → 递延所得税负债(N3)
 *   负债项：账面 < 计税基础 → 应纳税暂时性差异 → 递延所得税负债(N3)
 *
 * 递延所得税负债 = 应纳税暂时性差异 × 适用税率
 *
 * 不确认递延税负债的特殊项（ADR-4）:
 *   - 商誉初始确认（非企业合并取得资产/负债初始确认时的差异）
 *   - 长期股权投资拟长期持有（投资方能够控制且在可预见的未来不会转回）
 * ────────────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P3: 应纳税暂时性差异 = 账面价值 - 计税基础
 * - P4: 递延所得税负债 = 应纳税暂时性差异 × 适用税率
 * - 加权平均税率 = Σ递延税负债 / Σ应纳税暂时性差异
 * - 带ROUND的递延税负债（匹配xlsx =ROUND(C11*D11, 2)）
 * - 不确认递延税负债的特殊项检测
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/ Task 2.2
 * Requirements: 3.2, 4.1-4.3
 */

// ─── helpers ────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/NaN/空→0
 *
 * @param val - 任意输入值
 * @returns 有效数字，无效时返回0
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 应纳税暂时性差异 ──────────────────────────────────

/**
 * 计算应纳税暂时性差异（Property P3）
 *
 * 应纳税暂时性差异 = 账面价值 - 计税基础
 *
 * 来源：N3-2 明细表列C - 列D
 * xlsx公式对应位置：明细表第5列 = 第3列 - 第4列
 *
 * 业务含义：
 * - 资产项：账面价值 > 计税基础 → 正值 → 应纳税暂时性差异
 * - 负债项：账面价值 < 计税基础时也可产生应纳税差异（但这种情况在N3通常
 *   是账面-计税基础结果为正才确认负债，否则走N1递延税资产）
 *
 * 注意：此处不含方向判断，直接用减法。
 * 正值→应纳税暂时性差异→递延所得税负债(N3)
 * 负值→可抵扣暂时性差异→递延所得税资产(N1)
 *
 * @param bookValue - 账面价值（资产负债表余额）
 * @param taxBase - 计税基础（税法认可的余额）
 * @returns 暂时性差异（正=应纳税，负=可抵扣）
 *
 * @example
 * // 固定资产折旧差异：会计余额800万，税法余额600万
 * calcTaxableTemporaryDifference(8000000, 6000000) // → 2000000（应纳税）
 */
export function calcTaxableTemporaryDifference(bookValue: number, taxBase: number): number {
  return parseNum(bookValue) - parseNum(taxBase)
}

// ─── P4: 递延所得税负债 = 差异 × 税率 ─────────────────────

/**
 * 计算递延所得税负债（Property P4）
 *
 * 递延所得税负债 = 应纳税暂时性差异 × 适用税率
 *
 * 来源：N3-2 明细表列E/列K
 * 注意：此为无ROUND版本（保留完整精度），用于中间计算。
 * 若需匹配xlsx输出精度，使用 calcDeferredTaxLiabilityRounded。
 *
 * @param taxableDiff - 应纳税暂时性差异（通常为正值）
 * @param taxRate - 适用税率（小数形式，如0.25表示25%）
 * @returns 递延所得税负债金额
 *
 * @example
 * // 应纳税差异200万，税率25%
 * calcDeferredTaxLiability(2000000, 0.25) // → 500000
 */
export function calcDeferredTaxLiability(taxableDiff: number, taxRate: number): number {
  return parseNum(taxableDiff) * parseNum(taxRate)
}

// ─── 递延所得税负债（ROUND版，匹配xlsx） ─────────────────────

/**
 * 计算递延所得税负债（ROUND 2位小数，匹配xlsx精度）
 *
 * xlsx公式：=ROUND(C11*D11, 2)
 * - N3-2 明细表列E（期初递延税负债余额）= ROUND(应纳税暂时性差异 × 税率, 2)
 * - N3-2 明细表列K（期末递延税负债余额）= ROUND(应纳税暂时性差异 × 税率, 2)
 *
 * 与 calcDeferredTaxLiability 的区别：
 * - 本函数保留2位小数（匹配xlsx最终输出）
 * - calcDeferredTaxLiability 保留完整精度（适合中间计算/PBT验证）
 *
 * @param taxableDiff - 应纳税暂时性差异
 * @param taxRate - 适用税率（小数形式）
 * @returns 递延所得税负债金额（保留2位小数）
 *
 * @example
 * calcDeferredTaxLiabilityRounded(2000001.555, 0.25) // → 500000.39
 */
export function calcDeferredTaxLiabilityRounded(taxableDiff: number, taxRate: number): number {
  const result = parseNum(taxableDiff) * parseNum(taxRate)
  return Math.round(result * 100) / 100
}

// ─── 加权平均税率 ───────────────────────────────────────────

/**
 * 计算加权平均税率
 *
 * 加权平均税率 = Σ(各项递延所得税负债) / Σ(各项应纳税暂时性差异)
 *
 * 来源：N3-2 明细表底部统计行
 *
 * 当总应纳税暂时性差异为0时返回0（除零保护）。
 * 用于评估被审计单位整体递延所得税负债的实际税率水平。
 *
 * @param taxAmounts - 各项递延所得税负债金额数组
 * @param diffs - 各项应纳税暂时性差异金额数组（与taxAmounts一一对应）
 * @returns 加权平均税率（小数形式，如0.25表示25%）
 *
 * @example
 * // 项目A：差异200万，税负50万；项目B：差异100万，税负15万
 * calcWeightedAvgRate([500000, 150000], [2000000, 1000000])
 * // → (500000+150000) / (2000000+1000000) = 0.2167
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

// ─── 不确认递延税负债的特殊项检测（ADR-4） ───────────────────

/**
 * 不确认递延所得税负债的特殊项目名称（CAS18 准则例外）
 *
 * 1. 商誉初始确认：非企业合并中取得的资产或负债，
 *    交易发生时既不影响会计利润也不影响应纳税所得额，
 *    初始确认的差异不确认递延所得税负债。
 *
 * 2. 长期股权投资拟长期持有：企业对子公司/联营/合营
 *    的投资相关应纳税暂时性差异，在投资方能够控制
 *    暂时性差异转回时间且在可预见的未来不会转回时，
 *    不确认递延所得税负债。
 */
const SPECIAL_NON_RECOGNITION_KEYWORDS: string[] = [
  '商誉初始确认',
  '商誉',
  '长期股权投资拟长期持有',
  '长期股权投资',
  '拟长期持有',
]

/**
 * 检测是否为不确认递延税负债的特殊项（ADR-4）
 *
 * 根据 CAS18 准则例外条款，以下项目不确认递延所得税负债：
 * - 商誉初始确认（非企业合并取得资产/负债初始确认差异）
 * - 长期股权投资拟长期持有（投资方能够控制且在可预见的未来不会转回）
 *
 * 用于 N3-2 明细表中对这些特殊项提供说明标注而不计入测算。
 *
 * @param itemName - 应纳税暂时性差异项目名称
 * @returns true 表示该项为特殊项，不应确认递延所得税负债
 *
 * @example
 * isSpecialNonRecognitionItem('商誉初始确认') // → true
 * isSpecialNonRecognitionItem('固定资产折旧差异') // → false
 * isSpecialNonRecognitionItem('长期股权投资拟长期持有') // → true
 */
export function isSpecialNonRecognitionItem(itemName: string | null | undefined): boolean {
  if (!itemName || typeof itemName !== 'string') return false
  const trimmed = itemName.trim()
  if (!trimmed) return false
  return SPECIAL_NON_RECOGNITION_KEYWORDS.some((keyword) => trimmed.includes(keyword))
}
