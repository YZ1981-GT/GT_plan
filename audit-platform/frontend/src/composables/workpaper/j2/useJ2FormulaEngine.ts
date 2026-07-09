/**
 * useJ2FormulaEngine — J2 长期应付职工薪酬-设定受益计划 公式引擎（纯函数）
 *
 * 科目：2221长期应付职工薪酬（**贷方/负债类！**）
 * ⚠️ 负债类贷方科目：期末=期初+贷方(增加)-借方(减少)
 * 与 H9 同款方向，与资产类(H1~H8)相反！
 *
 * 核心公式：
 * - 审定数 = 未审数 + AJE + RJE
 * - 负债期末 = 期初 + 贷方发生(增加) - 借方发生(减少)
 * - 变动额 = 本期 - 上期
 * - 变动率 = 变动额 / 基数
 * - 合计 = SUM(数组)
 * - 占比 = 项目金额 / 合计金额
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 2.2-2.6
 */

// ─── 数值解析 ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/空串/NaN/Infinity → 0
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── 审定数公式 ──────────────────────────────────────────────────────────────

/**
 * 审定数 = 未审数 + AJE调整 + RJE重分类
 * Source: J2-1 审定表 审定数列 = 未审数 + 账项调整
 *
 * @param unadj 未审数
 * @param aje AJE调整额
 * @param rje RJE重分类额
 * @returns 审定数
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

// ─── 负债类期末余额 ─────────────────────────────────────────────────────────

/**
 * 负债类期末余额（贷方科目2221）：期末 = 期初 + 贷方发生(增加) - 借方发生(减少)
 * ⚠️ CRITICAL: 负债增加在贷方、减少在借方，与资产类相反！
 *
 * Source: J2-2 明细表 期末=期初+增加-减少
 *         附注(国企) E=B+C-D
 *
 * @param begin 期初余额
 * @param credit 贷方发生额（增加）
 * @param debit 借方发生额（减少）
 * @returns 期末余额
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return begin + credit - debit
}

// ─── 变动分析 ────────────────────────────────────────────────────────────────

/**
 * 变动额 = 本期 - 上期
 * Source: J2-1 H=E-B (本期未审-上期审定)
 */
export function calcChangeAmount(current: number, prior: number): number {
  return current - prior
}

/**
 * 变动率 = 变动额 / 基数
 * 处理基数=0的边界情况（审计实务标准处理）：
 * - 基数=0且当前=0 → 返回 0（无变动）
 * - 基数=0且当前≠0 → 返回 1（视为100%变动）
 *
 * Source: J2-1 I列=IF(AND(B=0,E=0),0,IF(AND(B=0,E>0),1,H/B))
 *
 * @param prior 基数（上期审定数）
 * @param current 本期数
 * @returns 变动率（小数形式，如0.5表示50%）
 */
export function calcChangeRate(prior: number, current: number): number {
  if (prior === 0 && current === 0) return 0
  if (prior === 0) return 1
  return (current - prior) / prior
}

// ─── 合计/小计 ──────────────────────────────────────────────────────────────

/**
 * 合计行 = SUM(数组)
 * Source: J2-1 设定受益计划合计=离职后+其他长期+辞退
 *
 * @param values 数值数组
 * @returns 合计值
 */
export function calcSubtotal(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0)
}

// ─── 占比 ────────────────────────────────────────────────────────────────────

/**
 * 占比 = 项目金额 / 合计金额
 * 合计=0时返回0（避免除零）
 *
 * @param amount 项目金额
 * @param total 合计金额
 * @returns 占比（小数形式）
 */
export function calcProportion(amount: number, total: number): number {
  if (total === 0) return 0
  return amount / total
}
