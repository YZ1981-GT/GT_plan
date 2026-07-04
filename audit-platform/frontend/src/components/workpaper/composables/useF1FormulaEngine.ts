/**
 * useF1FormulaEngine — F1 预付账款共享纯函数公式引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * 覆盖借方科目（1123预付账款/负债类）的全部公式计算需求。
 *
 * 核心差异 vs D2：借方科目期末 = 期初审定 + 借方 - 贷方（与D1/D2借方科目相反）。
 * 无坏账/无ECL/无SUMIF三分类/无截止独立sheet/无保理。
 * 新增：期后结转检查、款项性质分类、CAS14收入准则联动、双区块综合检查。
 *
 * Spec: .kiro/specs/f1-prepayment/
 * Requirements: 1.3, 1.4, 1.5, 1.6, 4.4, 10.3, 11.5
 */

// ─── 最小 DetailRow 接口（仅公式引擎需要的字段）────────────────────────────

export interface DetailRowForFormula {
  nature: string
  endAudited: number
  priorAudited: number
  agingAudited: { within1: number; y1to2: number; y2to3: number; over3: number }
}

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

// ─── 审定表公式 ──────────────────────────────────────────────────────────────

/**
 * 审定数 = 未审 + AJE + RJE
 *
 * 适用于 F1-1 审定表所有行的审定金额计算。
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

// ─── 变动分析公式 ────────────────────────────────────────────────────────────

/**
 * 变动额 = 期末审定 - 期初审定
 */
export function calcChangeAmount(current: number, prior: number): number {
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

// ─── 合计/小计公式 ──────────────────────────────────────────────────────────

/**
 * 小计/合计 = SUM(数组)
 *
 * 通用求和，适用于 F1-1/F1-2/F1-5/F1-6/F1-7 所有合计行。
 */
export function calcSubtotal(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0)
}

// ─── 期初审定余额 ───────────────────────────────────────────────────────────

/**
 * 期初审定余额 = 期初未审 + 账项调整 + 重分类调整
 *
 * F1-2 明细表 H列 = E + F + G。
 */
export function calcPriorAudited(unadjusted: number, adjustment: number, reclass: number): number {
  return unadjusted + adjustment + reclass
}

// ─── 借方科目期末余额 ───────────────────────────────────────────────────────

/**
 * 期末余额（借方科目）= 期初审定 + 贷方发生 - 借方发生
 *
 * F1-2 明细表 O列 = H + N - M。
 * 核心差异：借方科目贷方增加、借方减少（vs D2借方科目相反）。
 */
export function calcEndUnadjustedDebit(priorAudited: number, debit: number, credit: number): number {
  return priorAudited + debit - credit
}

export function calcEndBalance(priorAudited: number, debit: number, credit: number): number {
  return calcEndUnadjustedDebit(priorAudited, debit, credit)
}

// ─── 期末未审余额 ───────────────────────────────────────────────────────────

/**
 * 期末未审余额 = 期末余额 + 被审计单位重分类调整
 *
 * F1-2 明细表 Q列 = O + P。
 */
export function calcEndUnadjusted(endBalance: number, entityReclass: number): number {
  return endBalance + entityReclass
}

// ─── 期末审定数 ─────────────────────────────────────────────────────────────

/**
 * 期末审定数 = 期末未审 + 期末账项调整 + 期末重分类调整
 *
 * F1-2 明细表 T列 = Q + R + S。
 */
export function calcEndAudited(endUnadjusted: number, endAje: number, endRje: number): number {
  return endUnadjusted + endAje + endRje
}

// ─── 关联方期末余额 ─────────────────────────────────────────────────────────

/**
 * 关联方期末余额（借方科目）= 期初 + 贷方 - 借方
 *
 * F1-6 关联方检查表行内公式。与 calcEndBalance 逻辑一致，语义区分。
 */
export function calcRelatedPartyEndBalance(prior: number, debit: number, credit: number): number {
  return prior + debit - credit
}

// ─── 阈值判定 ────────────────────────────────────────────────────────────────

/**
 * 变动率绝对值是否超阈值
 *
 * 空串或'N/A'返回 false（无法判定），数值型取绝对值与阈值比较。
 * 适用于30%阈值高亮。
 */
export function isChangeRateExceeding(rate: number | '' | 'N/A', threshold: number): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}

// ─── 异常率 ─────────────────────────────────────────────────────────────────

/**
 * 异常率 = 异常笔数 / 已检查笔数 × 100%
 *
 * 已检查笔数=0时返回0。F1-7综合检查汇总使用。
 * 返回百分比值（如 15 代表 15%）。
 */
export function calcAnomalyRate(anomalyCount: number, totalChecked: number): number {
  if (totalChecked === 0) return 0
  return (anomalyCount / totalChecked) * 100
}

// ─── 按款项性质聚合 ─────────────────────────────────────────────────────────

/**
 * 按款项性质分组SUM
 *
 * 从 F1-2 明细行按 nature 列分组，对指定字段求和。
 * 适用于 F1-1 "按性质分类"区块自动取数。
 */
export function aggregateByNature(
  rows: DetailRowForFormula[],
  field: 'endAudited' | 'priorAudited'
): Record<string, number> {
  const result: Record<string, number> = {}
  for (const row of rows) {
    const key = row.nature || '其他'
    if (!result[key]) result[key] = 0
    result[key] += row[field]
  }
  return result
}

// ─── 按审定账龄聚合 ─────────────────────────────────────────────────────────

/**
 * 按审定账龄聚合：从明细行按 U~X 列聚合
 *
 * 适用于 F1-1 "按账龄分类"区块自动取数。
 */
export function aggregateByAging(
  rows: DetailRowForFormula[]
): { within1: number; y1to2: number; y2to3: number; over3: number } {
  const result = { within1: 0, y1to2: 0, y2to3: 0, over3: 0 }
  for (const row of rows) {
    result.within1 += row.agingAudited.within1
    result.y1to2 += row.agingAudited.y1to2
    result.y2to3 += row.agingAudited.y2to3
    result.over3 += row.agingAudited.over3
  }
  return result
}
