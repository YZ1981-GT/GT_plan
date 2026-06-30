/**
 * useD2FormulaEngine — D2 应收账款共享纯函数公式引擎
 *
 * 所有函数为纯函数，无副作用，便于单元测试和 PBT。
 * 从 useD2AccountsReceivable.ts 提取并增强，供各子 composable 复用。
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Requirements: 1.2, 1.4, 1.6, 2.7, 3.4, 5.2, 7.5, 9.2, 10.3, 10.5, 12.4, 12.5, 14.2, 22.1
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
 * 适用于所有审定表行的审定金额计算（D2-1、D2-2、D2-3 等）。
 */
export function getAuditedAmount(
  unadjusted: number,
  aje: number,
  rje: number
): number {
  return unadjusted + aje + rje
}

/**
 * 变动率计算，含期初=0特殊处理：
 * - 期初=0 且 审定=0 → ''（无意义）
 * - 期初=0 且 审定≠0 → 1（100%新增）
 * - 其他 → (审定-期初)/期初
 */
export function getChangeRate(prior: number, audited: number): number | '' {
  if (prior === 0 && audited === 0) return ''
  if (prior === 0) return 1
  return (audited - prior) / prior
}

// ─── 坏账准备公式 ────────────────────────────────────────────────────────────

/**
 * 应计提坏账准备 = 余额 × 损失率
 *
 * D2-9 ECL单项计提核心公式。
 */
export function calculateProvision(balance: number, lossRate: number): number {
  return balance * lossRate
}

/**
 * 差异 = 实际账面余额 - 应计提
 *
 * 用于 D2-9 差异列计算。正值表示多提，负值表示少提。
 */
export function calculateDifference(actual: number, should: number): number {
  return actual - should
}

// ─── 质押比例公式 ────────────────────────────────────────────────────────────

/**
 * 质押比例 = 质押总额 / 应收账款审定总额
 *
 * 除以零安全处理：总额=0 时返回 0。D2-12 质押情况检查使用。
 */
export function calculatePledgeRatio(pledged: number, total: number): number {
  if (total === 0) return 0
  return pledged / total
}

// ─── 截止测试公式 ────────────────────────────────────────────────────────────

/**
 * 截止判定：收入确认日期 > 资产负债表日 → true（跨期）
 *
 * 日期比较采用字符串→Date解析，无效日期返回 false。
 * D2-14截止测试和D2-7凭证抽查跨期标记使用。
 */
export function determineCutoff(revenueDate: string, bsDate: string): boolean {
  const rev = new Date(revenueDate)
  const bs = new Date(bsDate)
  if (isNaN(rev.getTime()) || isNaN(bs.getTime())) return false
  return rev > bs
}

// ─── SUMIF 聚合公式 ─────────────────────────────────────────────────────────

/**
 * SUMIF 聚合：从行数组中按分类字段筛选，然后对值字段求和
 *
 * D2-2 明细表按"信用风险组合方式"(AI列)聚合到 D2-1 审定表的核心引擎。
 * 泛型设计，可复用于任何按分类字段聚合值的场景。
 *
 * @param rows - 数据行数组
 * @param classificationField - 用于筛选的分类字段名
 * @param classificationValue - 分类字段目标值
 * @param valueField - 需要求和的数值字段名
 * @returns 符合条件行的值字段合计
 */
export function sumif<T extends Record<string, any>>(
  rows: T[],
  classificationField: keyof T,
  classificationValue: string,
  valueField: keyof T
): number {
  return rows
    .filter(row => row[classificationField] === classificationValue)
    .reduce((sum, row) => sum + (parseNum(row[valueField]) || 0), 0)
}

// ─── ECL 迁徙率公式 ─────────────────────────────────────────────────────────

/**
 * ECL 预期信用损失率 = 各阶段迁徙率连乘
 *
 * D2-10 组合迁徙率矩阵核心公式。空数组返回 0（无数据无意义）。
 * rates.reduce((a, b) => a * b, 1)
 */
export function calculateExpectedLossRate(migrationRates: number[]): number {
  if (migrationRates.length === 0) return 0
  return migrationRates.reduce((acc, rate) => acc * rate, 1)
}

// ─── 分析程序公式 ────────────────────────────────────────────────────────────

/**
 * 周转率 = 营业收入 / 平均应收账款
 *
 * 除以零安全处理：平均应收=0 时返回 0。D2-5 分析程序使用。
 */
export function calculateTurnoverRate(revenue: number, avgReceivable: number): number {
  if (avgReceivable === 0) return 0
  return revenue / avgReceivable
}

/**
 * 周转天数 = 365 / 周转率
 *
 * 周转率=0 时返回 0（避免除以零）。D2-5 分析程序使用。
 */
export function calculateTurnoverDays(turnoverRate: number): number {
  if (turnoverRate === 0) return 0
  return 365 / turnoverRate
}

// ─── 金额格式化 ─────────────────────────────────────────────────────────────

/**
 * 审计金额格式化（会计格式）：
 * - 正数 → 千分位 + 2位小数（如 1,234.56）
 * - 负数 → 红色括号格式（如 (1,234.56)）
 * - 零值 → "-"
 *
 * 此函数为纯格式化函数，不依赖 displayPrefs store。
 * 用于需要独立于全局偏好的场景（如导出、PBT测试）。
 * 组件内建议优先使用 displayPrefs.fmtAmount（支持单位切换）。
 */
export function fmtAuditAmount(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return '-'
  if (typeof value !== 'number' || isNaN(value)) return '-'
  if (value === 0) return '-'

  const abs = Math.abs(value)
  const formatted = abs.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })

  return value < 0 ? `(${formatted})` : formatted
}
