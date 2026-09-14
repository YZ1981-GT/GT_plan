/**
 * useM8FormulaEngine — M8 一般风险准备公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4104 一般风险准备（**贷方/权益类！**）
 *
 * ─── 权益类贷方方向铁律 ───
 * 一般风险准备是所有者权益的正常科目（贷方余额）。
 * 期末余额 = 期初 + 贷方发生（计提增加） - 借方发生（转回/使用减少）
 *
 * ⚠️ 与M3库存股（借方备抵）方向相反！
 *   M8一般风险准备（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：      期末 = 期初 + 借方 - 贷方
 * ─────────────────────────────────────
 *
 * 科目4104一般风险准备业务特征：
 * - 金融企业专属（银行/证券/保险/金融）
 * - 从净利润中计提 → 贷方增加（借:利润分配 贷:一般风险准备）
 * - 弥补损失/转回 → 借方减少（借:一般风险准备 贷:利润分配）
 * - 期末 = 期初 + 贷方(计提) - 借方(转回/使用)
 * - 按风险资产期末余额的1.5%计提（最低标准）
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M8-1 审定表）
 * - P2: 权益类贷方期末余额
 * - P5: 分类小计（数组求和）
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/ Task 2.1
 * Requirements: 2.3-2.4, 6.3-6.4
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
 * 来源：M8-1 审定表
 * 对应xlsx公式：审定 = 未审 + AJE + RJE
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
 *   期末 = 期初 + 贷方发生额（计提增加） - 借方发生额（转回/使用减少）
 *
 * 来源：M8-1 审定表 + M8-2 明细表
 * 对应xlsx公式：E=B+C-D（期末 = 期初 + 贷方计提 - 借方转回）
 *
 * 一般风险准备贷方增加场景：
 *   - 从净利润中计提一般风险准备（金融企业按风险资产1.5%计提）
 * 一般风险准备借方减少场景：
 *   - 弥补尚未识别的可能性损失
 *   - 经批准转回
 *
 * ⚠️ 与M3库存股（借方备抵类）方向相反！
 *   M8权益类：期末 = 期初 + 贷方(计提) - 借方(转回)
 *   M3备抵类：期末 = 期初 + 借方(回购) - 贷方(注销)
 *
 * @param begin - 期初余额（贷方余额）
 * @param credit - 贷方发生额（计提增加）
 * @param debit - 借方发生额（转回/使用减少）
 * @returns 期末余额（贷方余额）
 */
export function calcEquityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P5: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（一般风险准备分类汇总）（Property P5）
 *
 * 用于：
 * - M8-1 审定表分类小计
 * - M8-2 明细表列小计（计提/转回合计）
 * - M8-4 风险资产计提测试汇总
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
