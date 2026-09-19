/**
 * useN1FormulaEngine — N1 递延所得税资产公式引擎（资产类！期末余额）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：1811 递延所得税资产（**借方/资产类科目**）
 *
 * ─── 资产类方向铁律 ───
 * 资产类科目（借方科目）：期末余额 = 期初余额 + 本期借方 - 本期贷方
 * 借增贷减：借方增加资产，贷方减少资产。
 * TB 从 tb_balance 取期末余额（direction=借），**不是发生额**。
 * 与 N2/N3 负债类（贷方，期末=期初+贷-借）、N4/N5 损益类（取发生额）根本不同！
 * ─────────────────────
 *
 * 本引擎覆盖：
 * - 审定数公式链（N1-1 审定表）
 * - 资产类期末余额（期初+借方-贷方）
 * - 合计行（数组求和）
 * - 占比计算（单项/合计）
 * - 变动占比（xlsx K列公式模式）
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/ Task 2.1
 * Requirements: 1.5, 2.3, 2.4, 8.1-8.4
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

// ─── 1. 审定数公式链 ────────────────────────────────────────

/**
 * 计算审定数（Property P1）
 *
 * 审定数 = 未审数 + AJE + RJE
 *
 * 来源：N1-1 审定表
 * 审定数公式在资产/负债/损益类中相同，差异在取数口径。
 *
 * @param unadjusted - 未审数
 * @param aje - 审计调整金额
 * @param rje - 重分类调整金额
 * @returns 审定数
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return parseNum(unadjusted) + parseNum(aje) + parseNum(rje)
}

// ─── 2. 资产类期末余额（期初+借方-贷方！） ─────────────────

/**
 * 计算资产类期末余额（Property P2）
 *
 * ⚠️ 资产类（借方科目）方向：
 *   期末余额 = 期初余额 + 本期借方 - 本期贷方
 *
 * 1811 递延所得税资产为借方科目：借增贷减。
 * 从 tb_balance 取期末余额（direction=借），**不是发生额**。
 * 与 N2/N3 负债类（期末=期初+贷-借）**根本不同！**
 *
 * @param begin - 期初余额
 * @param debit - 本期借方发生额（资产增加）
 * @param credit - 本期贷方发生额（资产减少）
 * @returns 期末余额
 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return parseNum(begin) + parseNum(debit) - parseNum(credit)
}

// ─── 3. 合计行 ──────────────────────────────────────────────

/**
 * 数组求和（Property P5）
 *
 * 用于：
 * - N1-1 审定表按暂时性差异项目合计
 * - N1-2 明细表各列合计行
 * - N1-4 测算表递延税资产/负债合计
 *
 * @param arr - 待求和的金额数组
 * @returns 合计金额
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr)) return 0
  let total = 0
  for (const v of arr) {
    total += parseNum(v)
  }
  return total
}

// ─── 4. 占比计算 ────────────────────────────────────────────

/**
 * 计算单项占合计比例
 *
 * 公式：占比 = item / total
 * 合计为0时返回0（除零保护）。
 *
 * 用于：
 * - N1-2 明细表各项递延税资产占合计比例
 * - N1-4 测算表各暂时性差异项目占比
 *
 * @param item - 单项金额
 * @param total - 合计金额
 * @returns 占比（小数形式，如0.25表示25%）
 */
export function calcProportion(item: number, total: number): number {
  const t = parseNum(total)
  const i = parseNum(item)
  if (t === 0) return 0
  return i / t
}

// ─── 5. 变动占比（xlsx K列公式模式） ────────────────────────

/**
 * 计算变动占比（Change Proportion）
 *
 * 匹配 xlsx K列公式模式：
 *   IF(base=0 AND change=0, 0, IF(base=0 AND change>0, 1, change/base))
 *
 * 逻辑：
 * - 基数=0 且 变动=0 → 0（无变动无意义）
 * - 基数=0 且 变动>0 → 1（从无到有，100%增长）
 * - 其他情况 → change / base
 *
 * 用于：
 * - N1-1 审定表本期变动率
 * - N1-2 明细表期初→期末变动
 *
 * @param change - 变动额（本期-上期，或期末-期初）
 * @param base - 基数（上期/期初金额）
 * @returns 变动占比（小数形式）
 */
export function calcChangeProportion(change: number, base: number): number {
  const c = parseNum(change)
  const b = parseNum(base)
  if (b === 0 && c === 0) return 0
  if (b === 0 && c > 0) return 1
  if (b === 0) return c < 0 ? -1 : 0
  return c / b
}
