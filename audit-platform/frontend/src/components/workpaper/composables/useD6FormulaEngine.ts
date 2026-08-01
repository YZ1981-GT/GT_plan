/**
 * useD6FormulaEngine — D6 合同资产共享纯函数公式引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * 覆盖合同资产（科目1141/借方/资产类）的全部公式计算需求。
 *
 * 核心特色：
 *   - 三区块审定表：净值 = 原值 - 坏账准备（逐行跨区块联动）
 *   - ECL双组合测算：应计提 = 余额 × 损失率；差异 = 应计提 - 账面余额
 *   - 借方科目：期末未审 = 期初审定 + 借方发生 - 贷方发生
 *   - 减值准备变动：期末未审 = 期初审定 + 计提 + 其他增加 - 转回 - 核销 - 其他减少
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Requirements: 1.4, 2.3, 2.4, 2.5, 5.4, 8.3, 10.3, 13.3
 */

// ─── 数值解析 ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/空串/NaN/Infinity → 0
 *
 * 审计底稿中大量字段可能为空或无效值，统一转为数字 0 以确保公式运算不出 NaN。
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  if (!isFinite(n)) return 0
  return n
}

// ─── 审定表基础公式（D6-1 / D6-2 / D6-3 通用）────────────────────────────────

/**
 * 借方科目期末未审 = 期初审定 + 借方发生 - 贷方发生
 *
 * D6核心公式，适用于D6-2明细表第17列、D6-5关联方期末余额等。
 * 借方科目特征：借方增加、贷方减少。
 */
export function calcEndUnadjustedDebit(priorAudited: number, debit: number, credit: number): number {
  return priorAudited + debit - credit
}

/**
 * 审定数 = 未审 + AJE + RJE
 *
 * 通用审定金额计算，适用于D6-1/D6-2/D6-3所有审定列。
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

/**
 * 期末审定 = 期末未审 + 账项调整 + 重分类调整
 *
 * 与 calcAuditedAmount 逻辑相同，语义区分期末场景。
 * 适用于D6-1审定表、D6-3减值明细期末审定列。
 */
export function calcEndAudited(endUnadjusted: number, aje: number, rje: number): number {
  return endUnadjusted + aje + rje
}

// ─── 三区块审定表跨区块公式（D6-1 核心）──────────────────────────────────────

/**
 * 净值 = 原值 - 坏账准备（跨区块公式）
 *
 * D6-1三区块核心联动：区块三每行 = 区块一对应行 - 区块二对应行。
 * 适用于动态行、小计行、非流动扣减行、区块合计行。
 */
export function calcNetValue(originalValue: number, impairment: number): number {
  return originalValue - impairment
}

// ─── ECL减值测算公式（D6-8 核心）─────────────────────────────────────────────

/**
 * ECL应计提 = 审定余额 × 预期信用损失率
 *
 * D6-8减值测算表第③列公式。适用于单项计提和账龄组合计提所有行。
 */
export function calcExpectedProvision(balance: number, lossRate: number): number {
  return balance * lossRate
}

/**
 * ECL差异 = 应计提 - 账面余额
 *
 * D6-8减值测算表第⑤列公式。
 * 差异为正表示计提不足，为负表示计提过多。
 */
export function calcEclDifference(expectedProvision: number, bookBalance: number): number {
  return expectedProvision - bookBalance
}

// ─── 变动分析公式（D6-1 审定表）─────────────────────────────────────────────

/**
 * 变动额 = 期末审定 - 期初审定
 *
 * 注意参数顺序：(prior, current)，返回 current - prior。
 */
export function calcChangeAmount(prior: number, current: number): number {
  return current - prior
}

/**
 * 变动率计算，含期初=0特殊处理：
 * - 期初=0 且 期末=0 → ''（无意义，不显示）
 * - 期初=0（且期末≠0）→ 'N/A'（无法计算百分比变动）
 * - 其他 → (期末 - 期初) / 期初
 */
export function calcChangeRate(prior: number, current: number): number | '' | 'N/A' {
  if (prior === 0 && current === 0) return ''
  if (prior === 0) return 'N/A'
  return (current - prior) / prior
}

/**
 * 变动率绝对值是否超阈值
 *
 * 空串或'N/A'返回 false（无法判定），数值型取绝对值与阈值比较。
 * 适用于30%阈值高亮判定（变动率>30%红色高亮）。
 */
export function isChangeRateExceeding(rate: number | '' | 'N/A', threshold: number): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}

// ─── 合计/小计公式（多Sheet通用）────────────────────────────────────────────

/**
 * 合计 = SUM(明细行数组)
 *
 * 通用求和，适用于D6-1各区块小计/D6-2合计/D6-3小计/D6-5合计/D6-8合计。
 */
export function calcSubtotal(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0)
}

/**
 * XX小计 = 小计 - "减：列示于其他非流动资产"扣减值
 *
 * 三区块各自的区块合计行公式。
 * 例：合同资产原值小计 = 小计 - 减：列示于其他非流动资产的合同资产。
 */
export function calcBlockTotal(subtotal: number, nonCurrentDeduction: number): number {
  return subtotal - nonCurrentDeduction
}

// ─── 减值准备明细公式（D6-3）────────────────────────────────────────────────

/**
 * 减值准备期末未审 = 期初审定 + 计提 + 其他增加 - 转回 - 核销 - 其他减少
 *
 * D6-3减值准备明细表行内公式（期末未审列）。
 * 完整公式链：期初审定=未审+AJE+RJE → 期末未审=本函数 → 期末审定=期末未审+AJE+RJE
 */
export function calcImpairmentEndUnadjusted(
  priorAudited: number,
  provision: number,
  otherIncrease: number,
  reversal: number,
  writeOff: number,
  otherDecrease: number
): number {
  return priorAudited + provision + otherIncrease - reversal - writeOff - otherDecrease
}

// ─── 关联方检查公式（D6-5）──────────────────────────────────────────────────

/**
 * 关联方期末余额 = 期初余额 + 借方发生 - 贷方发生（借方科目）
 *
 * D6-5关联方检查表行内公式。与 calcEndUnadjustedDebit 逻辑一致，
 * 语义区分关联方场景。
 */
export function calcRelatedPartyEndBalance(priorBalance: number, debit: number, credit: number): number {
  return priorBalance + debit - credit
}

/**
 * 账面价值 = 期末余额 - 坏账准备
 *
 * D6-5关联方检查表 + 附注披露"账面价值"列通用公式。
 */
export function calcBookValue(endBalance: number, impairment: number): number {
  return endBalance - impairment
}

// ─── 附注披露公式 ───────────────────────────────────────────────────────────

/**
 * 比例% = 该类别金额 / 合计金额 × 100
 *
 * 附注披露（上市公司版）比例列计算。合计金额为0时安全返回0。
 */
export function calcPercentage(amount: number, total: number): number {
  if (total === 0) return 0
  return (amount / total) * 100
}
