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

// ─── 安全除法（IFERROR 语义） ────────────────────────────────────────────────

/**
 * 安全除法：divisor=0 返回 0，否则返回 numerator/divisor
 *
 * 对应源模板 IFERROR(x/y, 0) 语义，用于：
 * - 比例列计算 = IFERROR(本行余额 / 合计行余额, 0)
 * - 预期信用损失率 = IFERROR(坏账准备 / 账面余额, 0)
 */
export function safeDivide(numerator: number, divisor: number): number {
  if (divisor === 0) return 0
  return numerator / divisor
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

// ─── 贴息（贴现利息）公式 ────────────────────────────────────────────────────

/**
 * 贴息天数 = 到期日 - 贴现日（自然天数差）
 *
 * D1-9 贴息检查表：解析到期日与贴现日为日期，返回相差的整数天数。
 * 任一日期为空或非法 → 返回 0。
 * 贴现日 > 到期日（异常数据）→ 返回 0（贴息天数显示为 0）。
 */
export function calcDiscountDays(maturityDate: string, discountDate: string): number {
  if (!maturityDate || !discountDate) return 0
  const maturity = new Date(maturityDate).getTime()
  const discount = new Date(discountDate).getTime()
  if (isNaN(maturity) || isNaN(discount)) return 0
  const days = (maturity - discount) / 86400000
  if (days < 0) return 0
  return days
}

/**
 * 应计贴现利息 = 票面金额 × 贴现率 × 贴息天数 / 360
 *
 * D1-9 贴息检查表核心公式 P×R×D/360，用于与账面贴现利息核对。
 */
export function calcDiscountInterest(faceValue: number, discountRate: number, days: number): number {
  return (faceValue * discountRate * days) / 360
}

/**
 * 贴息差异 = 应计贴现利息 - 账面贴现利息
 *
 * D1-9 贴息检查表：正值表示应计大于账面（少计），负值表示应计小于账面（多计）。
 * 差异 ≠ 0 时高亮提示。
 */
export function calcInterestDifference(calculated: number, booked: number): number {
  return calculated - booked
}

// ─── 业务模式与列报项目判定（QA矩阵IF公式） ──────────────────────────────────

/**
 * QA矩阵业务模式判定：根据4个 Y/N 答案返回业务模式描述
 *
 * D1-6 业务模式分析，对应源模板 R21 的 IF(AND(...)) 嵌套公式：
 * - Q1=Y ∧ Q2=N → 以收取合同现金流量为目标的业务模式
 * - Q1=Y ∧ Q2=Y ∧ Q4=Y → 以收取合同现金流量和出售金融资产为目标的业务模式
 * - Q1=N ∨ (Q2=Y ∧ Q4=N) → 其他业务模式（以公允价值计量且其变动计入当期损益）
 * - 其余 → ''（判定条件不足）
 */
export function determineBusinessMode(
  q1: 'Y' | 'N' | '', q2: 'Y' | 'N' | '', q3: 'Y' | 'N' | '', q4: 'Y' | 'N' | ''
): string {
  if (q1 === 'Y' && q2 === 'N') {
    return '属于以收取合同现金流量为目标的业务模式'
  }
  if (q1 === 'Y' && q2 === 'Y' && q4 === 'Y') {
    return '属于以收取合同现金流量和出售金融资产为目标的业务模式'
  }
  if (q1 === 'N' || (q2 === 'Y' && q4 === 'N')) {
    return '其他业务模式（以公允价值计量且其变动计入当期损益）'
  }
  return ''
}

/**
 * 列报项目判定：根据业务模式返回列报科目
 *
 * D1-6 判定结果 → D1-1 列报分类映射。
 * 注意判定顺序：'收取合同现金流量和出售金融资产' 必须先于 '收取合同现金流量为目标' 判断，
 * 因为前者字符串包含子串 '收取合同现金流量'，顺序颠倒会导致误匹配。
 * - 收取合同现金流量和出售金融资产 → 应收款项融资
 * - 收取合同现金流量为目标 → 应收票据
 * - 其他业务模式 → 以公允价值计量且其变动计入当期损益的金融资产
 * - 其余 → ''
 */
export function determineReportItem(businessMode: string): string {
  if (businessMode.includes('收取合同现金流量和出售金融资产')) {
    return '应收款项融资'
  }
  if (businessMode.includes('收取合同现金流量为目标')) {
    return '应收票据'
  }
  if (businessMode.includes('其他业务模式')) {
    return '以公允价值计量且其变动计入当期损益的金融资产'
  }
  return ''
}
