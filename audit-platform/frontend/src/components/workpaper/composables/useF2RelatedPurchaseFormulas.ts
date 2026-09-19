/**
 * F2-52 存货关联采购分析表（对齐致同源模板）
 */
import { calcSubtotal } from './useF2InvValFormulaEngine'

export interface RelatedPurchaseItem {
  id: string
  relatedPartyName: string
  relationship: string
  itemNameSpec: string
  unit: string
  relatedQty: number
  relatedAmount: number
  totalQty: number
  totalAmount: number
  priorQtyRatio: number
  priorAmtRatio: number
  nonRelatedAvgPrice: number
  priorAvgPrice: number
  indexRef: string
}

export interface RelatedPurchaseAuditNotes {
  weightDescription: string
  weightChangeReason: string
  priceAbnormalReason: string
  undisclosedParty: string
}

export interface RelatedPurchaseSheet {
  auditNotes: RelatedPurchaseAuditNotes
  products: RelatedPurchaseItem[]
}

export interface EnrichedRelatedPurchase extends RelatedPurchaseItem {
  relatedUnitPrice: number
  currentQtyRatio: number
  currentAmtRatio: number
  priceVarianceRate: number | null
  isHighVariance: boolean
  highlight: boolean
}

export interface RelatedPurchaseTotals {
  relatedQty: number
  relatedAmount: number
  totalQty: number
  totalAmount: number
  currentQtyRatio: number
  currentAmtRatio: number
  relatedUnitPrice: number
}

export const F2_52_DEFAULT_OBJECTIVE =
  '分析向关联方采购存货的规模、占比及定价公允性，识别显著偏离非关联方采购均价的关联交易，评价关联采购披露与舞弊风险。'

export const F2_52_AUDIT_NOTE_LABELS = [
  '1. 关联采购比重说明（占同类采购数量/金额的比例及总体评价）；',
  '2. 关联采购比重较上年变动较大的原因；',
  '3. 关联采购价格异常的原因（公允性测试索引参见 F2-65、F2-66）；',
  '4. 如存在舞弊迹象，是否识别出未披露的关联方（索引参见 F2-67）。',
] as const

export const F2_52_TIPS = [
  '本年关联交易占比 = 本年关联采购 ÷ 本年采购总量（数量或金额分别计算）。',
  '关联采购单价 = 关联采购金额 ÷ 关联采购数量；单价差异率 = (关联单价 − 非关联方均价) ÷ 非关联方均价。',
  '合计行应对数量、金额求和，并重新计算占比；上年占比列为管理层提供或上年度底稿结转。',
  '关注关联采购定价是否公允、是否需按 CAS 36 号披露，异常价格须交叉索引公允性测试底稿。',
]

export const RELATIONSHIP_OPTIONS = [
  '母公司',
  '子公司',
  '同一母公司',
  '联营企业',
  '合营企业',
  '关键管理人员及其亲属',
  '其他关联方',
]

