/**
 * K8 销售费用 — 公式引擎（纯函数，无副作用）
 * 科目：6601销售费用（**损益类/借方科目**）
 * 核心特征：取发生额非余额！费用类发生额 = 借方发生 - 贷方发生(红冲)
 *   - 6601为借方科目：借方=费用增加，贷方=费用冲回/红冲
 *   - 与I6(6602研发费用)/H10(6115资产处置损益)同款损益类处理逻辑
 *   - TB回写发生额而非期末余额
 *   - 注意：损益类没有"期末余额"概念，只有发生额！
 * Spec: .kiro/specs/k8-selling-expenses/
 */

/**
 * 安全数字解析：NaN/null/undefined/Infinity → 0
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
 * 适用：审定表K8-1各费用明细行审定列
 * Validates: Requirements 2.3, 9.1
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return parseNum(unadj) + parseNum(aje) + parseNum(rje)
}

/**
 * 损益类费用发生额（6601借方科目）
 * 费用类发生额 = 借方发生 - 贷方发生（红冲）
 *   - 借方=费用增加（销售费用支出）
 *   - 贷方=费用冲回/红冲（期末结转损益）
 * 注意：与H10(6115贷方科目)方向相反！
 *   H10: 净额 = 贷方 - 借方（贷方科目，收益增加）
 *   K8:  净额 = 借方 - 贷方（借方科目，费用增加）
 * Validates: Requirements 2.4, 7.1-7.4, 9.2
 */
export function calcIncomeStatementOccurrence(debitOcc: number, creditOcc: number): number {
  return parseNum(debitOcc) - parseNum(creditOcc)
}

/**
 * 合计行 = SUM(数组元素)，过滤NaN/null/undefined
 * 空数组返回0
 * Validates: Requirements 9.6
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}

/**
 * 同比变动额 = 本期 - 上期
 * 用于审定表K8-1同比变动列
 */
export function calcYoYChangeAmount(current: number, prior: number): number {
  return parseNum(current) - parseNum(prior)
}
