/**
 * useJ1FormulaEngine — J1 应付职工薪酬 公式引擎（纯函数）
 *
 * 科目：2211应付职工薪酬（**贷方/负债类！**）
 * ⚠️ 负债类贷方科目：期末=期初+贷方(增加)-借方(减少)
 * 与 H9 同款方向，与资产类(H1~H8)相反！
 *
 * 核心公式：
 * - 审定数 = 未审数 + AJE + RJE
 * - 负债期末 = 期初 + 贷方发生(增加) - 借方发生(减少)
 * - 变动额 = 本期 - 上期
 * - 变动率 = 变动额 / 基数（基数=0特殊处理）
 * - 合计 = SUM(数组)
 * - 占比 = 项目金额 / 合计金额
 * - 月度合计 = SUM(1月~12月)
 * - 月度均值 = 月度合计 / 12
 * - 分配闭合 = Σ各费用科目分配 === 薪酬总额
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 2.2-2.6, 3.2-3.6, 4.3-4.4
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
 * Source: J1-1 审定表 G8=E8+F8（审定=未审+调整）
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
 * 负债类期末余额（贷方科目2211）：期末 = 期初 + 贷方发生(增加) - 借方发生(减少)
 * ⚠️ CRITICAL: 负债增加在贷方、减少在借方，与资产类相反！
 *
 * Source: J1-2 明细表 F14=C14+D14-E14（期末=期初+增加-减少）
 *         附注(国企) E9=B9+C9-D9
 *
 * @param begin 期初余额
 * @param credit 贷方发生额（增加/计提）
 * @param debit 借方发生额（减少/发放）
 * @returns 期末余额
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return begin + credit - debit
}

// ─── 变动分析 ────────────────────────────────────────────────────────────────

/**
 * 变动额 = 本期 - 上期
 * Source: J1-1 H8=E8-B8
 */
export function calcChangeDiff(current: number, prior: number): number {
  return current - prior
}

/**
 * 变动率 = 变动额 / 基数 × 100
 * 处理基数=0的边界情况（审计实务标准处理）：
 * - 基数=0且当前=0 → 返回 0（无变动）
 * - 基数=0且当前≠0 → 返回 100（视为100%变动）
 *
 * Source: J1-1 I8=IF(AND(B8=0,E8=0),0,IF(AND(B8=0,E8>0),1,H8/B8))
 * 注意：源表返回小数(1=100%)，此处返回百分比数值以便显示
 *
 * @param current 本期数
 * @param prior 基数（上期数）
 * @returns 变动率百分比（如 50 表示 50%），基数=0时返回 0 或 100
 */
export function calcChangeRate(current: number, prior: number): number {
  if (prior === 0 && current === 0) return 0
  if (prior === 0) return 100
  return ((current - prior) / prior) * 100
}

// ─── 合计/小计 ──────────────────────────────────────────────────────────────

/**
 * 合计行 = SUM(数组)
 * Source: J1-1 各分类小计=SUM(明细项)
 *         J1-2 C13=SUM(C14:C18)
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
 * @returns 占比（小数形式，如 0.25 表示 25%）
 */
export function calcProportion(amount: number, total: number): number {
  if (total === 0) return 0
  return amount / total
}

// ─── 月度分析 ────────────────────────────────────────────────────────────────

/**
 * 月度合计 = SUM(1月~12月)
 * Source: J1-4 月度分析表 各行合计列=SUM(B:M) 12个月
 *
 * @param months 12个月份数值数组
 * @returns 月度合计
 */
export function calcMonthlyTotal(months: number[]): number {
  return months.reduce((sum, v) => sum + v, 0)
}

/**
 * 月度均值 = 月度合计 / 有效月数
 * 有效月数=数组长度（正常应为12，支持不足12月的场景）
 *
 * @param months 月份数值数组
 * @returns 月度均值，空数组返回0
 */
export function calcMonthlyAverage(months: number[]): number {
  if (months.length === 0) return 0
  return calcMonthlyTotal(months) / months.length
}

// ─── 分配闭合校验 ────────────────────────────────────────────────────────────

/**
 * 分配闭合校验：各费用科目分配之和 === 薪酬总额
 *
 * 审计逻辑：J1-7分配检查核验 管理费用+销售费用+生产成本+制造费用+研发费用+在建工程 = 明细表贷方增加
 * 允许精度误差 0.01 元（浮点精度）
 *
 * Source: J1-7 分配情况检查表 列合计校验
 *
 * @param allocated 各费用科目分配金额数组
 * @param total 应分配总额（薪酬贷方增加合计）
 * @returns { isValid: 是否闭合, difference: 差额 }
 */
export function validateAllocationClosure(
  allocated: number[],
  total: number,
): { isValid: boolean; difference: number } {
  const allocatedTotal = allocated.reduce((sum, v) => sum + v, 0)
  const difference = allocatedTotal - total
  return {
    isValid: Math.abs(difference) < 0.01,
    difference,
  }
}

// ─── Re-exports from useJ1SalaryCalc (backward compatibility) ────────────────

export { calcIndustryDiffRate, calcPerCapitaSalary, calcSalaryRevenueRatio } from './useJ1SalaryCalc'
