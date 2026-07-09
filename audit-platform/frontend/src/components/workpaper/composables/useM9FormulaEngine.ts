/**
 * useM9FormulaEngine — M9 其他综合收益公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4103 其他综合收益（**贷方/权益类！**）
 *
 * ─── 权益类贷方方向铁律 ───
 * 其他综合收益是所有者权益的正常科目（贷方余额）。
 * 期末余额 = 期初 + 贷方发生（增加） - 借方发生（减少）
 *
 * ⚠️ 与M3库存股（借方备抵）方向相反！
 *   M9其他综合收益（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：      期末 = 期初 + 借方 - 贷方
 * ─────────────────────────────────────
 *
 * 科目4103其他综合收益业务特征：
 * - OCI增加 → 贷方增加（如：其他权益工具投资公允价值上升）
 * - OCI减少/重分类进损益 → 借方减少（如：处置时转入投资收益）
 * - 期末 = 期初 + 贷方(OCI增加) - 借方(减少/重分类)
 *
 * 两大类：
 * - 以后不能重分类进损益：G8其他权益工具投资公允变动、J2设定受益计划重计量
 * - 以后能重分类进损益：其他债权投资公允变动、现金流量套期损益、外币折算差额
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M9-1 审定表）
 * - P2: 权益类贷方期末余额
 * - P6: 分类小计（数组求和）
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/ Task 2.1
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
 * 来源：M9-1 审定表
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
 * 来源：M9-1 审定表 + M9-2 明细表
 * 其他综合收益贷方增加场景：
 *   - 其他权益工具投资公允价值上升（不可重分类，来源G8）
 *   - 设定受益计划重计量利得（不可重分类，来源J2）
 *   - 其他债权投资公允价值上升（可重分类）
 *   - 现金流量套期有效部分（可重分类）
 *   - 外币财务报表折算汇兑差额（可重分类）
 * 其他综合收益借方减少场景：
 *   - 处置其他权益工具投资转入留存收益
 *   - 重分类进损益（如处置其他债权投资时）
 *   - 现金流量套期被套期项目影响损益时
 *
 * ⚠️ 与M3库存股（借方备抵类）方向相反！
 *   M9权益类：期末 = 期初 + 贷方(OCI增加) - 借方(减少/重分类)
 *   M3备抵类：期末 = 期初 + 借方(回购) - 贷方(注销)
 *
 * @param begin - 期初余额（贷方余额）
 * @param credit - 贷方发生额（OCI增加）
 * @param debit - 借方发生额（OCI减少/重分类进损益）
 * @returns 期末余额（贷方余额）
 */
export function calcEquityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P6: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（OCI两大类分组汇总）（Property P6）
 *
 * 用于：
 * - M9-1 审定表双区块（不可重分类+可重分类）分类合计
 * - M9-2 明细表各列小计
 * - M9-4 核对表来源合计行
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
