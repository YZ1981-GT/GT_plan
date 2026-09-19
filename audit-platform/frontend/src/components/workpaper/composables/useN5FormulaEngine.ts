/**
 * useN5FormulaEngine — N5 所得税费用公式引擎（损益类！取发生额）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：6801 所得税费用（**借方/损益类！**）
 *
 * ─── 损益类方向铁律 ───
 * 损益类科目无"期初期末"概念，只有"本期/上期"发生额对比。
 * 本期发生额 = 借方发生 - 贷方发生（费用为借方科目，借方增加）
 * 与N2负债类（贷方/余额）根本不同！
 * ─────────────────────
 *
 * 本引擎覆盖：
 * - 审定数公式链（N5-1 审定表）
 * - 损益类本期发生额（借方发生 - 贷方发生，从tb_ledger）
 * - 合计行（数组求和）
 * - 有效税率（所得税费用 / 会计利润）
 *
 * 与N4/H10/I6/L8同款（损益类取发生额模式）
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 2.1
 * Requirements: 1.5, 2.3, 2.4, 12.1-12.4
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
 * 来源：N5-1 审定表
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
 * 与 N2 负债类（期末=期初+贷-借）**根本不同！**
 *
 * @param debitOccur - 借方发生额（费用增加）
 * @param creditOccur - 贷方发生额（费用冲回）
 * @returns 本期发生额
 */
export function calcPeriodAmount(debitOccur: number, creditOccur: number): number {
  return parseNum(debitOccur) - parseNum(creditOccur)
}

// ─── 3. 合计行 ──────────────────────────────────────────────

/**
 * 数组求和（合计行 = Σarr）
 *
 * 用于：
 * - N5-1 审定表各费用项合计
 * - N5-5 纳税调整各分类小计
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

// ─── 4. 有效税率 ────────────────────────────────────────────

/**
 * 计算有效税率（所得税费用 / 会计利润）
 *
 * 有效税率 = 所得税费用 / 会计利润
 * 会计利润为0时返回 null 避免除零。
 *
 * 用于：
 * - N5-1 审定表有效税率行
 * - 附注：所得税费用与会计利润调节表
 *
 * @param incomeTax - 所得税费用
 * @param accountingProfit - 会计利润
 * @returns 有效税率（小数），或 null（除零保护）
 */
export function calcEffectiveTaxRate(incomeTax: number, accountingProfit: number): number | null {
  const profit = parseNum(accountingProfit)
  if (profit === 0) return null
  return parseNum(incomeTax) / profit
}