export function newRelatedPurchaseId(): string {
  return `f2rp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyAuditNotes(): RelatedPurchaseAuditNotes {
  return {
    weightDescription: '',
    weightChangeReason: '',
    priceAbnormalReason: '',
    undisclosedParty: '',
  }
}

export function emptyRelatedPurchaseItem(): RelatedPurchaseItem {
  return {
    id: newRelatedPurchaseId(),
    relatedPartyName: '',
    relationship: '',
    itemNameSpec: '',
    unit: '',
    relatedQty: 0,
    relatedAmount: 0,
    totalQty: 0,
    totalAmount: 0,
    priorQtyRatio: 0,
    priorAmtRatio: 0,
    nonRelatedAvgPrice: 0,
    priorAvgPrice: 0,
    indexRef: '',
  }
}

export function defaultRelatedPurchaseSheet(): RelatedPurchaseSheet {
  return {
    auditNotes: emptyAuditNotes(),
    products: [emptyRelatedPurchaseItem()],
  }
}

export function isBlankRelatedPurchaseItem(row: RelatedPurchaseItem): boolean {
  return !row.relatedPartyName.trim()
    && !row.relationship.trim()
    && !row.itemNameSpec.trim()
    && !row.unit.trim()
    && !row.relatedQty
    && !row.relatedAmount
    && !row.totalQty
    && !row.totalAmount
    && !row.priorQtyRatio
    && !row.priorAmtRatio
    && !row.nonRelatedAvgPrice
    && !row.priorAvgPrice
    && !row.indexRef.trim()
}

export function pruneBlankRelatedPurchaseItems(
  products: RelatedPurchaseItem[],
): RelatedPurchaseItem[] {
  const filled = products.filter((row) => !isBlankRelatedPurchaseItem(row))
  return filled.length ? filled : [products[0] || emptyRelatedPurchaseItem()]
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

export function calcRatio(part: number, whole: number): number {
  if (!whole) return 0
  return part / whole
}

export function calcPriceVariance(relatedUnit: number, benchmark: number): number | null {
  if (!benchmark) return null
  return (relatedUnit - benchmark) / benchmark
}

export function enrichRelatedPurchaseItem(row: RelatedPurchaseItem): EnrichedRelatedPurchase {
  const relatedQty = n(row.relatedQty)
  const relatedAmount = n(row.relatedAmount)
  const relatedUnitPrice = relatedQty ? relatedAmount / relatedQty : 0
  const currentQtyRatio = calcRatio(relatedQty, n(row.totalQty))
  const currentAmtRatio = calcRatio(relatedAmount, n(row.totalAmount))
  const priceVarianceRate = calcPriceVariance(relatedUnitPrice, n(row.nonRelatedAvgPrice))
  const isHighVariance = priceVarianceRate != null && Math.abs(priceVarianceRate) > 0.1

  return {
    ...row,
    relatedUnitPrice,
    currentQtyRatio,
    currentAmtRatio,
    priceVarianceRate,
    isHighVariance,
    highlight: isHighVariance,
  }
}

export function enrichRelatedPurchases(rows: RelatedPurchaseItem[]): EnrichedRelatedPurchase[] {
  return rows.map(enrichRelatedPurchaseItem)
}

export function calcRelatedPurchaseTotals(rows: EnrichedRelatedPurchase[]): RelatedPurchaseTotals {
  const relatedQty = calcSubtotal(rows.map((r) => r.relatedQty))
  const relatedAmount = calcSubtotal(rows.map((r) => r.relatedAmount))
  const totalQty = calcSubtotal(rows.map((r) => r.totalQty))
  const totalAmount = calcSubtotal(rows.map((r) => r.totalAmount))
  return {
    relatedQty,
    relatedAmount,
    totalQty,
    totalAmount,
    currentQtyRatio: calcRatio(relatedQty, totalQty),
    currentAmtRatio: calcRatio(relatedAmount, totalAmount),
    relatedUnitPrice: relatedQty ? relatedAmount / relatedQty : 0,
  }
}

export function migrateRelatedPurchaseSheet(legacy: unknown): RelatedPurchaseSheet | null {
  if (!legacy) return null

  if (typeof legacy === 'object' && legacy !== null && 'products' in legacy) {
    const sheet = legacy as RelatedPurchaseSheet
    return {
      ...defaultRelatedPurchaseSheet(),
      ...sheet,
      auditNotes: { ...emptyAuditNotes(), ...sheet.auditNotes },
      products: pruneBlankRelatedPurchaseItems(
        Array.isArray(sheet.products) ? sheet.products : [],
      ),
    }
  }

  if (Array.isArray(legacy) && legacy.length) {
    const first = legacy[0] as Record<string, unknown>
    if ('rowId' in first || 'relatedParty' in first) {
      return {
        auditNotes: emptyAuditNotes(),
        products: pruneBlankRelatedPurchaseItems((legacy as Array<Record<string, unknown>>).map((r) => {
          const qty = Number(r.quantity || r.relatedQty || 0)
          const price = Number(r.relatedPrice || 0)
          const amount = Number(r.relatedAmount || 0) || qty * price
          return {
            ...emptyRelatedPurchaseItem(),
            id: String(r.rowId || newRelatedPurchaseId()),
            relatedPartyName: String(r.relatedParty || r.relatedPartyName || ''),
            itemNameSpec: String(r.itemName || r.itemNameSpec || ''),
            relatedQty: qty,
            relatedAmount: amount,
            nonRelatedAvgPrice: Number(r.comparablePrice || r.nonRelatedAvgPrice || 0),
            indexRef: String(r.indexRef || ''),
          }
        })),
      }
    }
  }

  return null
}
