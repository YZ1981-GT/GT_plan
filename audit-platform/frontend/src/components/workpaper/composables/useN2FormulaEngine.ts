/**
 * useN2FormulaEngine — N2 应交税费公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2221 应交税费（**贷方/负债类！**）
 *
 * ─── 负债类方向铁律 ───
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生（计提/增加）- 借方发生（缴纳/减少）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 *
 * 2221应交税费是负债类贷方科目：
 *   - 贷方增加（计提应交）：借:税金及附加/所得税费用 贷:应交税费
 *   - 借方减少（实际缴纳）：借:应交税费 贷:银行存款
 *   - 期末 = 期初 + 贷方(计提) - 借方(缴纳)
 *
 * 这是 N 税费循环（应交税费/递延所得税等）的负债类科目共用规则。
 * ─────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（N2-1 审定表）
 * - P2: 负债类贷方期末余额（期初+贷-借）
 * - P8: 合计行恒等（数组求和）
 * - calcDiff: 账面金额 vs 申报表差异
 *
 * Spec: .kiro/specs/n2-taxes-payable/ Task 2.1
 * Requirements: 1.5, 2.3, 2.4, 12.1-12.4
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P1: 审定数公式链 ───────────────────────────────────────

/**
 * 计算审定数（Property P1）
 * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
 *
 * 来源：N2-1 审定表 E=B+C+D
 * N循环所有科目审定公式统一。
 *
 * @param unadjusted - 未审数（trial_balance.unadjusted_amount）
 * @param aje - 审计调整金额（正=调增，负=调减）
 * @param rje - 重分类调整金额
 * @returns 审定数
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return safe(unadjusted) + safe(aje) + safe(rje)
}

// ─── P2: 负债类期末余额（贷方！） ──────────────────────────

/**
 * 计算负债类科目期末余额（Property P2）
 *
 * ⚠️⚠️⚠️ 负债类（贷方科目）方向：
 *   期末 = 期初 + 贷方发生额（计提/增加） - 借方发生额（缴纳/减少）
 *
 * 来源：N2-1 审定表 + N2-2 明细表
 * 应交税费贷方增加场景：
 *   - 各税种计提（借:税金及附加/所得税费用 贷:应交税费）
 *   - 增值税销项（借:应收账款 贷:主营业务收入/应交税费-应交增值税-销项税额）
 * 应交税费借方减少场景：
 *   - 实际缴纳（借:应交税费 贷:银行存款）
 *   - 进项税额抵扣
 *
 * ⚠️ 与资产类方向相反！
 *   N2负债类：期末 = 期初 + 贷方(计提) - 借方(缴纳)
 *   资产类：  期末 = 期初 + 借方(增加) - 贷方(减少)
 *
 * @param begin - 期初余额（贷方余额）
 * @param credit - 贷方发生额（计提/增加）
 * @param debit - 借方发生额（缴纳/减少）
 * @returns 期末余额（贷方余额）
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P8: 合计行恒等 ────────────────────────────────────────

/**
 * 数组求和（各税种分行小计/合计行）（Property P8）
 *
 * 用于：
 * - N2-1 审定表各税种行合计
 * - N2-2 明细表列小计（计提合计/缴纳合计/期末合计）
 * - N2-5 认定表汇总行
 *
 * @param arr - 待求和的金额数组
 * @returns 合计金额
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr)) return 0
  let total = 0
  for (const a of arr) {
    total += safe(a)
  }
  return total
}

// ─── 账面 vs 申报表差异 ────────────────────────────────────

/**
 * 计算账面金额与申报表金额的差异
 *
 * 差异 = 账面金额 - 申报表金额
 * 来源：N2-2 明细表（核对区段）
 *
 * 含义：正值=账面大于申报表（可能多计提），负值=账面小于申报表（可能少计提）
 * 差异≠0 时需红色高亮标注，审计人员需填写差异原因说明。
 *
 * @param bookAmount - 账面金额（期末余额/本期计提额）
 * @param declaredAmount - 申报表金额（纳税申报表对应数据）
 * @returns 差异金额（正=账面>申报表，负=账面<申报表）
 */
export function calcDiff(bookAmount: number, declaredAmount: number): number {
  return safe(bookAmount) - safe(declaredAmount)
}
