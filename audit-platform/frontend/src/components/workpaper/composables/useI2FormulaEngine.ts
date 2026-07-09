/**
 * I2 开发支出 — 公式引擎（纯函数，无副作用）
 * 科目：1717开发支出（借方/资产类）
 * 核心特征：CAS6五条件资本化 + I6↔I2双向联动 + I1转入 + 三角勾稽
 * Spec: .kiro/specs/i2-development-expenditure/
 */

// ---------- 基础公式 ----------

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末余额（借方科目1717开发支出）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/**
 * 三角勾稽校验：差额 = 期末 - (期初 + 增加 - 减少)
 * 返回0表示勾稽平衡，非0表示存在差异
 */
export function calcTriangleReconciliation(begin: number, increase: number, decrease: number, end: number): number {
  return end - (begin + increase - decrease)
}

/** 净值 = 原值 - 减值准备 */
export function calcNetValue(cost: number, impairment: number): number {
  return cost - impairment
}

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

// ---------- 分析公式 ----------

/** 变动率 = (本期 - 上期) / 上期；上期为0时返回null */
export function calcChangeRate(current: number, prior: number): number | null {
  if (prior === 0) return null
  return (current - prior) / prior
}

/** 差异 = 实际值 - 预期值 */
export function calcVarianceFromExpected(actual: number, expected: number): number {
  return actual - expected
}

// ---------- I2 专属公式 ----------

/**
 * 借贷平衡校验
 * 比较借方合计与贷方合计，精度容差1e-6
 */
export function calcDebitCreditBalance(debits: number[], credits: number[]): {
  totalDebit: number
  totalCredit: number
  isBalanced: boolean
} {
  const totalDebit = debits.reduce((s, d) => s + d, 0)
  const totalCredit = credits.reduce((s, c) => s + c, 0)
  const EPSILON = 1e-6
  return {
    totalDebit,
    totalCredit,
    isBalanced: Math.abs(totalDebit - totalCredit) < EPSILON,
  }
}

/**
 * 减值金额有效性校验：减值金额 ∈ [0, 账面价值]
 * impairment >= 0 且 impairment <= bookValue 时有效
 */
export function calcImpairmentValid(impairment: number, bookValue: number): boolean {
  return impairment >= 0 && impairment <= bookValue
}

/**
 * 截止测试日期差（天数）：|记账日 - 单据日|
 * 返回绝对天数差
 */
export function calcDateDiffDays(recordDate: Date, documentDate: Date): number {
  const MS_PER_DAY = 86400000
  const diffMs = Math.abs(recordDate.getTime() - documentDate.getTime())
  return Math.floor(diffMs / MS_PER_DAY)
}

/**
 * 截止测试跨期判断：日期差 > 阈值天数则为跨期
 */
export function isCrossPeriod(recordDate: Date, documentDate: Date, thresholdDays: number): boolean {
  return calcDateDiffDays(recordDate, documentDate) > thresholdDays
}

/**
 * 转入I1金额一致性：转入明细合计 === 审定表对应列
 * 返回差额，0表示一致
 */
export function calcTransferConsistency(transfers: number[], auditedTotal: number): number {
  const sum = transfers.reduce((a, b) => a + b, 0)
  return sum - auditedTotal
}
