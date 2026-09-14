/**
 * useL8FormulaEngine — L8 财务费用公式引擎（损益类！取发生额）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：6603 财务费用（**借方/损益类！**）
 *
 * ─── 损益类方向铁律 ───
 * 损益类科目无"期初期末"概念，只有"本期/上期"发生额对比。
 * 本期发生额 = 借方发生 - 贷方发生（费用为借方科目，借方增加）
 * 与L1~L7负债类（贷方/余额）根本不同！
 * ─────────────────────
 *
 * 本引擎覆盖：
 * - 审定数公式链（L8-1 审定表）
 * - 损益类本期发生额（借方发生 - 贷方发生）
 * - 净财务费用（利息支出-利息收入+汇兑+手续费+其他）
 * - 变动率（百分比）
 * - 分类小计（数组求和）
 *
 * Spec: .kiro/specs/l8-financial-expenses/ Task 2.1
 * Requirements: 2.3-2.4, 3.2-3.3, 8.1-8.4
 */

// ─── helpers ────────────────────────────────────────────────

/** 安全数值解析：null/undefined/NaN/空→0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── 1. 审定数公式链 ────────────────────────────────────────

/**
 * 计算审定数（Property P1）
 * 审定数 = 未审数 + AJE + RJE
 *
 * 来源：L8-1 审定表
 * 损益类审定公式与资产/负债类相同，差异在取数口径（发生额 vs 余额）。
 *
 * @param unadjusted - 未审数（本期发生额）
 * @param aje - 审计调整金额
 * @param rje - 重分类调整金额
 * @returns 审定数
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return parseNum(unadjusted) + parseNum(aje) + parseNum(rje)
}

// ─── 2. 损益类本期发生额（借方-贷方！） ─────────────────────

/**
 * 计算损益类本期发生额（Property P2）
 *
 * ⚠️ 损益类（借方科目/费用类）方向：
 *   本期发生额 = 借方发生 - 贷方发生
 *
 * 费用为借方科目：借方增加（费用发生），贷方减少（费用冲回）
 * 从 tb_ledger 取本期借贷发生额，**不是期末余额**。
 * 与 L1~L7 负债类（期末=期初+贷-借）**根本不同！**
 *
 * @param debitOccur - 借方发生额（费用增加）
 * @param creditOccur - 贷方发生额（费用冲回）
 * @returns 本期发生额
 */
export function calcOccurrence(debitOccur: number, creditOccur: number): number {
  return parseNum(debitOccur) - parseNum(creditOccur)
}

// ─── 3. 净财务费用 ──────────────────────────────────────────

/**
 * 计算净财务费用（Property P3）
 *
 * 净财务费用 = 利息支出 - 利息收入 + 汇兑损益 + 手续费 + 其他
 *
 * 来源：L8-2 明细表
 * 利息收入为减项（冲抵费用），其余为加项。
 *
 * @param interestExp - 利息支出
 * @param interestInc - 利息收入（减项）
 * @param fx - 汇兑损益
 * @param fee - 手续费
 * @param other - 其他
 * @returns 净财务费用
 */
export function calcNetFinanceExpense(
  interestExp: number,
  interestInc: number,
  fx: number,
  fee: number,
  other: number,
): number {
  return parseNum(interestExp) - parseNum(interestInc) + parseNum(fx) + parseNum(fee) + parseNum(other)
}

// ─── 4. 变动率 ──────────────────────────────────────────────

/**
 * 计算变动率（Property P4）
 *
 * 公式：变动率 = (本期 - 上期) / 上期 × 100
 * 上期=0时返回 'N/A'（除零保护）
 *
 * 返回百分比数值（如20表示20%）。
 *
 * @param current - 本期发生额
 * @param prior - 上期发生额
 * @returns 变动率百分比，或 'N/A'（上期为0时）
 */
export function calcChangeRate(current: number, prior: number): number | 'N/A' {
  const p = parseNum(prior)
  const c = parseNum(current)
  if (p === 0) return 'N/A'
  return ((c - p) / p) * 100
}

// ─── 5. 分类小计 ────────────────────────────────────────────

/**
 * 数组求和（按项目/分类汇总）
 *
 * 用于：
 * - L8-1 审定表按费用明细分类合计
 * - L8-2 明细表列小计
 * - 各列合计行
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

// ─── 6. 变动额 ──────────────────────────────────────────────

/**
 * 计算变动额
 * 变动额 = 本期 - 上期
 *
 * @param current - 本期发生额
 * @param prior - 上期发生额
 * @returns 变动额
 */
export function calcChangeAmount(current: number, prior: number): number {
  return parseNum(current) - parseNum(prior)
}

// ─── 7. 变动率是否超阈值 ────────────────────────────────────

/**
 * 判断变动率是否超过阈值
 *
 * @param rate - calcChangeRate 返回值
 * @param threshold - 阈值（百分比，如20表示20%）
 * @returns 是否超阈值
 */
export function isChangeRateExceeding(rate: number | 'N/A', threshold: number): boolean {
  if (rate === 'N/A') return false
  return Math.abs(rate) > threshold
}

// ─── 8. 跨sheet交叉验证 ────────────────────────────────────

/**
 * 审定表 vs 明细表合计交叉验证
 *
 * 比对审定表审定合计与明细表各项目发生额之和，
 * 差额为0表示勾稽一致。
 *
 * @param adjTotal - 审定表合计金额
 * @param detailTotal - 明细表各项目发生额之和
 * @returns { diff: 差额, isMatch: 是否一致 }
 */
export function validateAdjudicationVsDetail(
  adjTotal: number,
  detailTotal: number,
): { diff: number; isMatch: boolean } {
  const d = parseNum(adjTotal) - parseNum(detailTotal)
  return { diff: d, isMatch: Math.abs(d) < 0.01 }
}
