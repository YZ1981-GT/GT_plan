/**
 * useH7FormulaEngine — H7 生产性生物资产纯函数公式引擎
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 2.1
 * Requirements: 2.3-2.5, 8.2, 10.3
 *
 * 所有函数为纯函数（无副作用），方便PBT验证。
 * 科目：1621生产性生物资产（借方/资产类）+ 累计折旧（贷方/备抵类）
 */

// ─── 审定数公式 ─────────────────────────────────────────────────────────────

/**
 * 审定数 = 未审数 + AJE调整 + RJE重分类
 * Property P1: ∀ u,a,r: calcAuditedAmount(u,a,r) === u + a + r
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

// ─── 资产类期末余额（借方科目：1621生产性生物资产-原值） ──────────────────────

/**
 * 资产类期末余额 = 期初 + 借方发生 - 贷方发生
 * Property P2: ∀ b,d,c: calcAssetEndBalance(b,d,c) === b + d - c
 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

// ─── 备抵类期末余额（贷方科目：累计折旧） ────────────────────────────────────

/**
 * 备抵类期末余额 = 期初 + 贷方发生 - 借方发生
 * Property P3: ∀ b,d,c: calcContraEndBalance(b,d,c) === b + c - d
 */
export function calcContraEndBalance(begin: number, debit: number, credit: number): number {
  return begin + credit - debit
}

// ─── 公允价值模式期末余额 ────────────────────────────────────────────────────

/**
 * 公允价值模式期末 = 期初 + 增加 - 减少 + 公允价值变动
 * Property P4: ∀ b,i,d,fc: calcFairEndBalance(b,i,d,fc) === b + i - d + fc
 */
export function calcFairEndBalance(
  begin: number,
  increase: number,
  decrease: number,
  fairChange: number,
): number {
  return begin + increase - decrease + fairChange
}

// ─── 净值公式 ────────────────────────────────────────────────────────────────

/**
 * 净值 = 原值 - 累计折旧 - 减值准备
 * Property P9: ∀ c,d,i: calcNetValue(c,d,i) === c - d - i
 */
export function calcNetValue(cost: number, accDep: number, impairment: number): number {
  return cost - accDep - impairment
}

// ─── 合计行恒等 ──────────────────────────────────────────────────────────────

/**
 * 合计 = 数组所有元素之和
 * Property P8: ∀ arr: calcSubtotal(arr) === Σarr
 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((sum, v) => sum + v, 0)
}

// ─── 变动率 ──────────────────────────────────────────────────────────────────

/**
 * 变动率(%) = (本期 - 上期) / 上期 × 100
 * Property P10: ∀ current,prior(≠0): calcChangeRate(c,p) === (c-p)/p × 100
 * prior === 0 时返回 0（避免除零）
 */
export function calcChangeRate(current: number, prior: number): number {
  if (prior === 0) return 0
  return ((current - prior) / prior) * 100
}

// ─── 价差率（关联交易） ──────────────────────────────────────────────────────

/**
 * 价差率(%) = (交易价格 - 市场价格) / 市场价格 × 100
 * marketPrice === 0 时返回 0
 */
export function calcPriceDiffRate(transPrice: number, marketPrice: number): number {
  if (marketPrice === 0) return 0
  return ((transPrice - marketPrice) / marketPrice) * 100
}

// ─── 公允价值差异率 ──────────────────────────────────────────────────────────

/**
 * 公允价值差异率(%) = (评估值 - 账面值) / 账面值 × 100
 * Property P11: ∀ assessed,book(≠0): calcFairValueDiffRate(a,b) === (a-b)/b × 100
 * bookValue === 0 时返回 0
 */
export function calcFairValueDiffRate(assessed: number, bookValue: number): number {
  if (bookValue === 0) return 0
  return ((assessed - bookValue) / bookValue) * 100
}
