/**
 * useM1FormulaEngine — M1 应付股利（利润）公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2232 应付股利（**贷方/负债类！**）
 *
 * ─── 负债类方向铁律 ───
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生（增加） - 借方发生（减少）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 * ─────────────────────
 *
 * 科目2232应付股利业务特征：
 * - 宣告分配时 → 贷方增加（贷记应付股利）
 * - 实际支付时 → 借方减少（借记应付股利）
 * - 期末 = 期初 + 贷方(宣告增加) - 借方(支付减少)
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M1-1 审定表）
 * - P2: 负债类期末余额（贷方科目方向）
 * - P6: 分类小计（数组求和）
 * - 变动额/变动率（审定表M1-1附加）
 *
 * Spec: .kiro/specs/m1-dividends-payable/ Task 2.1
 * Requirements: 2.3-2.4, 7.5
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
 * 来源：M1-1 审定表
 * M循环所有科目审定公式统一。
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
 * ⚠️ 负债类（贷方科目）方向：
 *   期末 = 期初 + 贷方发生额（增加） - 借方发生额（减少）
 *
 * 来源：M1-1 审定表 + M1-2 明细表
 * 应付股利贷方增加场景：股东大会决议宣告分配股利（借:利润分配 贷:应付股利）
 * 应付股利借方减少场景：实际支付股利（借:应付股利 贷:银行存款）
 *
 * 与资产类相反！资产类期末 = 期初 + 借方 - 贷方
 *
 * @param begin - 期初余额
 * @param credit - 贷方发生额（宣告增加）
 * @param debit - 借方发生额（支付减少）
 * @returns 期末余额
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P6: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（按股东/分类汇总）（Property P6）
 *
 * 用于：
 * - M1-1 审定表按股东分类合计（B13=SUM(B7:B12)）
 * - M1-2 明细表列小计
 * - M1-4 外币合计行
 * - M1-5 股利测算合计行
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

// ─── 变动额（审定表M1-1附加） ───────────────────────────────

/**
 * 计算变动额
 * 变动额 = 期末审定 - 期初审定
 *
 * 来源：M1-1 审定表 J列（xlsx: J7=I7-E7）
 * 正值=本期应付股利增加，负值=本期减少
 *
 * @param endAudited - 期末审定数（I列）
 * @param beginAudited - 期初审定数（E列）
 * @returns 变动额
 */
export function calcVarianceAmount(endAudited: number, beginAudited: number): number {
  return safe(endAudited) - safe(beginAudited)
}

// ─── 变动率（审定表M1-1附加） ───────────────────────────────

/**
 * 计算变动率（条件除法）
 *
 * xlsx公式（K列）：
 *   K7=IF(AND(E7=0,J7=0),0,IF(AND(E7=0,J7>0),1,J7/E7))
 *
 * 翻译：
 *   - 期初=0 且 变动额=0 → 0（无变动）
 *   - 期初=0 且 变动额>0 → 1（100%增长）
 *   - 其他 → 变动额/期初（变动比率）
 *
 * 注意：参数顺序与xlsx对应：
 *   beginAudited = E列（期初审定）
 *   varianceAmount = J列（变动额）
 *
 * @param beginAudited - 期初审定数（E列，除数）
 * @param varianceAmount - 变动额（J列，被除数）
 * @returns 变动率（小数形式，1=100%）
 */
export function calcVarianceRate(beginAudited: number, varianceAmount: number): number {
  const b = safe(beginAudited)
  const v = safe(varianceAmount)
  if (b === 0 && v === 0) return 0
  if (b === 0 && v > 0) return 1
  if (b === 0) return v // 期初=0且变动<0，保护性返回变动额本身（避免除零）
  return v / b
}
