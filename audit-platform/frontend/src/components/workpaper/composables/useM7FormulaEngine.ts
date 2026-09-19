/**
 * useM7FormulaEngine — M7 专项储备公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4201 专项储备（**贷方/权益类！**）
 *
 * ─── 权益类贷方方向铁律 ───
 * 专项储备是所有者权益的正常科目（贷方余额）。
 * 期末余额 = 期初 + 贷方发生（计提增加） - 借方发生（使用减少）
 *
 * ⚠️ 与M3库存股（借方备抵）方向相反！
 *   M7专项储备（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方 - 贷方
 * ─────────────────────────────────────
 *
 * 科目4201专项储备业务特征：
 * - 安全生产费计提 → 贷方增加（借:生产成本/制造费用/管理费用 贷:专项储备）
 * - 费用性支出使用 → 借方减少（借:专项储备 贷:银行存款等）
 * - 资本性支出使用 → 借方减少（借:专项储备 贷:累计折旧—专项储备折旧）
 * - 期末 = 期初 + 贷方(计提) - 借方(使用)
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M7-1 审定表）
 * - P2: 权益类贷方期末余额
 * - P6: 分类小计（数组求和）
 *
 * Spec: .kiro/specs/m7-special-reserve/ Task 2.1
 * Requirements: 2.3-2.4, 7.4
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
 * 来源：M7-1 审定表
 * 对应xlsx公式：L10 = B10+F10+G10（审定期初 = 未审期初 + AJE + RJE）
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

// ─── P2: 权益类贷方期末余额 ─────────────────────────────────

/**
 * 计算权益类科目期末余额（Property P2）
 *
 * ⚠️⚠️⚠️ 权益类贷方科目方向：
 *   期末 = 期初 + 贷方发生额（计提增加） - 借方发生额（使用减少）
 *
 * 来源：M7-1 审定表 + M7-2 明细表
 * 对应xlsx公式：E10 = B10+C10-D10（期末 = 期初 + 贷方 - 借方）
 *              O10 = L10+M10-N10（审定期末 = 审定期初 + 审定增加 - 审定减少）
 *
 * 专项储备贷方增加场景：
 *   - 安全生产费计提（高危行业按产量/收入分档计提）
 *   - 其他专项储备计提
 * 专项储备借方减少场景：
 *   - 费用性支出（直接冲减专项储备）
 *   - 资本性支出（形成固定资产，同时全额折旧冲减专项储备）
 *
 * ⚠️ 与M3库存股（借方备抵类）方向相反！
 *   M7权益类：期末 = 期初 + 贷方(计提) - 借方(使用)
 *   M3备抵类：期末 = 期初 + 借方(回购) - 贷方(注销)
 *
 * @param begin - 期初余额（贷方余额）
 * @param credit - 贷方发生额（计提增加）
 * @param debit - 借方发生额（使用减少）
 * @returns 期末余额（贷方余额）
 */
export function calcEquityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P6: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（专项储备分类汇总）（Property P6）
 *
 * 用于：
 * - M7-1 审定表按类别分类小计
 * - M7-2 明细表列小计（计提/费用化使用/资本化使用）
 * - SUM(B7:B12) 等xlsx中的区域求和
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
