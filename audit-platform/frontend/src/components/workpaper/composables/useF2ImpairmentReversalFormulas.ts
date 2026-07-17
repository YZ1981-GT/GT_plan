/**
 * F2-49 存货跌价准备转回核对表（对齐致同源模板）
 *
 * 转回金额 = 上期末已计提跌价 × (本年发出数量 ÷ 期初结存数量)，限原计提数内
 * 按发出结构分摊至营业成本、研发费用等科目，并核对勾稽
 */
import { calcSubtotal } from './useF2InvValFormulaEngine'
import {
  type ImpairmentAging,
  emptyAging,
  agingTotal,
} from './useF2ImpairmentTestFormulas'

export type { ImpairmentAging }

export interface IssuanceBreakdown {
  total: number
  production: number
  sales: number
  rnd: number
  other: number
}

export interface ReversalAccountSplit {
  costOfSales: number
  rndExpense: number
  other: number
}

export interface ImpairmentReversalItem {
  id: string
  category: string
  itemCode: string
  itemName: string
  specification: string
  unit: string
  openingQty: number
  openingUnitPrice: number
  aging: ImpairmentAging
  separateProvision: boolean
  priorProvision: number
  issuance: IssuanceBreakdown
  accountSplit: ReversalAccountSplit
}

export interface ImpairmentReversalSheet {
  products: ImpairmentReversalItem[]
}

export interface EnrichedReversalItem extends ImpairmentReversalItem {
  openingAmount: number
  agingTotal: number
  agingMismatch: boolean
  issuanceMismatch: boolean
  reversalTotal: number
  effectiveCostOfSales: number
  effectiveRndExpense: number
  effectiveOther: number
  verificationDiff: number
  verifyOk: boolean
  highlight: boolean
}

export interface ReversalColumnTotals {
  openingQty: number
  openingAmount: number
  priorProvision: number
  issuanceTotal: number
  reversalTotal: number
  costOfSales: number
  rndExpense: number
  other: number
}

export const F2_49_DEFAULT_OBJECTIVE =
  '核对存货跌价准备转回金额是否与原计提数、本年发出数量相匹配，并按发出用途分摊至营业成本、研发费用等科目，验证转回计入当期损益的准确性。'

export const F2_49_TIPS = [
  '以前减记存货价值的影响因素已经消失的，减记的金额予以恢复，并在原已计提的存货跌价准备金额内转回，转回的金额计入当期损益。',
  '转回金额通常按本年发出数量占期初结存数量的比例，对应转销上期末已计提的跌价准备。',
  '发出数量应分解为生产领用、销售、研发领用等，转回金额按相同比例分摊至营业成本、研发费用等科目。',
  '转回金额核对 = 跌价转回合计 − 各科目转回金额之和，差异应接近于零。',
]

