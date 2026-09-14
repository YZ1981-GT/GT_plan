/**
 * useM5FormulaEngine — M5 盈余公积公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4101 盈余公积（**贷方/权益类！**）
 *
 * ─── 权益类贷方方向铁律 ───
 * 盈余公积是所有者权益的正常科目（贷方余额）。
 * 期末余额 = 期初 + 贷方发生（增加） - 借方发生（减少）
 *
 * ⚠️ 与M3库存股（借方备抵）方向相反！
 *   M5盈余公积（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方 - 贷方
 * ─────────────────────────────────────
 *
 * 科目4101盈余公积业务特征：
 * - 法定盈余公积计提 → 贷方增加（借:利润分配-提取法定盈余公积 贷:盈余公积-法定盈余公积）
 * - 任意盈余公积计提 → 贷方增加（借:利润分配-提取任意盈余公积 贷:盈余公积-任意盈余公积）
 * - 转增资本 → 借方减少（借:盈余公积 贷:实收资本/股本）
 * - 弥补亏损 → 借方减少（借:盈余公积 贷:利润分配-盈余公积补亏）
 * - 期末 = 期初 + 贷方(计提) - 借方(转增/弥补)
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M5-1 审定表）
 * - P2: 权益类贷方期末余额
 * - P6: 分类小计（数组求和）
 *
 * Spec: .kiro/specs/m5-surplus-reserve/ Task 2.1
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
 * 来源：M5-1 审定表
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
 * 来源：M5-1 审定表 + M5-2 明细表
 * 盈余公积贷方增加场景：
 *   - 法定盈余公积计提（按净利润10%，累计不超注册资本50%）
 *   - 任意盈余公积计提（股东会决议）
 * 盈余公积借方减少场景：
 *   - 转增资本（借:盈余公积 贷:实收资本/股本）
 *   - 弥补亏损（借:盈余公积 贷:利润分配-盈余公积补亏）
 *
 * ⚠️ 与M3库存股（借方备抵类）方向相反！
 *   M5权益类：期末 = 期初 + 贷方(计提) - 借方(转增/弥补)
 *   M3备抵类：期末 = 期初 + 借方(回购) - 贷方(注销)
 *
 * @param begin - 期初余额（贷方余额）
 * @param credit - 贷方发生额（计提增加）
 * @param debit - 借方发生额（转增/弥补减少）
 * @returns 期末余额（贷方余额）
 */
export function calcEquityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P6: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（法定/任意盈余公积分类汇总）（Property P6）
 *
 * 用于：
 * - M5-1 审定表双区块（法定盈余公积+任意盈余公积）分类合计
 * - M5-2 明细表列小计
 * - M5-4 计提检查表核对合计行
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
