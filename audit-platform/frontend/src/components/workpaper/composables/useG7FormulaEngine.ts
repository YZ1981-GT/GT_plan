/**
 * G7 长期股权投资(main组) — 公式引擎（借方/资产类科目 1511）
 *
 * 8个纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 *
 * 核心公式链：
 * - 借方余额：期初审定 + 借方 - 贷方（资产类科目）
 * - 审定数：未审 + AJE + RJE（G7审定表有AJE/RJE两列独立调整）
 * - 期末投资成本：期初 + 新增投资 - 处置减少
 * - 期末权益法调整：期初 + 权益法增加 - 权益法减少
 * - 账面价值：期末小计 - 期末减值准备
 * - 变动率：(current - prior) / prior，prior=0时null
 * - 借贷平衡：|SUM(debits) - SUM(credits)| < 0.01
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/ Requirements 6.2, 3.3, 5.3, 5.4, 5.5
 */

// ═══ parseNum: 安全数值转换（null/undefined/NaN/空串/'  '/'abc' → 0）═══

/**
 * 安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0; 有效数值→原值
 * @source G7公式引擎通用辅助，所有公式输入前调用
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  if (typeof v === 'string') {
    const trimmed = v.trim()
    if (trimmed === '') return 0
    const n = Number(trimmed)
    return Number.isFinite(n) ? n : 0
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ═══ P1: 借方余额 = 期初审定 + 借方 - 贷方 ═══

/**
 * 借方余额公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
 * G7为借方/资产类科目(1511长期股权投资)
 * @source G7-1审定表 期末未审列，Requirements 3.3
 */
export function calcDebitBalance(opening: number, debit: number, credit: number): number {
  return opening + debit - credit
}

// ═══ P2: 审定数 = 未审 + AJE + RJE ═══

/**
 * 审定数 = 未审数 + AJE + RJE
 * G7审定表有AJE/RJE两列独立调整（期初审定 & 期末审定均用此公式）
 * @source G7-1审定表 期初审定/期末审定列，Requirements 3.3
 */
export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

// ═══ P3: 期末投资成本 = 期初投资成本 + 新增投资 - 处置减少 ═══

/**
 * 期末投资成本 = 期初投资成本 + 新增投资 - 处置减少
 * G7-2明细表Tab4核心公式，子公司/合营/联营通用
 * @source G7-2明细表 Tab4 期末投资成本列，Requirements 5.3
 */
export function calcEndingCost(opening: number, increase: number, decrease: number): number {
  return opening + increase - decrease
}

// ═══ P4: 期末权益法调整 = 期初 + 权益法增加 - 权益法减少 ═══

/**
 * 期末权益法调整 = 期初权益法调整 + 权益法增加 - 权益法减少
 * G7-2明细表Tab4权益法科目专用（合营/联营企业使用）
 * @source G7-2明细表 Tab4 期末权益法调整列，Requirements 5.4
 */
export function calcEndingEquityAdj(opening: number, equityIncrease: number, equityDecrease: number): number {
  return opening + equityIncrease - equityDecrease
}

// ═══ P5: 期末账面价值 = 期末小计 - 期末减值准备 ═══

/**
 * 期末账面价值 = 期末小计 - 期末减值准备
 * G7-2明细表Tab4，小计=投资成本+权益法调整
 * @source G7-2明细表 Tab4 期末账面价值列，Requirements 5.5
 */
export function calcBookValue(subtotal: number, impairment: number): number {
  return subtotal - impairment
}

// ═══ P6: 变动率 = (current - prior) / prior ═══

/**
 * 变动率 = (current - prior) / prior
 * prior=0时返回null（避免除零），用于审定表变动率列
 * @source G7-1审定表 变动率列，|变动率|>20%橙色高亮，Requirements 3.5
 */
export function calcChangeRate(prior: number, current: number): number | null {
  if (prior === 0) return null
  return (current - prior) / prior
}

// ═══ P7: 借贷平衡校验 — |SUM(debits) - SUM(credits)| < 0.01 ═══

/**
 * 借贷平衡校验：|SUM(debits) - SUM(credits)| < 0.01
 * G7-3调整分录表保存前必须通过此校验
 * @source G7-3调整分录 借贷平衡校验，Requirements 6.1
 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}
