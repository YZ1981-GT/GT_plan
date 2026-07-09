/**
 * useM2VerifyEngine — M2-5 验资核对引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 用途：M2-5 实收资本(股本)检查表（验资核对清单）
 *
 * ─── 验资核对逻辑 ───
 * 实收资本的存在与准确性认定依赖验资核对：
 * 将账面实缴出资与验资报告金额对比，确认出资真实性。
 * 出资到位率 < 100% 需关注认缴未实缴风险（公司法出资义务）。
 * ──────────────────────
 *
 * xlsx公式验证（M2-5检查表）：
 *   验资差异 = 实缴出资 - 验资金额
 *   出资到位率 = 实缴出资 / 认缴出资（G20 = G18 / G19）
 *
 * 本引擎覆盖：
 * - P5: calcVerifyDiff（实缴 - 验资 → 验资差异）
 * - P6: calcPaidInRate（实缴 / 认缴 → 出资到位率）
 *
 * Spec: .kiro/specs/m2-paid-in-capital/ Task 2.2
 * Requirements: 5.2-5.3, 7.3-7.4
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P5: 验资差异 ───────────────────────────────────────────

/**
 * 计算验资差异（Property P5）
 *
 * 验资差异 = 实缴出资 - 验资金额
 *
 * 来源：M2-5 实收资本(股本)检查表
 *
 * 正差异：实缴 > 验资（企业多记/验资少记，需查明原因）
 * 负差异：实缴 < 验资（企业少记/验资多记，需追补出资凭证）
 * 差异为0：核对一致，出资真实性得到验证。
 *
 * @param paid - 实缴出资金额（账面记录）
 * @param verified - 验资金额（验资报告确认数）
 * @returns 验资差异
 */
export function calcVerifyDiff(paid: number, verified: number): number {
  return safe(paid) - safe(verified)
}

// ─── P6: 出资到位率 ─────────────────────────────────────────

/**
 * 计算出资到位率（Property P6）
 *
 * 出资到位率 = 实缴出资 / 认缴出资
 *
 * 来源：M2-5 实收资本(股本)检查表
 * xlsx: G20 = G18 / G19
 *
 * 结果解读：
 *   = 1.0 (100%)：全额到位，出资义务已履行完毕
 *   < 1.0：部分到位，存在认缴未实缴（关注公司法出资期限）
 *   > 1.0：超额出资（罕见，需查明原因——溢价/误记？）
 *
 * ⚠️ 当认缴出资为0时返回0（避免除零，认缴=0属异常数据）
 *
 * @param paid - 实缴出资金额
 * @param subscribed - 认缴出资金额（除数，不可为0）
 * @returns 出资到位率（小数形式，1.0 = 100%）
 */
export function calcPaidInRate(paid: number, subscribed: number): number {
  const p = safe(paid)
  const s = safe(subscribed)
  if (s === 0) return 0
  return p / s
}
