/**
 * useM4FormulaEngine — M4 资本公积公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4002 资本公积（**贷方/权益类！**）
 *
 * ─── 权益类贷方方向铁律 ───
 * 资本公积是所有者权益的正常科目（贷方余额）。
 * 期末余额 = 期初 + 贷方发生（增加） - 借方发生（减少）
 *
 * ⚠️ 与M3库存股（借方备抵）方向相反！
 *   M4资本公积（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方 - 贷方
 * ─────────────────────────────────────
 *
 * 科目4002资本公积业务特征：
 * - 资本溢价增加 → 贷方增加（借:银行存款 贷:资本公积-资本溢价）
 * - 其他资本公积增加 → 贷方增加（如J3股份支付权益结算、M2外币折算差异）
 * - 转增资本/弥补亏损 → 借方减少（借:资本公积 贷:实收资本/利润分配）
 * - 期末 = 期初 + 贷方(增加) - 借方(减少)
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M4-1 审定表）
 * - P2: 权益类贷方期末余额
 * - P5: 分类小计（数组求和）
 *
 * Spec: .kiro/specs/m4-capital-reserve/ Task 2.1
 * Requirements: 2.3-2.4, 6.3
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
 * 来源：M4-1 审定表
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
 *   期末 = 期初 + 贷方发生额（增加） - 借方发生额（减少）
 *
 * 来源：M4-1 审定表 + M4-2 明细表
 * 资本公积贷方增加场景：
 *   - 资本溢价（出资超面值部分）
 *   - J3股份支付权益结算（等待期确认计入其他资本公积）
 *   - M2外币出资折算差异
 * 资本公积借方减少场景：
 *   - 转增资本（借:资本公积 贷:实收资本）
 *   - 弥补亏损（借:资本公积 贷:利润分配）
 *
 * ⚠️ 与M3库存股（借方备抵类）方向相反！
 *   M4权益类：期末 = 期初 + 贷方(增加) - 借方(减少)
 *   M3备抵类：期末 = 期初 + 借方(回购) - 贷方(注销)
 *
 * @param begin - 期初余额（贷方余额）
 * @param credit - 贷方发生额（增加）
 * @param debit - 借方发生额（减少）
 * @returns 期末余额（贷方余额）
 */
export function calcEquityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P5: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（资本溢价/其他资本公积分类汇总）（Property P5）
 *
 * 用于：
 * - M4-1 审定表双区块（资本溢价+其他资本公积）分类合计
 * - M4-2 明细表列小计
 * - M4-4 检查表核对合计行
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
