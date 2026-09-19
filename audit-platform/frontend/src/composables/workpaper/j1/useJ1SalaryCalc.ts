/**
 * useJ1SalaryCalc — J1 应付职工薪酬 薪酬测算纯函数引擎
 *
 * 核心测算公式（J1-6 计提情况检查表）：
 * - 工资测算 = 人数 × 月均薪酬 × 月数
 * - 社保测算 = 缴费基数 × 缴纳比例 × 月数
 * - 住房公积金 = 缴费基数 × 缴纳比例 × 月数
 * - 计提差异率 = (实提 - 应提) / 应提
 * - 人均薪酬 = 薪酬总额 / 人数
 * - 薪酬占收入比 = 薪酬总额 / 营业收入
 * - 行业差异率 = (公司值 - 行业均值) / 行业均值
 *
 * 所有函数为纯函数，无副作用，便于 PBT 验证数学正确性。
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 4.6, 5.2-5.4, 6.2-6.5
 */

// ─── 工资测算 ────────────────────────────────────────────────────────────────

/**
 * 工资测算 = 人数 × 月均薪酬 × 月数
 *
 * 审计逻辑：根据期末在职人数、平均薪酬和计提月数，估算应计提工资总额。
 * 与实际计提金额对比，判断薪酬计提完整性/准确性。
 *
 * Source: J1-6 计提检查 应提金额=人数×月均薪×月数
 *
 * @param headcount 期末在职人数（正整数）
 * @param avgSalary 月均薪酬（元）
 * @param months 计提月数（1~12）
 * @returns 估算工资总额
 */
export function calcSalaryEstimate(headcount: number, avgSalary: number, months: number): number {
  return headcount * avgSalary * months
}

// ─── 社保测算 ────────────────────────────────────────────────────────────────

/**
 * 社保测算 = 缴费基数 × 缴纳比例 × 月数
 *
 * 审计逻辑：按社保局核定基数和当地比例（养老16%/医疗8%/失业0.5%/工伤0.4%/生育0.8%），
 * 估算应计提社保金额，与实际计提对比。
 *
 * Source: J1-6 计提检查 社保应提=基数×比例×月数
 *
 * @param base 缴费基数（通常=人数×平均基数或单位月缴费基数合计）
 * @param rate 缴纳比例（小数形式，如0.16表示16%养老险单位部分）
 * @param months 缴纳月数（1~12）
 * @returns 估算社保金额
 */
export function calcInsuranceEstimate(base: number, rate: number, months: number): number {
  return base * rate * months
}

// ─── 住房公积金测算 ──────────────────────────────────────────────────────────

/**
 * 住房公积金测算 = 缴费基数 × 缴纳比例 × 月数
 *
 * 审计逻辑：住房公积金单位缴纳比例5%~12%，按缴费基数和月数估算。
 *
 * Source: J1-6 计提检查 公积金应提=基数×比例×月数
 *
 * @param base 缴费基数
 * @param rate 缴纳比例（小数形式，如0.12表示12%）
 * @param months 缴纳月数
 * @returns 估算住房公积金
 */
export function calcHousingFundEstimate(base: number, rate: number, months: number): number {
  return base * rate * months
}

// ─── 计提差异率 ──────────────────────────────────────────────────────────────

/**
 * 计提差异率 = (实际计提 - 应计提) / 应计提 × 100
 *
 * 审计关注：差异率超过5%应进一步调查原因。
 * 正值=多提（可能虚增费用）；负值=少提（可能低估负债）。
 *
 * @param actual 实际计提金额
 * @param estimated 应计提金额（测算数）
 * @returns 差异率百分比（如 3.5 表示 3.5%），估算为0时返回null
 */
export function calcAccrualDiffRate(actual: number, estimated: number): number | null {
  if (estimated === 0) return null
  return ((actual - estimated) / estimated) * 100
}

// ─── 人均薪酬 ────────────────────────────────────────────────────────────────

/**
 * 人均薪酬 = 薪酬总额 / 期末人数
 *
 * 审计逻辑：与上年、行业数据对比判断合理性。
 *
 * @param totalSalary 薪酬总额
 * @param headcount 期末在职人数
 * @returns 人均薪酬，人数=0时返回null
 */
export function calcPerCapitaSalary(totalSalary: number, headcount: number): number | null {
  if (headcount === 0) return null
  return totalSalary / headcount
}

// ─── 薪酬占收入比 ────────────────────────────────────────────────────────────

/**
 * 薪酬占收入比 = 薪酬总额 / 营业收入 × 100
 *
 * 审计逻辑：薪酬强度指标，与行业数据对比判断合理性。
 * 制造业通常10~20%；服务业通常30~50%；科技行业通常40~60%。
 *
 * @param totalSalary 薪酬总额
 * @param revenue 营业收入
 * @returns 薪酬占比百分比，收入=0时返回null
 */
export function calcSalaryRevenueRatio(totalSalary: number, revenue: number): number | null {
  if (revenue === 0) return null
  return (totalSalary / revenue) * 100
}

// ─── 行业差异率 ──────────────────────────────────────────────────────────────

/**
 * 行业差异率 = (公司值 - 行业均值) / 行业均值 × 100
 *
 * Source: J1-5 同行业对比分析表 差异率列
 *
 * @param company 公司数据（如人均薪酬/薪酬占比）
 * @param industryAvg 行业平均值
 * @returns 差异率百分比，行业均值=0时返回null
 */
export function calcIndustryDiffRate(company: number, industryAvg: number): number | null {
  if (industryAvg === 0) return null
  return ((company - industryAvg) / industryAvg) * 100
}
