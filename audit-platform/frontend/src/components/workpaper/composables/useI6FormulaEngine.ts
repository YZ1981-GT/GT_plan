/**
 * I6 研发费用 — 公式引擎（纯函数，无副作用）
 * 科目：6602研发费用（**损益类/借方科目**）
 * 核心特征：取发生额非余额！净发生额 = 借方发生 - 贷方发生
 *   - 6602为借方科目：借方=费用增加，贷方=费用冲回/结转
 *   - 与H10(6115资产处置损益)同款处理逻辑
 *   - TB回写发生额而非期末余额
 * I6↔I2双向联动：VR-I6-01 费用化+资本化=研发总额
 * Spec: .kiro/specs/i6-research-development-expense/
 */

/**
 * 安全数字解析：NaN/null/undefined → 0
 * 所有公式函数内部调用以防御非法输入
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const s = String(v).trim()
  if (!s || s === 'NaN') return 0
  const n = Number(s)
  return Number.isFinite(n) ? n : 0
}

/**
 * 审定数 = 未审数 + AJE调整 + RJE重分类
 * 适用：审定表I6-1各行审定列
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return parseNum(unadj) + parseNum(aje) + parseNum(rje)
}

/**
 * 损益类净发生额（6602借方科目）
 * 净发生额 = 借方发生 - 贷方发生
 *   - 借方=费用增加（研发支出）
 *   - 贷方=费用冲回/结转（期末结转损益）
 * 注意：与H10(6115贷方科目)方向相反！
 *   H10: 净额 = 贷方 - 借方（贷方科目，收益增加）
 *   I6:  净额 = 借方 - 贷方（借方科目，费用增加）
 */
export function calcIncomeStatementNet(debit: number, credit: number): number {
  return parseNum(debit) - parseNum(credit)
}

/**
 * 合计行 = SUM(数组元素)
 * 空数组返回0
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}

/**
 * 月度合计 = SUM(1月~12月)
 * 明细表I6-2横向12列汇总
 */
export function calcMonthlyTotal(monthlyAmounts: number[]): number {
  if (!Array.isArray(monthlyAmounts) || monthlyAmounts.length === 0) return 0
  return monthlyAmounts.reduce((sum, v) => sum + parseNum(v), 0)
}

/**
 * 变动率 = (本期 - 同期) / 同期 × 100 (%)
 * 同期为0时返回null（无法计算变动率）
 */
export function calcChangeRate(current: number, prior: number): number | null {
  const p = parseNum(prior)
  if (p === 0) return null
  return ((parseNum(current) - p) / Math.abs(p)) * 100
}

/**
 * 研发总额 = 费用化金额(I6) + 资本化金额(I2)
 * VR-I6-01校验的左侧计算
 */
export function calcResearchTotal(expenseI6: number, capitalizedI2: number): number {
  return parseNum(expenseI6) + parseNum(capitalizedI2)
}

/**
 * VR-I6-01校验：费用化(I6) + 资本化(I2) = 研发总额
 * @returns isValid: 差额绝对值<0.01视为平衡
 * @returns difference: 实际差额（正=超出，负=不足）
 */
export function validateVRI601(
  expenseI6: number,
  capitalizedI2: number,
  expectedTotal: number,
): { isValid: boolean; difference: number } {
  const actual = parseNum(expenseI6) + parseNum(capitalizedI2)
  const expected = parseNum(expectedTotal)
  const difference = actual - expected
  return {
    isValid: Math.abs(difference) < 0.01,
    difference,
  }
}

/**
 * 借贷平衡校验（调整分录I6-3）
 * @returns totalDebit: 借方合计
 * @returns totalCredit: 贷方合计
 * @returns isBalanced: 借贷差额<0.01视为平衡
 */
export function calcDebitCreditBalance(
  debits: number[],
  credits: number[],
): { totalDebit: number; totalCredit: number; isBalanced: boolean } {
  const totalDebit = (Array.isArray(debits) ? debits : []).reduce((s, v) => s + parseNum(v), 0)
  const totalCredit = (Array.isArray(credits) ? credits : []).reduce((s, v) => s + parseNum(v), 0)
  return {
    totalDebit,
    totalCredit,
    isBalanced: Math.abs(totalDebit - totalCredit) < 0.01,
  }
}

/**
 * 截止测试日期差判断（I6-5/I6-6）
 * 判断记账日与单据日之间的天数差是否超过阈值
 * @param bookingDate 记账日期
 * @param documentDate 单据日期
 * @param thresholdDays 阈值天数（默认5天，期末±5天）
 * @returns true=跨期（日期差>阈值），false=未跨期
 */
export function isCutoffCrossover(
  bookingDate: Date,
  documentDate: Date,
  thresholdDays: number = 5,
): boolean {
  if (!(bookingDate instanceof Date) || isNaN(bookingDate.getTime())) return false
  if (!(documentDate instanceof Date) || isNaN(documentDate.getTime())) return false
  const diffMs = Math.abs(bookingDate.getTime() - documentDate.getTime())
  const diffDays = diffMs / (1000 * 60 * 60 * 24)
  return diffDays > thresholdDays
}
