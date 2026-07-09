/**
 * useM2FormulaEngine — M2 实收资本（股本）公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4001 实收资本/股本（**贷方/权益类！**）
 *
 * ─── 权益类方向铁律 ───
 * 权益类（贷方科目）期末余额 = 期初 + 贷方发生（增资） - 借方发生（减资）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 * M股东权益循环 M2/M4/M5/M6/M7/M8/M9/M10 均为权益类贷方。
 * ─────────────────────
 *
 * 科目4001实收资本/股本业务特征：
 * - 增资时 → 贷方增加（贷记实收资本）
 * - 减资时 → 借方减少（借记实收资本）
 * - 期末 = 期初 + 贷方(增资) - 借方(减资)
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M2-1 审定表）
 * - P2: 权益类期末余额（贷方科目方向）
 * - P7: 分类小计（数组求和）
 * - 变动额/变动率（审定表M2-1附加）
 * - 持股/出资比例（明细表M2-2）
 *
 * Spec: .kiro/specs/m2-paid-in-capital/ Task 2.1
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
 * 来源：M2-1 审定表
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

// ─── P2: 权益类期末余额（贷方！） ──────────────────────────

/**
 * 计算权益类科目期末余额（Property P2）
 *
 * ⚠️ 权益类（贷方科目）方向：
 *   期末 = 期初 + 贷方发生额（增资） - 借方发生额（减资）
 *
 * 来源：M2-1 审定表 + M2-2 明细表
 *
 * xlsx验证：
 *   非上市 T=P+R-S（期末=期初+贷方增资-借方减资）
 *   上市   K=D+F-J（期末=期初+本期增加-本期减少）
 *   上市   AF=Y+AE（审定期末公式同理）
 *
 * 与资产类相反！资产类期末 = 期初 + 借方 - 贷方
 *
 * @param begin - 期初余额
 * @param credit - 贷方发生额（增资）
 * @param debit - 借方发生额（减资）
 * @returns 期末余额
 */
export function calcEquityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P7: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（按出资人/股东分类汇总）（Property P7）
 *
 * 用于：
 * - M2-1 审定表按出资人分类合计
 * - M2-2 明细表列小计
 * - M2-4 外币投资合计行
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

// ─── 变动额（审定表M2-1附加） ───────────────────────────────

/**
 * 计算变动额
 * 变动额 = 期末审定 - 期初审定
 *
 * 来源：M2-1 审定表（xlsx: J=I-E）
 * 正值=本期实收资本增加（增资），负值=本期减少（减资）
 *
 * @param endAudited - 期末审定数
 * @param beginAudited - 期初审定数
 * @returns 变动额
 */
export function calcVarianceAmount(endAudited: number, beginAudited: number): number {
  return safe(endAudited) - safe(beginAudited)
}

// ─── 变动率（审定表M2-1附加） ───────────────────────────────

/**
 * 计算变动率（条件除法）
 *
 * xlsx公式：
 *   K=IF(AND(E=0,J=0),0,IF(AND(E=0,J>0),1,J/E))
 *
 * 翻译：
 *   - 期初=0 且 变动额=0 → 0（无变动）
 *   - 期初=0 且 变动额>0 → 1（100%增长）
 *   - 其他 → 变动额/期初（变动比率）
 *
 * @param beginAudited - 期初审定数（除数）
 * @param varianceAmount - 变动额（被除数）
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

// ─── 持股/出资比例（明细表M2-2） ────────────────────────────

/**
 * 计算持股比例 / 出资比例
 *
 * 个体出资 / 合计出资（0除法保护）
 *
 * 来源：M2-2 明细表
 *   上市：个人股数/总股数
 *   非上市：个人出资/总出资
 *
 * @param individual - 个体出资/股数
 * @param total - 合计出资/股数
 * @returns 持股/出资比例（小数形式，0.5=50%）
 */
export function calcShareRatio(individual: number, total: number): number {
  const ind = safe(individual)
  const tot = safe(total)
  if (tot === 0) return 0
  return ind / tot
}
