/**
 * K7 递延收益 — 政府补助分摊引擎（纯函数）
 *
 * CAS16 政府补助分摊测算：
 *   与资产相关：在相关资产使用寿命内按直线法分期计入损益
 *     本期分摊 = 补助总额 / 分摊期总期数 × 本期期数
 *   与收益相关：
 *     补偿以后期间费用 → 确认为递延收益，分期计入其他收益/营业外收入
 *     补偿已发生费用/损失 → 直接计入当期损益
 *   期末余额 = 补助总额 - 累计分摊
 *   测算差异 = 测算分摊 - 企业分摊
 *
 * 设计原则：纯函数，无Vue响应式，无副作用，可PBT验证
 * 所有函数对 NaN / undefined 输入视为 0 处理
 *
 * Spec: .kiro/specs/k7-deferred-income/ Requirements 4.2-4.5, 7.3-7.5
 */

// ─── Helpers ────────────────────────────────────────────────────────────────

/** 将 NaN / undefined / null 转为 0 */
function safeNum(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isNaN(n) ? 0 : n
}

// ─── 分摊函数 ───────────────────────────────────────────────────────────────

/**
 * 直线分摊 = 补助总额 / 分摊期总期数 × 本期期数
 *
 * CAS16: 与资产相关的政府补助，在相关资产使用寿命内按合理系统方法分期计入损益
 * K7-4 xlsx: M11=IF(C11=0,0,C11/(I11*12-DATEDIF(D11,$B$9,"M"))*K11)
 *
 * 错误处理（兜底）：
 * - totalPeriods = 0 → 返回 0（除零兜底 + 警告）
 * - NaN 输入 → 视为 0
 *
 * @param total 补助总额（≥0）
 * @param totalPeriods 分摊期总期数（>0，通常为月数）
 * @param currentPeriods 本期期数（≥0，通常为本期月数）
 * @returns 本期应分摊金额
 *
 * Requirement 7.3
 */
export function calcStraightLineAmort(total: number, totalPeriods: number, currentPeriods: number): number {
  const t = safeNum(total)
  const tp = safeNum(totalPeriods)
  const cp = safeNum(currentPeriods)
  if (tp === 0) return 0
  return (t / tp) * cp
}

/**
 * 期末余额 = 补助总额 - 累计分摊
 *
 * 递延收益余额反映尚未分摊的政府补助金额
 *
 * 错误处理（兜底）：
 * - accumulated > total → 返回 0（不允许负数余额，红色警告）
 * - NaN 输入 → 视为 0
 *
 * @param total 补助总额
 * @param accumulated 累计已分摊金额
 * @returns 期末余额（≥0）
 *
 * Requirement 7.4
 */
export function calcRemainingBalance(total: number, accumulated: number): number {
  const t = safeNum(total)
  const acc = safeNum(accumulated)
  const balance = t - acc
  return balance < 0 ? 0 : balance
}

/**
 * 分摊差异 = 测算分摊 - 企业分摊
 *
 * 正数 = 测算 > 企业（企业少摊了，可能低估费用/高估递延收益）
 * 负数 = 企业 > 测算（企业多摊了，可能高估费用/低估递延收益）
 *
 * @param calculated 测算应分摊金额
 * @param booked 企业账面已分摊金额
 * @returns 差异金额
 *
 * Requirement 7.5
 */
export function calcAmortVariance(calculated: number, booked: number): number {
  return safeNum(calculated) - safeNum(booked)
}
