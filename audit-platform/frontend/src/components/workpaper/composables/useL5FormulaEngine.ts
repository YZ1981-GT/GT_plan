/**
 * useL5FormulaEngine — L5 长期应付款公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2701 长期应付款（**贷方/负债类！**）+ 未确认融资费用（借方/负债备抵类）
 *
 * ─── 负债类方向铁律 ───
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生（借入/增加） - 借方发生（归还/减少）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 * 这是 L 筹资循环 L1~L7 所有底稿的共同规则。
 * ─────────────────────
 *
 * ─── 备抵类方向 ───
 * 未确认融资费用是负债备抵科目（借方科目），用于冲减长期应付款面值：
 * 备抵类期末 = 期初 + 借方发生（新增未确认）- 贷方发生（摊销冲减）
 * 净额 = 长期应付款 - 未确认融资费用
 * ──────────────────
 *
 * 本引擎覆盖：
 * - 审定数公式链（L5-1 审定表）
 * - 负债类期末余额（L5-2 长期应付款明细，贷方科目方向）
 * - 备抵类期末余额（L5-3 未确认融资费用明细，借方备抵方向）
 * - 净额计算（长期应付款 - 未确认融资费用）
 * - 分类小计（数组求和）
 */

// ─── 1. 审定数公式链 ────────────────────────────────────────

/**
 * 计算审定数
 * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
 *
 * 来源：L5-1 审定表 E8=B8+C8+D8
 * 与 L3/L4 相同公式，L 循环统一。
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
 * 计算负债类科目期末余额（L5-2 长期应付款明细表）
 *
 * ⚠️ 负债类（贷方科目）方向：
 *   期末 = 期初 + 贷方发生额（新增应付）- 借方发生额（偿还/减少）
 *
 * 来源：L5-2 明细表 E11=B11-C11+D11（期末=期初-借方+贷方，即 期初+贷方-借方）
 * 长期应付款贷方增加场景：新增融资租赁应付款、分期付款购置资产等
 * 长期应付款借方减少场景：到期偿付、提前清偿
 *
 * 与资产类相反！资产类期末 = 期初 + 借方 - 贷方
 * 此为 L 循环（短期借款/长期借款/应付债券/长期应付款）共用铁律。
 *
 * @param beginning - 期初余额
 * @param credit - 贷方发生额（新增应付/增加）
 * @param debit - 借方发生额（偿还/减少）
 * @returns 期末余额
 */
export function calcLiabilityEndBalance(beginning: number, credit: number, debit: number): number {
  return beginning + credit - debit
}

// ─── 3. 备抵类期末余额（未确认融资费用，借方！） ──────────────

/**
 * 计算备抵类科目期末余额（L5-3 未确认融资费用明细）
 *
 * ⚠️ 备抵类（借方科目，冲减负债面值）方向：
 *   期末 = 期初 + 借方发生额（新增未确认）- 贷方发生额（摊销冲减）
 *
 * 来源：design.md P3 定义 + tasks.md PBT断言
 * 未确认融资费用借方增加场景：初始确认新的融资租赁/分期付款时新增
 * 未确认融资费用贷方减少场景：按实际利率法逐期摊销（→财务费用）
 *
 * 注意：未确认融资费用是长期应付款的备抵科目，其余额最终被净额公式扣减。
 * 净额 = 长期应付款 - 未确认融资费用 才是报表列报金额。
 *
 * @param beginning - 期初余额
 * @param debit - 借方发生额（新增未确认融资费用）
 * @param credit - 贷方发生额（本期摊销冲减额）
 * @returns 期末余额
 */
export function calcContraLiabilityEndBalance(beginning: number, debit: number, credit: number): number {
  return beginning + debit - credit
}

// ─── 4. 净额计算 ────────────────────────────────────────────

/**
 * 计算长期应付款净额
 * 净额 = 长期应付款余额 - 未确认融资费用余额
 *
 * 来源：L5-1 审定表第三区块"净值"
 * 报表列报的长期应付款=面值(原值)-未确认融资费用=实际融资成本(现值)
 *
 * 含义：
 * - 长期应付款（面值/原值）：合同约定的应付总额（含利息部分）
 * - 未确认融资费用：尚未分摊计入财务费用的利息差额
 * - 净额 = 真实负债成本（现值/摊余成本）
 *
 * @param payable - 长期应付款期末余额（面值/原值）
 * @param unrecognized - 未确认融资费用期末余额
 * @returns 净额（报表列报金额）
 */
export function calcNetPayable(payable: number, unrecognized: number): number {
  return payable - unrecognized
}

// ─── 5. 分类小计 ────────────────────────────────────────────

/**
 * 数组求和（按款项/分类汇总）
 *
 * 用于：
 * - L5-1 审定表按款项合计
 * - L5-2 明细表分类小计
 * - L5-3 未确认融资费用分类小计
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
