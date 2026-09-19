/**
 * useM1FxEngine — M1 外币汇率折算引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * 对应：外币汇率测算表M1-4（25×7，16 calc公式）
 * 科目：2232 应付股利（贷方/负债类）中的外币股东部分
 *
 * 本引擎覆盖：
 * - P3: 折算本位币 = 原币金额 × 期末汇率（xlsx: M1-4 E=C*D）
 * - P4: 汇兑差异 = 折算本位币 - 账面数（xlsx: M1-4 G=E-F）
 *
 * 列名映射（xlsx列名权威）：
 * | xlsx列名   | 变量名     | 列位 | 备注         |
 * |-----------|-----------|------|------------|
 * | 原币金额   | amount    | C列  | 用户输入     |
 * | 折算汇率   | rate      | D列  | 期末即期汇率  |
 * | 折合人民币  | converted | E列  | 计算值       |
 * | 账面数     | booked    | F列  | 用户输入     |
 * | 差额      | diff      | G列  | 计算值       |
 *
 * Spec: .kiro/specs/m1-dividends-payable/ Task 2.2
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
 * 折算本位币 = 原币金额 × 期末汇率
 *
 * 来源：M1-4 外币汇率测算表
 * xlsx公式：E10=C10*D10 ... E15=C15*D15
 *
 * @param amount - 原币金额（C列）
 * @param rate - 折算汇率/期末即期汇率（D列）
 * @returns 折合人民币（E列）
 */
export function calcFxConverted(amount: number, rate: number): number {
  return safe(amount) * safe(rate)
}

// ─── P4: 汇兑差异 ───────────────────────────────────────────

/**
 * 计算汇兑差异（Property P4）
 *
 * 汇兑差异 = 折算本位币 - 账面本位币
 *
 * 来源：M1-4 外币汇率测算表
 * xlsx公式：G10=E10-F10 ... G15=E15-F15
 *
 * 正值=折算后大于账面（汇率上升导致外币负债增加）
 * 负值=折算后小于账面（汇率下降导致外币负债减少）
 *
 * @param converted - 折算本位币/折合人民币（E列，计算值）
 * @param booked - 账面本位币/账面数（F列，用户输入）
 * @returns 汇兑差异/差额（G列）
 */
export function calcFxDiff(converted: number, booked: number): number {
  return safe(converted) - safe(booked)
}
