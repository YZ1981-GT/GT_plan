/**
 * useD1FormulaEngine — D1 应收票据共享纯函数公式引擎
 *
 * 所有函数为纯函数，无副作用，便于单元测试和 PBT。
 * 供 useD1Adjudication / useD1DetailCategory / useD1DetailCustomer / useD1BadDebt 复用。
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 6.4, 10.5
 */

// ─── 数值解析 ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/空串/NaN → 0
 *
 * 审计底稿中大量字段可能为空或无效值，统一转为数字 0 以确保公式运算不出 NaN。
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : parseFloat(val)
  return isNaN(n) ? 0 : n
}

// ─── 审定表公式 ──────────────────────────────────────────────────────────────

/**
 * 审定数 = 未审数 + AJE净额 + RJE净额
 *
 * 源模板公式 E8=B8+C8+D8，AJE/RJE 为净额不分借贷。
 * 适用于 D1-1 审定表、D1-2 按类别明细、D1-3 按客户明细的审定金额计算。
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

/**
 * 变动率计算，含期初=0特殊处理：
 * - 期初=0 且 审定=0 → ''（无意义）
 * - 期初=0 且 审定≠0 → 1（100%新增）
 * - 其他 → (审定-期初)/期初
 */
export function calcChangeRate(prior: number, audited: number): number | '' {
  if (prior === 0 && audited === 0) return ''
  if (prior === 0) return 1
  return (audited - prior) / prior
}

// ─── 小计与净值 ──────────────────────────────────────────────────────────────

/**
 * 小计 = SUM(明细行对应列)
 *
 * 审定表中每个区块的小计行公式，不可手动编辑。
 */
export function calcSubtotal(rows: number[]): number {
  return rows.reduce((sum, v) => sum + v, 0)
}

/**
 * 净值 = 原值 - 坏账准备
 *
 * D1-1 审定表第三区块"应收票据净值"行公式。
 */
export function calcNetValue(grossValue: number, badDebt: number): number {
  return grossValue - badDebt
}

// ─── 阈值判定 ────────────────────────────────────────────────────────────────

/**
 * 增减比例绝对值是否超阈值
 *
 * 审定表中 |变动率| > 30% 时红色高亮。rate 为 '' 时视为未超阈值。
 */
export function isChangeRateExceeding(rate: number | '', threshold: number): boolean {
  if (rate === '') return false
  return Math.abs(rate) > threshold
}

// ─── ECL 坏账准备公式 ────────────────────────────────────────────────────────

/**
 * ECL 预期信用损失率 = 各阶段迁徙率连乘
 *
 * D1-4 坏账准备按组合计提时，各账龄段迁徙率连乘得出预期损失率。
 * 空数组返回 0（无数据无意义）。
 */
export function calcExpectedLossRate(migrationRates: number[]): number {
  if (migrationRates.length === 0) return 0
  return migrationRates.reduce((acc, r) => acc * r, 1)
}

/**
 * 应计提 = 余额 × 损失率
 *
 * D1-4 坏账准备单项/组合计提核心公式。
 */
export function calcProvision(balance: number, lossRate: number): number {
  return balance * lossRate
}

/**
 * 差异 = 实际账面余额 - 应计提
 *
 * 正值表示多提，负值表示少提。
 */
export function calcDifference(actual: number, should: number): number {
  return actual - should
}

// ─── 坏账准备变动公式 ────────────────────────────────────────────────────────

/**
 * 期末未审数 = 期初审定 + 本期计提 - 本期收回 - 本期转回 - 本期核销 + 本期其他
 *
 * D1-4 坏账准备明细表各行的期末未审数自动计算。
 */
export function calcBadDebtEndBalance(
  priorAudited: number,
  provision: number,
  recovery: number,
  reversal: number,
  writeOff: number,
  other: number
): number {
  return priorAudited + provision - recovery - reversal - writeOff + other
}

/**
 * 期末未审数 = 期初审定 + 本期增加 - 本期减少
 *
 * D1-2（按类别）/ D1-3（按客户）原值明细表的期末未审数计算。
 */
export function calcCurrentUnadjusted(
  priorAudited: number,
  increase: number,
  decrease: number
): number {
  return priorAudited + increase - decrease
}
