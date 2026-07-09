/**
 * K13 营业外支出 — 公式引擎（纯函数，无副作用）
 * 科目：6711营业外支出（**损益类/借方科目**）
 * 核心特征：取发生额非余额！支出类发生额 = 借方发生 - 贷方发生(红冲)
 *   - 6711为借方科目：借方=支出增加，贷方=支出冲回/红冲
 *   - 与K12(6301营业外收入贷方)方向相反！
 *     K12: 净额 = 贷方 - 借方（贷方科目，收入增加）
 *     K13: 净额 = 借方 - 贷方（借方科目，支出增加）
 *   - TB回写发生额而非期末余额
 *   - 注意：损益类没有"期末余额"概念，只有发生额！
 * 营业外支出分类：与日常活动无关的损失（非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失等）
 * Spec: .kiro/specs/k13-non-operating-expense/
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
 * CP-K13-01: 审定数 = 未审数 + AJE调整 + RJE重分类
 * 适用：审定表K13-1各营业外支出明细行审定列
 * 公式：audited = unadjusted + AJE + RJE
 * Validates: Requirements 2.3, 6.3
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return parseNum(unadj) + parseNum(aje) + parseNum(rje)
}

/**
 * CP-K13-02: 损益类支出发生额（6711借方科目）
 * 支出类发生额 = 借方发生额 - 贷方发生额（红冲）
 *   - 借方=支出增加（营业外支出确认：非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失等）
 *   - 贷方=支出冲回/红冲（错误冲销或期末结转损益）
 * 重要：取发生额而非期末余额！损益类科目期末余额为0（已结转）
 * 数据来源：tb_ledger明细科目发生额汇总
 *
 * ⚠️ 方向注意：K13是借方科目(debit - credit)，与K12(credit - debit)相反！
 *
 * Validates: Requirements 2.4, 5.1-5.3, 6.4
 */
export function calcIncomeStatementOccurrence(debitOcc: number, creditOcc: number): number {
  return parseNum(debitOcc) - parseNum(creditOcc)
}

/**
 * CP-K13-03: 同比变动率 = (本期 - 上期) / 上期
 * 上期为0时返回null（除零保护，前端显示"—"）
 *
 * @param current 本期发生额
 * @param prior 上期发生额
 * @returns 变动率（小数形式，如0.5表示50%增长）或null
 *
 * Validates: Requirements 6.5
 */
export function calcYoYChange(current: number, prior: number): number | null {
  const p = parseNum(prior)
  if (p === 0) return null
  return (parseNum(current) - p) / p
}

/**
 * CP-K13-04: 占比 = 单项 / 合计
 * 合计为0时返回null（除零保护，前端显示"—"）
 *
 * @param item 单项金额
 * @param total 合计金额
 * @returns 占比（小数形式，如0.25表示25%）或null
 *
 * Validates: Requirements 6.6
 */
export function calcProportion(item: number, total: number): number | null {
  const t = parseNum(total)
  if (t === 0) return null
  return parseNum(item) / t
}

/**
 * CP-K13-05: 合计行求和 = SUM(数组元素)，忽略NaN/null/undefined
 * 空数组返回0；非数组返回0
 * 适用：审定表合计行、明细表分类小计
 *
 * Validates: Requirements 6.7
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}