export function newReversalItemId(): string {
  return `f2rev-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyIssuance(): IssuanceBreakdown {
  return { total: 0, production: 0, sales: 0, rnd: 0, other: 0 }
}

export function emptyAccountSplit(): ReversalAccountSplit {
  return { costOfSales: 0, rndExpense: 0, other: 0 }
}

export function emptyReversalItem(): ImpairmentReversalItem {
  return {
    id: newReversalItemId(),
    category: '',
    itemCode: '',
    itemName: '',
    specification: '',
    unit: '',
    openingQty: 0,
    openingUnitPrice: 0,
    aging: emptyAging(),
    separateProvision: true,
    priorProvision: 0,
    issuance: emptyIssuance(),
    accountSplit: emptyAccountSplit(),
  }
}

export function defaultReversalSheet(): ImpairmentReversalSheet {
  return {
    products: Array.from({ length: 10 }, () => emptyReversalItem()),
  }
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

export function calcReversalTotal(row: ImpairmentReversalItem): number {
  if (!row.separateProvision) return 0
  const openQty = n(row.openingQty)
  const prior = n(row.priorProvision)
  const issued = n(row.issuance.total)
  if (!openQty || !prior || !issued) return 0
  const ratio = Math.min(1, issued / openQty)
  return prior * ratio
}

export function calcEffectiveAccountSplit(
  row: ImpairmentReversalItem,
  reversalTotal: number,
): ReversalAccountSplit {
  const manual = row.accountSplit
  const manualSum = n(manual.costOfSales) + n(manual.rndExpense) + n(manual.other)
  if (manualSum > 0) {
    return {
      costOfSales: n(manual.costOfSales),
      rndExpense: n(manual.rndExpense),
      other: n(manual.other),
    }
  }

  const issued = n(row.issuance.total)
  if (!issued || !reversalTotal) {
    return { costOfSales: reversalTotal, rndExpense: 0, other: 0 }
  }

  const prod = n(row.issuance.production)
  const sales = n(row.issuance.sales)
  const rnd = n(row.issuance.rnd)
  const other = n(row.issuance.other)
  const breakdownSum = prod + sales + rnd + other

  if (breakdownSum > 0) {
    return {
      costOfSales: reversalTotal * (prod + sales) / breakdownSum,
      rndExpense: reversalTotal * rnd / breakdownSum,
      other: reversalTotal * other / breakdownSum,
    }
  }

  return { costOfSales: reversalTotal, rndExpense: 0, other: 0 }
}

export function enrichReversalItem(row: ImpairmentReversalItem): EnrichedReversalItem {
  const openingQty = n(row.openingQty)
  const openingAmount = openingQty * n(row.openingUnitPrice)
  const agTotal = agingTotal(row.aging)
  const agingMismatch = openingQty > 0 && agTotal > 0 && Math.abs(agTotal - openingQty) > 0.01

  const breakdownSum =
    n(row.issuance.production) +
    n(row.issuance.sales) +
    n(row.issuance.rnd) +
    n(row.issuance.other)
  const issuedTotal = n(row.issuance.total)
  const issuanceMismatch =
    issuedTotal > 0 &&
    breakdownSum > 0 &&
    Math.abs(breakdownSum - issuedTotal) > 0.01

  const reversalTotal = calcReversalTotal(row)
  const accounts = calcEffectiveAccountSplit(row, reversalTotal)
  const allocated = accounts.costOfSales + accounts.rndExpense + accounts.other
  const verificationDiff = reversalTotal - allocated
  const verifyOk = Math.abs(verificationDiff) < 0.01

  return {
    ...row,
    openingAmount,
    agingTotal: agTotal,
    agingMismatch,
    issuanceMismatch,
    reversalTotal,
    effectiveCostOfSales: accounts.costOfSales,
    effectiveRndExpense: accounts.rndExpense,
    effectiveOther: accounts.other,
    verificationDiff,
    verifyOk,
    highlight: reversalTotal > 0 && (!verifyOk || issuanceMismatch),
  }
}

export function enrichReversalItems(rows: ImpairmentReversalItem[]): EnrichedReversalItem[] {
  return rows.map(enrichReversalItem)
}

export function calcReversalTotals(rows: EnrichedReversalItem[]): ReversalColumnTotals {
  return {
    openingQty: calcSubtotal(rows.map((r) => r.openingQty)),
    openingAmount: calcSubtotal(rows.map((r) => r.openingAmount)),
    priorProvision: calcSubtotal(rows.map((r) => r.priorProvision)),
    issuanceTotal: calcSubtotal(rows.map((r) => r.issuance.total)),
    reversalTotal: calcSubtotal(rows.map((r) => r.reversalTotal)),
    costOfSales: calcSubtotal(rows.map((r) => r.effectiveCostOfSales)),
    rndExpense: calcSubtotal(rows.map((r) => r.effectiveRndExpense)),
    other: calcSubtotal(rows.map((r) => r.effectiveOther)),
  }
}

export function migrateReversalSheet(legacy: unknown): ImpairmentReversalSheet | null {
  if (!legacy) return null

  if (typeof legacy === 'object' && legacy !== null && 'products' in legacy) {
    const sheet = legacy as ImpairmentReversalSheet
    return {
      products: sheet.products?.length ? sheet.products : defaultReversalSheet().products,
    }
  }

  if (Array.isArray(legacy) && legacy.length) {
    const first = legacy[0] as Record<string, unknown>
    if ('rowId' in first || 'itemName' in first) {
      return {
        products: (legacy as Array<Record<string, unknown>>).map((r) => ({
          ...emptyReversalItem(),
          id: String(r.rowId || newReversalItemId()),
          itemName: String(r.itemName || ''),
          openingQty: Number(r.openingQty || 0) || 1,
          openingUnitPrice: Number(r.openingUnitPrice || 0) ||
            (Number(r.bookCost || 0) / (Number(r.openingQty || 0) || 1)),
          priorProvision: Number(r.priorProvision || 0),
          separateProvision: true,
          issuance: {
            ...emptyIssuance(),
            total: Number(r.issuanceTotal || r.issuedQty || 0),
          },
          accountSplit: {
            costOfSales: Number(r.reversalAmount || 0),
            rndExpense: 0,
            other: 0,
          },
        })),
      }
    }
  }

  return null
}
