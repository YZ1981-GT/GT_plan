/**
 * useD5FormulaEngine — D5 应收款项融资共享纯函数公式引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * 覆盖 FVOCI 金融资产（科目1124/借方/资产类）的全部公式计算需求。
 *
 * 核心特色：公允价值测算（贴现法）
 *   贴现利息 = 票面金额 × 市场贴现利率 × 剩余天数 ÷ 360
 *   公允价值 = 票面金额 - 贴现利息
 *
 * 审定表特殊结构：公允价值合计 = 小计 - OCI公允价值变动（非简单加总）
 *
 * Spec: .kiro/specs/d5-receivables-financing/
 * Requirements: 1.4, 2.3, 2.4, 4.3, 6.2
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

// ─── 贴现公式（D5-4 核心）──────────────────────────────────────────────────

/**
 * 贴现利息 = 票面金额 × 市场贴现利率 × 剩余天数 ÷ 360
 *
 * D5-4 公允价值测算表 I列公式。
 * 审计背景：FVOCI 金融资产以贴现法估算公允价值。
 */
export function calcDiscountInterest(faceValue: number, rate: number, days: number): number {
  return faceValue * rate * days / 360
}

/**
 * 公允价值 = 票面金额 - 贴现利息
 *
 * D5-4 公允价值测算表 J/K列公式。
 */
export function calcFairValue(faceValue: number, discountInterest: number): number {
  return faceValue - discountInterest
}

/**
 * 剩余天数 = 到期日 - 计量日（天数差）
 *
 * D5-4 公允价值测算表 G列公式。
 * 日期格式：YYYY-MM-DD。无效日期返回 0。
 */
export function calcRemainingDays(measurementDate: string, maturityDate: string): number {
  if (!measurementDate || !maturityDate) return 0
  const d1 = new Date(measurementDate)
  const d2 = new Date(maturityDate)
  if (isNaN(d1.getTime()) || isNaN(d2.getTime())) return 0
  const diffMs = d2.getTime() - d1.getTime()
  if (diffMs <= 0) return 0
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24))
}

// ─── 审定表公式（D5-1）─────────────────────────────────────────────────────

/**
 * 审定数 = 未审 + AJE + RJE
 *
 * 适用于 D5-1 审定表所有行 + D5-2 明细表期初/期末审定金额。
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

// ─── 变动分析公式 ────────────────────────────────────────────────────────────

/**
 * 变动额 = 期末审定 - 期初审定
 *
 * 注意参数顺序：current - prior。
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
 * 适用于30%阈值高亮判定。
 */
export function isChangeRateExceeding(rate: number | '' | 'N/A', threshold: number): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}

// ─── 合计/小计公式 ──────────────────────────────────────────────────────────

/**
 * 小计/合计 = SUM(数组)
 *
 * 通用求和，适用于 D5-1 小计行 / D5-2 合计行 / D5-4 合计行。
 */
export function calcSubtotal(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0)
}

/**
 * 公允价值合计 = 小计 - OCI变动
 *
 * D5-1 审定表特殊结构：应收款项融资公允价值合计 = 小计 - 减:OCI公允价值变动。
 * 此为 D5 区别于其他科目审定表的核心公式。
 */
export function calcFvTotal(subtotal: number, ociChange: number): number {
  return subtotal - ociChange
}

// ─── 明细表D5-2行内公式链 ───────────────────────────────────────────────────

/**
 * 期末余额 = 期初审定 + 本期增加 - 本期减少
 *
 * D5-2 明细表 J列 = F + H - I。
 * 借方科目：借方增加、贷方减少。
 */
export function calcEndBalance(priorAudited: number, increase: number, decrease: number): number {
  return priorAudited + increase - decrease
}

/**
 * 期末未审余额 = 期末余额 + 被审计单位重分类
 *
 * D5-2 明细表 L列 = J + K。
 */
export function calcEndUnadjusted(endBalance: number, entityReclass: number): number {
  return endBalance + entityReclass
}

/**
 * 期末审定余额 = 期末未审 + 账项调整 + 重分类调整
 *
 * D5-2 明细表 O列 = L + M + N。
 */
export function calcEndAudited(endUnadjusted: number, aje: number, rje: number): number {
  return endUnadjusted + aje + rje
}

// ─── 减值准备变动（附注披露）────────────────────────────────────────────────

/**
 * 减值准备期末 = 上年末 + 本期计提 - 收回转回 - 核销
 *
 * 附注披露（上市公司版）第(2)子节减值准备变动表行内公式。
 */
export function calcImpairmentEnd(
  priorEnd: number,
  provision: number,
  reversal: number,
  writeOff: number
): number {
  return priorEnd + provision - reversal - writeOff
}

// ─── ECL 阶段辅助 ──────────────────────────────────────────────────────

/** ECL阶段选项 */
export const ECL_STAGE_OPTIONS = ['阶段一', '阶段二', '阶段三'] as const

/**
 * 判断信用风险是否显著增加(简化规则)
 * 逾期>30天 或 明确违约标志 → 阶段二/三
 */
export function suggestEclStage(overdueDays: number, isDefault = false): string {
  if (isDefault || overdueDays > 90) return '阶段三'
  if (overdueDays > 30) return '阶段二'
  return '阶段一'
}
