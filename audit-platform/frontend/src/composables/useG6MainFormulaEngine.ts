/**
 * G6 其他债权投资(main组) — 公式引擎
 *
 * 科目1503 其他债权投资（借方/资产类）
 * 计量属性：以公允价值计量且变动计入其他综合收益（FVOCI-Debt）
 *
 * 10个纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 * 所有数值结果保留2位小数（Math.round(x * 100) / 100），变动率保留4位小数。
 *
 * **双重计量特征**：
 * - 账面价值同时受公允价值变动(OCI)和ECL减值(损益)影响
 * - 审定表需同时反映公允价值调整和减值准备
 *
 * 核心公式：
 * - P1: 借方余额 — 期末未审 = 期初审定 + 借方 - 贷方
 * - P2: 审定数 = 未审数 + 调整(AJE+RJE合并)
 * - P3: 余额小计 = 成本 + 利息调整 + 应计利息（G6-1四组/G6-2期初小计）
 * - P4: 期末小计 = 期初小计 + 增加 - 减少 + 利息收入（G6-2明细表）
 * - P5a: 未审坏账准备 = 账面余额 × 信用损失率
 * - P5b: 坏账调整 = 余额调整×调整后损失率 + 账面余额×(调整后损失率-原损失率)
 * - P5c: 审定账面价值 = 审定余额 - 审定坏账
 * - P6: 变动率 = (current - prior) / prior，prior=0返回null
 * - P7: 借贷平衡 — |SUM(debits) - SUM(credits)| < 0.01
 * - P8: 报表列示数 = 小计 + 公允价值变动 - 减值准备（G6-1七组）
 *
 * ECL公式链推导（G6-3核心）：
 * - ③ = ① × ②
 * - ⑥ = ⑤×②A + ①×(②A-②)
 * - ⑦ = ① + ⑤
 * - ⑧ = ③ + ⑥ = ⑦×②A（恒等式）
 * - ⑨ = ⑦ - ⑧ = ⑦(1-②A)
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/ Requirements 8.1~8.10
 */

// ═══ parseNum: 安全数值转换（null/undefined/NaN/空串 → 0）═══

/** 安全数值转换：null/undefined/''/NaN → 0，有限数值原样返回 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ═══ P1: 借方余额公式 — 期末未审 = 期初审定 + 借方 - 贷方 ═══

/** P1: 借方余额公式（G6为借方/资产类科目1503） */
export function calcDebitBalance(opening: number, debit: number, credit: number): number {
  return Math.round((parseNum(opening) + parseNum(debit) - parseNum(credit)) * 100) / 100
}

// ═══ P2: 审定数 = 未审数 + 调整(AJE+RJE合并) ═══

/** P2: 审定数 = 未审数 + 调整 */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number {
  return Math.round((parseNum(unadjusted) + parseNum(adjustment)) * 100) / 100
}

// ═══ P3: 余额小计 = 成本 + 利息调整 + 应计利息 ═══

/** P3: 余额小计（G6-1审定表四组 / G6-2明细表期初小计） */
export function calcSubtotal(cost: number, interestAdj: number, accruedInterest: number): number {
  return Math.round((parseNum(cost) + parseNum(interestAdj) + parseNum(accruedInterest)) * 100) / 100
}

// ═══ P4: 期末小计 = 期初小计 + 增加 - 减少 + 利息收入 ═══

/** P4: 期末小计（G6-2明细表核心公式） */
export function calcEndingSubtotal(
  openingSubtotal: number, increase: number, decrease: number, interestIncome: number
): number {
  return Math.round((parseNum(openingSubtotal) + parseNum(increase) - parseNum(decrease) + parseNum(interestIncome)) * 100) / 100
}

// ═══ P5a: 未审坏账准备 = 账面余额 × 信用损失率 ═══

/** P5a: 未审坏账准备（G6-3 ③=①×②） */
export function calcUnadjustedProvision(bookBalance: number, creditLossRate: number): number {
  return Math.round(parseNum(bookBalance) * parseNum(creditLossRate) * 100) / 100
}

// ═══ P5b: 坏账调整 = 余额调整×调整后损失率 + 账面余额×(调整后损失率-原损失率) ═══

/** P5b: 坏账调整（G6-3 ⑥=⑤×②A+①×(②A-②)，可负） */
export function calcImpairmentAdjustment(
  balanceAdj: number, adjRate: number, origBalance: number, origRate: number
): number {
  const ba = parseNum(balanceAdj)
  const ar = parseNum(adjRate)
  const ob = parseNum(origBalance)
  const or_ = parseNum(origRate)
  return Math.round((ba * ar + ob * (ar - or_)) * 100) / 100
}

// ═══ P5c: 审定账面价值 = 审定余额 - 审定坏账 ═══

/** P5c: 审定账面价值（G6-3 ⑨=⑦-⑧） */
export function calcAdjustedBookValue(adjustedBalance: number, adjustedProvision: number): number {
  return Math.round((parseNum(adjustedBalance) - parseNum(adjustedProvision)) * 100) / 100
}

// ═══ P6: 变动率 = (current - prior) / prior，prior≈0时返回null ═══

/** P6: 变动率（4位小数百分比），prior≈0时返回null避免除零 */
export function calcChangeRate(prior: number, current: number): number | null {
  const p = parseNum(prior)
  const c = parseNum(current)
  if (Math.abs(p) < 0.001) return null
  return Math.round(((c - p) / p) * 10000) / 10000
}

// ═══ P7: 借贷平衡校验 — |SUM(debits) - SUM(credits)| < 0.01 ═══

/** P7: 借贷平衡校验（G6-4调整分录） */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}

// ═══ P8: 报表列示数 = 小计 + 公允价值变动 - 减值准备 ═══

/** P8: 报表列示数（G6-1审定表七组公式） */
export function calcReportAmount(subtotal: number, fvChange: number, impairment: number): number {
  return Math.round((parseNum(subtotal) + parseNum(fvChange) - parseNum(impairment)) * 100) / 100
}
