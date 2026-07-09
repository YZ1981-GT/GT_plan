/**
 * useL4FormulaEngine — L4 应付债券公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2502 应付债券（**贷方/负债类！**）
 *
 * ─── 负债类方向铁律 ───
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生（发行/利息调整增加） - 借方发生（兑付/减少）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 * 这是 L 筹资循环 L1~L7 所有底稿的共同规则。
 * ─────────────────────
 *
 * 本引擎覆盖：
 * - 审定数公式链（L4-1 审定表）
 * - 负债类期末余额（贷方科目方向）
 * - 初始计量（L4-6：发行价-交易费用、溢折价）
 * - 分类小计（数组求和）
 */

// ─── 1. 审定数公式链 ────────────────────────────────────────

/**
 * 计算审定数
 * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
 *
 * 来源：L4-1 审定表（应付债券审定）
 * 与 L3 长期借款相同公式，L 循环统一。
 *
 * @param unadjusted - 未审数（trial_balance.unadjusted_amount）
 * @param aje - 审计调整金额（正=调增，负=调减）
 * @param rje - 重分类调整金额
 * @returns 审定数
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

// ─── 2. 负债类期末余额（贷方！） ─────────────────────────────

/**
 * 计算负债类科目期末余额
 *
 * ⚠️ 负债类（贷方科目）方向：
 *   期末 = 期初 + 贷方发生额（发行/利息调整增加） - 借方发生额（兑付/减少）
 *
 * 来源：L4-1 审定表 + L4-2 明细表
 * 应付债券贷方增加场景：新发行债券、溢价摊销（利息调整贷方）
 * 应付债券借方减少场景：到期兑付、提前赎回
 *
 * 与资产类相反！资产类期末 = 期初 + 借方 - 贷方
 * 此为 L 循环（短期借款/长期借款/应付债券等）共用铁律。
 *
 * @param beginning - 期初余额
 * @param credit - 贷方发生额（发行/利息调整增加）
 * @param debit - 借方发生额（兑付/减少）
 * @returns 期末余额
 */
export function calcLiabilityEndBalance(beginning: number, credit: number, debit: number): number {
  return beginning + credit - debit
}

// ─── 3. 初始计量（L4-6） ────────────────────────────────────

/**
 * 计算初始入账金额
 * 初始入账金额 = 发行价格 - 交易费用
 *
 * 来源：L4-6 初始计量表
 * 依据 CAS 22：金融负债初始确认按公允价值（发行价格）减去直接归属交易费用。
 * 该金额即为债券初始摊余成本，后续通过实际利率法进行摊销。
 *
 * @param issuePrice - 发行价格（实际收到的发行对价）
 * @param transactionCost - 交易费用（承销费、律师费等直接归属费用）
 * @returns 初始入账金额（初始摊余成本）
 */
export function calcInitialAmount(issuePrice: number, transactionCost: number): number {
  return issuePrice - transactionCost
}

/**
 * 计算溢折价
 * 溢折价 = 初始入账金额 - 面值
 *
 * 来源：L4-6 初始计量表
 * - 正值（>0）：溢价发行（发行价>面值，票面利率>市场利率）
 * - 负值（<0）：折价发行（发行价<面值，票面利率<市场利率）
 * - 零值（=0）：平价发行
 *
 * 溢折价将在债券存续期内通过实际利率法逐期摊销。
 *
 * @param initialAmount - 初始入账金额（= 发行价格 - 交易费用）
 * @param faceValue - 债券面值
 * @returns 溢折价（正=溢价，负=折价，0=平价）
 */
export function calcPremiumDiscount(initialAmount: number, faceValue: number): number {
  return initialAmount - faceValue
}

// ─── 4. 分类小计 ────────────────────────────────────────────

/**
 * 数组求和（按品种/类型汇总）
 *
 * 用于：
 * - L4-1 审定表按债券品种分类小计
 * - L4-2 明细表按付息方式汇总
 * - L4-6 初始计量合计
 *
 * @param arr - 待求和的金额数组
 * @returns 合计金额
 */
export function calcSubtotal(arr: number[]): number {
  let total = 0
  for (const a of arr) {
    total += a
  }
  return total
}
