/**
 * useM3FormulaEngine — M3 库存股公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4002 库存股（**借方/权益备抵类！**）
 *
 * ─── 权益备抵类方向铁律（M3独有！） ───
 * 库存股是所有者权益的**备抵科目**，在资产负债表所有者权益项下以负数列示。
 * 期末余额 = 期初 + 借方发生（回购增加） - 贷方发生（注销/再售减少）
 *
 * ⚠️ 方向与其他M权益类（M2/M4/M5/M6/M7/M8/M9/M10）完全相反！
 *   其他M权益类（贷方科目）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方 - 贷方
 * ─────────────────────────────────────
 *
 * 科目4002库存股业务特征：
 * - 回购股份时 → 借方增加（借记库存股，贷记银行存款）
 * - 注销/再出售时 → 贷方减少（贷记库存股，借记实收资本/资本公积）
 * - 期末 = 期初 + 借方(回购增加) - 贷方(注销/再售减少)
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M3-1 审定表）
 * - P2: 权益备抵类期末余额（借方科目方向！）
 * - P6: 分类小计（数组求和）
 *
 * Spec: .kiro/specs/m3-treasury-stock/ Task 2.1
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
 * 来源：M3-1 审定表
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

// ─── P2: 权益备抵类期末余额（借方！） ──────────────────────

/**
 * 计算权益备抵类科目期末余额（Property P2）
 *
 * ⚠️⚠️⚠️ M3独有公式 — 权益备抵类（借方科目）方向：
 *   期末 = 期初 + 借方发生额（回购增加） - 贷方发生额（注销/再售减少）
 *
 * 来源：M3-1 审定表 + M3-2 明细表
 * 库存股借方增加场景：股份回购（借:库存股 贷:银行存款）
 * 库存股贷方减少场景：注销库存股（借:实收资本/资本公积 贷:库存股）或再出售
 *
 * ⚠️ 与M2/M4/M5/M6等权益类（贷方增加）方向相反！
 *   M2权益类：期末 = 期初 + 贷方(增资) - 借方(减资)
 *   M3备抵类：期末 = 期初 + 借方(回购) - 贷方(注销)
 *
 * @param begin - 期初余额（借方余额）
 * @param debit - 借方发生额（回购增加）
 * @param credit - 贷方发生额（注销/再售减少）
 * @returns 期末余额（借方余额）
 */
export function calcContraEquityEndBalance(begin: number, debit: number, credit: number): number {
  return safe(begin) + safe(debit) - safe(credit)
}

// ─── P6: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（按回购批次分类汇总）（Property P6）
 *
 * 用于：
 * - M3-1 审定表按回购批次分类合计
 * - M3-2 明细表列小计
 * - M3-5 检查表核对合计行
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
