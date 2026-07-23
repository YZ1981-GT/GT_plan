/**
 * I2 开发支出 — 公式引擎（纯函数，无副作用）
 * 科目：1717开发支出（借方/资产类）
 * 核心特征：CAS6五条件资本化 + I6↔I2双向联动 + I1转入 + 三角勾稽
 * Spec: .kiro/specs/i2-development-expenditure/
 *
 * 收敛（cutoff-test-architecture-convergence Wave1）：isCutoffPeriodCrossing 委托
 * cutoffCanonical.crossesByCutoffBoundary 单一真源（截止日两侧 XOR），行为等价（P8 已锁定）。
 */
import { crossesByCutoffBoundary } from './cutoffCanonical'

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
  const a = recordDate?.getTime?.()
  const b = documentDate?.getTime?.()
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 0
  const diffMs = Math.abs(a - b)
  return Math.floor(diffMs / MS_PER_DAY)
}

/**
 * 滞后天数异常：日期差 > 抽样窗口阈值（用于样本异常提示，非会计跨期判定）
 */
export function isCrossPeriod(recordDate: Date, documentDate: Date, thresholdDays: number): boolean {
  return calcDateDiffDays(recordDate, documentDate) > thresholdDays
}

/**
 * 会计跨期判定（相对资产负债表日）：
 * 单据日与记账日分处截止日两侧即为跨期。
 * - 单据到账：单据≤截止 且 记账>截止 → 本期漏记
 * - 账到单据：记账≤截止 且 单据>截止 → 本期多记
 * 两侧任一方向跨过截止日均视为跨期。
 */
export function isCutoffPeriodCrossing(
  documentDate: Date,
  recordDate: Date,
  cutoffDate: Date,
): boolean {
  // 薄封装：委托 cutoffCanonical.crossesByCutoffBoundary（截止日两侧 XOR 单一真源）。
  // Date → 本地 YYYY-MM-DD（与 canonical parseDate 的本地 0 点口径一致，避免 UTC 偏移）；
  // 非法 Date → 空串 → canonical 解析为 null → false（等价原 finite 校验）。
  const fmt = (dt: Date): string => {
    const t = dt?.getTime?.()
    if (!Number.isFinite(t)) return ''
    const y = dt.getFullYear()
    const m = String(dt.getMonth() + 1).padStart(2, '0')
    const d = String(dt.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }
  return crossesByCutoffBoundary(fmt(recordDate), fmt(documentDate), fmt(cutoffDate))
}

/**
 * 跨期金额：跨期时取单据金额（单据到账）或记账金额（账到单据），否则 0
 */
export function calcCrossPeriodAmount(isCrossing: boolean, amount: number): number {
  if (!isCrossing) return 0
  const n = Number(amount)
  return Number.isFinite(n) ? n : 0
}

/**
 * 转入I1金额一致性：转入明细合计 === 审定表对应列
 * 返回差额，0表示一致
 */
export function calcTransferConsistency(transfers: number[], auditedTotal: number): number {
  const sum = transfers.reduce((a, b) => a + b, 0)
  return sum - auditedTotal
}
