/**
 * F2 计价减值组 — 扩展公式引擎
 * Spec: .kiro/specs/f2-inventory-valuation-impairment/ Task 2.1
 * 复用 useF2InvMaiFormulaEngine 基础函数
 */
export {
  parseNum,
  calcSubtotal,
  calcChangeRate,
  calcChangeAmount,
} from './useF2InvMaiFormulaEngine'

import { parseNum, calcChangeRate } from './useF2InvMaiFormulaEngine'

/** NRV = 售价 - 完工成本 - 销售费用 - 销售税金 */
export function calcNRV(
  sellingPrice: number,
  completionCost: number,
  sellingExpense: number,
  tax: number,
): number {
  return sellingPrice - completionCost - sellingExpense - tax
}

/** 应计提跌价 = MAX(0, 账面成本 - NRV) */
export function calcImpairmentProvision(bookCost: number, nrv: number): number {
  return Math.max(0, bookCost - nrv)
}

/** 加权平均单价 = (期初金额+入库金额)/(期初数量+入库数量) */
export function calcWeightedAvgPrice(
  openingAmt: number,
  inboundAmt: number,
  openingQty: number,
  inboundQty: number,
): number {
  const totalQty = openingQty + inboundQty
  if (totalQty === 0) return 0
  return (openingAmt + inboundAmt) / totalQty
}

export function calcStandardCost(stdPrice: number, stdQty: number): number {
  return stdPrice * stdQty
}

export function calcPriceVariance(
  actualPrice: number,
  stdPrice: number,
  actualQty: number,
): number {
  return (actualPrice - stdPrice) * actualQty
}

export function calcQuantityVariance(
  actualQty: number,
  stdQty: number,
  stdPrice: number,
): number {
  return (actualQty - stdQty) * stdPrice
}

export function calcTotalVariance(
  actualPrice: number,
  actualQty: number,
  stdPrice: number,
  stdQty: number,
): number {
  return actualPrice * actualQty - stdPrice * stdQty
}

/** 转回金额 = MIN(MAX(0, 已计提-应计提), 转回上限) */
export function calcReversalAmount(
  existingProvision: number,
  requiredProvision: number,
  reversalCap: number,
): number {
  const raw = Math.max(0, existingProvision - requiredProvision)
  return Math.min(raw, reversalCap)
}

export function calcAllocationRatio(itemBase: number, totalBase: number): number {
  if (totalBase === 0) return 0
  return (itemBase / totalBase) * 100
}

export function calcFairnessDeviation(
  relatedPrice: number,
  comparablePrice: number,
): number | 'N/A' {
  if (comparablePrice === 0) return 'N/A'
  return ((relatedPrice - comparablePrice) / comparablePrice) * 100
}

export function isExpired(ageDays: number, shelfDays: number): boolean {
  return ageDays > shelfDays
}

export function calcRemainingShelfDays(ageDays: number, shelfDays: number): number {
  return shelfDays - ageDays
}

export function calcVarianceRate(bookAmt: number, auditAmt: number): number | '' | 'N/A' {
  return calcChangeRate(bookAmt, auditAmt)
}

export function isVarianceExceeding(
  rate: number | '' | 'N/A',
  thresholdPct: number,
): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > thresholdPct / 100
}
