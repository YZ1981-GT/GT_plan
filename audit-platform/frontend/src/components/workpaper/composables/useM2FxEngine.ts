/**
 * useM2FxEngine — M2-4 外币投资折算引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 用途：M2-4 外币投资汇率测算表（20×7，13公式）
 *
 * ─── 外币出资折算逻辑 ───
 * 外币出资按出资日汇率折算为本位币。
 * 折算差异 = 折算本位币 - 账面本位币。
 * 差异计入资本公积（M4），参见ADR-4。
 * ────────────────────────
 *
 * xlsx公式验证：
 *   E = C × D （折算本位币 = 原币金额 × 出资日汇率）
 *   G = E - F （折算差异 = 折算本位币 - 账面本位币）
 *
 * 本引擎覆盖：
 * - P3: calcFxConverted（原币×汇率 → 折算本位币）
 * - P4: calcFxDiff（折算本位币 - 账面本位币 → 折算差异）
 *
 * Spec: .kiro/specs/m2-paid-in-capital/ Task 2.2
 * Requirements: 4.2-4.3, 7.1-7.2
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 折算本位币 ─────────────────────────────────────────

/**
 * 计算折算本位币（Property P3）
 *
 * 折算本位币 = 原币金额 × 出资日汇率
 *
 * 来源：M2-4 外币投资汇率测算表
 * xlsx: E = C × D
 *
 * 示例：
 *   USD 100万 × 汇率6.5 = RMB 650万
 *
 * @param amount - 原币出资金额（C列）
 * @param rate - 出资日即期汇率（D列）
 * @returns 折算本位币金额（E列）
 */
export function calcFxConverted(amount: number, rate: number): number {
  return safe(amount) * safe(rate)
}

// ─── P4: 折算差异 ───────────────────────────────────────────

/**
 * 计算折算差异（Property P4）
 *
 * 折算差异 = 折算本位币 - 账面本位币
 *
 * 来源：M2-4 外币投资汇率测算表
 * xlsx: G = E - F
 *
 * 正差异：折算值 > 账面值（多记资本公积贷方）
 * 负差异：折算值 < 账面值（少记资本公积借方）
 * 差异计入M4资本公积（资本溢价/股本溢价），参见ADR-4。
 *
 * @param converted - 折算本位币金额（E列，即 calcFxConverted 结果）
 * @param booked - 账面本位币金额（F列，企业账面记录值）
 * @returns 折算差异（G列）
 */
export function calcFxDiff(converted: number, booked: number): number {
  return safe(converted) - safe(booked)
}
