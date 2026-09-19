/**
 * useN4FormulaEngine — N4 税金及附加公式引擎（损益类！取发生额）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：6403 税金及附加（**借方/损益类！**）
 *
 * ─── 损益类方向铁律 ───
 * 损益类科目无"期初期末"概念，只有"本期/上期"发生额对比。
 * 本期发生额 = 借方发生 - 贷方发生（费用为借方科目，借方增加）
 * 与N2负债类（贷方/余额）根本不同！
 * ─────────────────────
 *
 * 本引擎覆盖：
 * - 审定数公式链（N4-1 审定表）
 * - 损益类本期发生额（借方发生 - 贷方发生，从tb_ledger）
 * - 合计行（数组求和）
 * - 同比变动率（(本期-上期)/上期）
 *
 * 与N5所得税费用/H10资产处置损益/I6研发费用/K8~K13同款（损益类取发生额模式）
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/ Task 2.1
 * Requirements: 1.5, 2.3, 2.4, 7.1-7.4
 *
 * Correctness Properties:
 * CP-N4-P1: calcAuditedAmount(u, a, r) === u + a + r
 * CP-N4-P2: calcPeriodAmount(debitOccur, creditOccur) === debitOccur - creditOccur
 * CP-N4-P3: calcSubtotal(arr) === Σarr
 * CP-N4-P4: calcYoyChange(cur, prior) === (cur - prior) / prior (prior≠0)
 */

// ─── helpers ────────────────────────────────────────────────

/** 安全数值解析：null/undefined/NaN/空/Infinity → 0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── 1. 审定数公式链 ────────────────────────────────────────

/**
 * CP-N4-P1: 计算审定数
 * 审定数 = 未审数 + AJE + RJE
 *
 * 来源：N4-1 审定表各税种行审定列
 * 损益类审定公式与资产/负债类相同，差异在取数口径（发生额 vs 余额）。
 *
 * @param unadjusted - 未审数（本期发生额）
 * @param aje - 审计调整金额
 * @param rje - 重分类调整金额
 * @returns 审定数
 *
 * Validates: Requirements 2.3, 7.3
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return parseNum(unadjusted) + parseNum(aje) + parseNum(rje)
}

// ─── 2. 损益类本期发生额（借方-贷方！） ─────────────────────

/**
 * CP-N4-P2: 计算损益类本期发生额
 *
 * ⚠️ 损益类（借方科目/费用类）方向：
 *   本期发生额 = 借方发生 - 贷方发生
 *
 * 费用为借方科目：借方增加（费用发生），贷方减少（费用冲回）
 * 从 tb_ledger 取本期借贷发生额，**不是期末余额**。
 * 与 N2 负债类（期末=期初+贷-借）**根本不同！**
 *
 * 科目6403税金及附加：消费税/城建税/教育费附加/房产税/印花税/土地使用税等
 * 数据来源：tb_ledger 明细科目发生额汇总
 *
 * @param debitOccur - 借方发生额（费用增加）
 * @param creditOccur - 贷方发生额（费用冲回）
 * @returns 本期发生额
 *
 * Validates: Requirements 2.4, 7.1, 7.2
 */
export function calcPeriodAmount(debitOccur: number, creditOccur: number): number {
  return parseNum(debitOccur) - parseNum(creditOccur)
}

// ─── 3. 合计行 ──────────────────────────────────────────────

/**
 * CP-N4-P3: 数组求和（合计行 = Σarr）
 *
 * 用于：
 * - N4-1 审定表各税种合计
 * - N4-2 明细表分类小计
 * - 各列合计行
 *
 * 空数组返回0；非数组返回0。
 *
 * @param arr - 待求和的金额数组
 * @returns 合计金额
 *
 * Validates: Requirements 7.4
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}

// ─── 4. 同比变动率 ──────────────────────────────────────────

/**
 * CP-N4-P4: 同比变动 = (本期 - 上期) / 上期
 * 上期为0时返回 null（除零保护，前端显示"—"）
 *
 * 用于：
 * - N4-1 审定表同比变动列
 * - N4-2 明细表各税种同比变动
 * - 附注：各税种本期/上期对比
 *
 * @param current - 本期发生额
 * @param prior - 上期发生额
 * @returns 变动率（小数形式，如0.5表示50%增长），或 null（上期为0除零保护）
 *
 * Validates: Requirements 1.5, 7.4
 */
export function calcYoyChange(current: number, prior: number): number | null {
  const p = parseNum(prior)
  if (p === 0) return null
  return (parseNum(current) - p) / p
}
