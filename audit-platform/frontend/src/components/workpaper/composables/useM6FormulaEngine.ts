/**
 * useM6FormulaEngine — M6 未分配利润公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！**）
 *
 * ─── 权益类贷方方向铁律 ───
 * 未分配利润是所有者权益的正常科目（贷方余额）。
 * 期末余额 = 期初 + 贷方发生（增加） - 借方发生（减少）
 *
 * ⚠️ 与M3库存股（借方备抵）方向相反！
 *   M6未分配利润（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：    期末 = 期初 + 借方 - 贷方
 * ─────────────────────────────────────
 *
 * 科目4104利润分配-未分配利润业务特征：
 * - 本年净利润结转 → 贷方增加（借:本年利润 贷:利润分配-未分配利润）
 * - 提取盈余公积 → 借方减少（借:利润分配-未分配利润 贷:盈余公积）
 * - 宣告分配股利 → 借方减少（借:利润分配-未分配利润 贷:应付股利）
 * - 期末 = 期初 + 贷方(净利润转入) - 借方(分配)
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M6-1 审定表）
 * - P2: 权益类贷方期末余额
 * - P6: 分类小计（数组求和）
 *
 * Spec: .kiro/specs/m6-retained-earnings/ Task 2.1
 * Requirements: 2.3-2.4, 6.4
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
 * 来源：M6-1 审定表
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
 * 来源：M6-1 审定表
 * 未分配利润贷方增加场景：
 *   - 本年净利润结转（借:本年利润 贷:利润分配-未分配利润）
 *   - 盈余公积弥补亏损转入（借:盈余公积 贷:利润分配-未分配利润）
 * 未分配利润借方减少场景：
 *   - 提取法定盈余公积（借:利润分配-未分配利润 贷:盈余公积）
 *   - 提取任意盈余公积（借:利润分配-未分配利润 贷:盈余公积）
 *   - 宣告分配股利（借:利润分配-未分配利润 贷:应付股利）
 *
 * ⚠️ 与M3库存股（借方备抵类）方向相反！
 *   M6权益类：期末 = 期初 + 贷方(增加) - 借方(减少)
 *   M3备抵类：期末 = 期初 + 借方(回购) - 贷方(注销)
 *
 * @param begin - 期初余额（贷方余额）
 * @param credit - 贷方发生额（净利润转入等增加）
 * @param debit - 借方发生额（分配等减少）
 * @returns 期末余额（贷方余额）
 */
export function calcEquityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P6: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（利润分配项目分类汇总）（Property P6）
 *
 * 用于：
 * - M6-1 审定表合计行
 * - M6-2 明细表列小计（净利润转入/盈余公积提取/股利分配各项合计）
 * - M6-4 检查表核对合计行
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
