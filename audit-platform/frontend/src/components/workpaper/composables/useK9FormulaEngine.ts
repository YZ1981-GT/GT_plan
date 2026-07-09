/**
 * K9 管理费用 — 公式引擎（纯函数，无副作用）
 * 科目：6602管理费用（**损益类/借方科目**）
 * 核心特征：取发生额非余额！费用类发生额 = 借方发生 - 贷方发生(红冲)
 *   - 6602为借方科目：借方=费用增加，贷方=费用冲回/红冲
 *   - 与K8(6601销售费用)/I6(6602研发费用)/H10(6115资产处置损益)同款损益类处理逻辑
 *   - TB回写发生额而非期末余额
 *   - 注意：损益类没有"期末余额"概念，只有发生额！
 * Spec: .kiro/specs/k9-admin-expenses/
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
 * 适用：审定表K9-1各管理费用明细行审定列
 * 公式：audited = unadjusted + AJE + RJE
 * Validates: Requirements 2.3, 9.1
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return parseNum(unadj) + parseNum(aje) + parseNum(rje)
}

/**
 * 损益类费用发生额（6602借方科目）
 * 费用类发生额 = 借方发生额 - 贷方发生额（红冲）
 *   - 借方=费用增加（管理费用支出：职工薪酬/办公费/折旧摊销/中介机构费等）
 *   - 贷方=费用冲回/红冲（期末结转损益）
 * 重要：取发生额而非期末余额！损益类科目期末余额为0（已结转）
 * 数据来源：tb_ledger明细科目发生额汇总
 * Validates: Requirements 2.4, 7.1-7.4, 9.2
 */
export function calcIncomeStatementOccurrence(debitOcc: number, creditOcc: number): number {
  return parseNum(debitOcc) - parseNum(creditOcc)
}

/**
 * 合计行求和 = SUM(数组元素)，忽略NaN/null/undefined
 * 空数组返回0；非数组返回0
 * 适用：审定表合计行、明细表分类小计
 * Validates: Requirements 9.6
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}
