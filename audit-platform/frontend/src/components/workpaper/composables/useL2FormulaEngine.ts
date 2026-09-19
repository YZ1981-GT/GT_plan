/**
 * useL2FormulaEngine — L2 应付利息公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2231 应付利息（**贷方/负债类！**）
 *
 * ─── 负债类方向铁律 ───
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生（计提）- 借方发生（支付）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 * 这是 L 筹资循环 L1~L7 所有底稿的共同规则。
 * ─────────────────────
 */

// ─── 1. 审定数公式链 ────────────────────────────────────────

/**
 * 计算审定数
 * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
 *
 * Property P1: ∀ u,a,r: calcAuditedAmount = u + a + r
 * **Validates: Requirements 2.3**
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
 *   期末 = 期初 + 贷方发生额（计提/增加） - 借方发生额（支付/减少）
 *
 * 与资产类相反！资产类期末 = 期初 + 借方 - 贷方
 * 此为 L 循环（短期借款/长期借款/应付债券/应付利息等）共用铁律。
 *
 * Property P2: ∀ b,cr,dr: calcLiabilityEndBalance = b + cr - dr
 * **Validates: Requirements 2.4**
 *
 * @param beginning - 期初余额
 * @param credit - 贷方发生额（计提/增加）
 * @param debit - 借方发生额（支付/减少）
 * @returns 期末余额
 */
export function calcLiabilityEndBalance(beginning: number, credit: number, debit: number): number {
  return beginning + credit - debit
}

// ─── 3. 分类小计 ────────────────────────────────────────────

/**
 * 按分类汇总金额（如按来源：短期借款利息/长期借款利息/应付债券利息分类小计）
 *
 * Property P4: ∀ arr: calcSubtotal = Σarr
 * **Validates: Requirements 2.3**
 *
 * @param amounts - 待求和的金额数组
 * @returns 合计金额
 */
export function calcSubtotal(amounts: number[]): number {
  let total = 0
  for (const a of amounts) {
    total += a
  }
  return total
}

// ─── Composable 导出 ────────────────────────────────────────

/**
 * L2 应付利息公式引擎 composable 包装
 * 提供纯函数分组导出，方便 Vue 组件中统一引用
 */
export function useL2FormulaEngine() {
  return {
    calcAuditedAmount,
    calcLiabilityEndBalance,
    calcSubtotal,
  }
}
