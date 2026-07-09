/**
 * useM3FxEngine — M3 库存股外币折算引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4002 库存股（**借方/权益备抵类！**）
 *
 * ─── 外币回购折算逻辑 ───
 * 境外回购以外币计价，按回购日即期汇率折算为本位币（人民币）。
 * 折算差异 = 折算本位币 - 账面本位币（已入账金额）
 * 当 |折算差异| > 阈值时，前端红色高亮提示审计人员关注。
 * ────────────────────────
 *
 * 本引擎覆盖：
 * - P5: 外币折算本位币（原币 × 回购日汇率）
 * - calcFxDiff: 折算差异（折算本位币 - 账面本位币）
 *
 * Spec: .kiro/specs/m3-treasury-stock/ Task 2.2
 * Requirements: 4.2-4.3, 7.1-7.2
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P5: 外币折算本位币 ─────────────────────────────────────

/**
 * 计算外币折算本位币（Property P5）
 * 折算本位币 = 原币回购额 × 回购日即期汇率
 *
 * 来源：M3-4 外币投资汇率测算表
 * 适用场景：境外回购库存股，外币金额按交易日汇率折算。
 *
 * @param amount - 原币回购金额（外币，如 USD/HKD）
 * @param rate - 回购日即期汇率（1外币=X人民币）
 * @returns 折算本位币金额（人民币）
 */
export function calcFxConverted(amount: number, rate: number): number {
  return safe(amount) * safe(rate)
}

// ─── 折算差异 ───────────────────────────────────────────────

/**
 * 计算折算差异
 * 折算差异 = 折算本位币 - 账面本位币
 *
 * 来源：M3-4 外币投资汇率测算表
 * 当差异显著（超过阈值）时提示审计关注，可能涉及汇率选用错误。
 *
 * @param converted - 折算本位币金额（calcFxConverted 计算结果）
 * @param booked - 账面本位币金额（被审计单位已入账金额）
 * @returns 折算差异（正=折算>账面，负=折算<账面）
 */
export function calcFxDiff(converted: number, booked: number): number {
  return safe(converted) - safe(booked)
}
