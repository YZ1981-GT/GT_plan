/**
 * K1 其他应收款 — 坏账准备测算引擎（纯函数）
 *
 * 核心公式：
 * - ECL = EAD × PD × LGD（PD或LGD为0时ECL=0兜底）
 * - 账龄损失 = 余额 × 损失率
 * - 测算差异 = 测算应计提 - 企业计提
 *
 * Spec: .kiro/specs/k1-other-receivables/ Requirements 6.2-6.4, 12.2-12.3
 */

/**
 * ECL = EAD × PD × LGD
 *
 * Edge case: 任何输入为负数时返回0兜底（per design.md错误处理）
 *
 * @param ead - 违约风险暴露（Exposure at Default）
 * @param pd - 违约概率（Probability of Default）
 * @param lgd - 违约损失率（Loss Given Default）
 * @returns ECL金额
 */
export function calcECL(ead: number, pd: number, lgd: number): number {
  if (ead < 0 || pd < 0 || lgd < 0) return 0
  return ead * pd * lgd
}

/**
 * 账龄损失 = 余额 × 损失率
 *
 * @param balance - 期末余额
 * @param lossRate - 预期损失率
 * @returns 账龄组预期损失
 */
export function calcAgingLoss(balance: number, lossRate: number): number {
  if (balance < 0 || lossRate < 0) return 0
  return balance * lossRate
}

/**
 * 测算差异 = 测算应计提 - 企业计提
 *
 * @param calculated - 测算应计提金额
 * @param booked - 企业实际计提金额
 * @returns 差异（正值表示企业少提，负值表示企业多提）
 */
export function calcProvisionVariance(calculated: number, booked: number): number {
  return calculated - booked
}
