/**
 * F2-48 长库龄/呆滞/超过保质期存货明细表（对齐致同源模板）
 *
 * 结存金额 = 结存数量 × 结存单价；库龄四档数量合计应等于结存数量
 */
import { calcSubtotal } from './useF2InvValFormulaEngine'
import {
  type ImpairmentAging,
  emptyAging,
  agingTotal,
} from './useF2ImpairmentTestFormulas'

export type { ImpairmentAging }

export interface ObsoleteInventoryItem {
  id: string
  category: string
  itemCode: string
  itemName: string
  specification: string
  unit: string
  qty: number
  unitPrice: number
  aging: ImpairmentAging
  impairmentSigns: string
  provisionAmount: number
}

export interface ObsoleteInventorySheet {
  products: ObsoleteInventoryItem[]
}

export interface EnrichedObsoleteItem extends ObsoleteInventoryItem {
  endingAmount: number
  agingTotal: number
  agingMismatch: boolean
  isLongAge: boolean
  hasImpairmentSign: boolean
  highlight: boolean
}

export interface ObsoleteColumnTotals {
  qty: number
  endingAmount: number
  agingWithin1y: number
  agingY1to2: number
  agingY2to3: number
  agingOver3y: number
  provisionAmount: number
}

export const F2_48_DEFAULT_OBJECTIVE =
  '识别长库龄、呆滞及超过保质期存货，分析减值迹象，核对跌价准备计提的充分性与完整性，为 F2-47 跌价测试提供明细支撑。'

export const F2_48_TIPS = [
  '本表明细列示存在长库龄、呆滞、冷背、过时或超过保质期等减值迹象的存货结存及库龄分布。',
  '结存金额 = 结存数量 × 结存单价；库龄四档数量合计应与结存数量勾稽一致。',
  '“减值迹象”栏据盘点、库龄分析及管理层说明填列；计提跌价金额与账面已计提数比较，差异在 F2-47 进一步测试。',
  '2 年以上库龄或存在明显减值迹象的存货，应结合可变现净值评价跌价准备是否充分。',
]

export const IMPAIRMENT_SIGN_OPTIONS = [
  '无',
  '长库龄',
  '呆滞',
  '冷背',
  '过时',
  '超保质期',
  '毁损',
  '其他',
]

export function newObsoleteItemId(): string {
  return `f2obs-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyObsoleteItem(): ObsoleteInventoryItem {
  return {
    id: newObsoleteItemId(),
    category: '',
    itemCode: '',
    itemName: '',
    specification: '',
    unit: '',
    qty: 0,
    unitPrice: 0,
    aging: emptyAging(),
    impairmentSigns: '',
    provisionAmount: 0,
  }
}

export function defaultObsoleteSheet(): ObsoleteInventorySheet {
  return {
    /** 不预留空行；需要时由「+ 存货」添加 */
    products: [emptyObsoleteItem()],
  }
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

/** 是否为尚未录入的空白行 */
export function isBlankObsoleteItem(row: ObsoleteInventoryItem): boolean {
  return !(
    row.category.trim()
    || row.itemCode.trim()
    || row.itemName.trim()
    || row.specification.trim()
    || row.unit.trim()
    || n(row.qty)
    || n(row.unitPrice)
    || n(row.aging.within1y)
    || n(row.aging.y1to2)
    || n(row.aging.y2to3)
    || n(row.aging.over3y)
    || row.impairmentSigns.trim()
    || n(row.provisionAmount)
  )
}

/** 裁剪预留空行：只保留已填行；若全部空白则仅保留 1 行 */
export function pruneBlankObsoleteItems(rows: ObsoleteInventoryItem[]): ObsoleteInventoryItem[] {
  const filled = rows.filter((r) => !isBlankObsoleteItem(r))
  return filled.length ? filled : [emptyObsoleteItem()]
}

export function hasImpairmentSign(signs: string): boolean {
  const s = signs.trim()
  return s.length > 0 && s !== '无'
}

export function isLongAgeBucket(aging: ImpairmentAging): boolean {
  return n(aging.y2to3) > 0 || n(aging.over3y) > 0
}

export function enrichObsoleteItem(row: ObsoleteInventoryItem): EnrichedObsoleteItem {
  const qty = n(row.qty)
  const endingAmount = qty * n(row.unitPrice)
  const agTotal = agingTotal(row.aging)
  const agingMismatch = qty > 0 && agTotal > 0 && Math.abs(agTotal - qty) > 0.01
  const longAge = isLongAgeBucket(row.aging)
  const hasSign = hasImpairmentSign(row.impairmentSigns)
  return {
    ...row,
    endingAmount,
    agingTotal: agTotal,
    agingMismatch,
    isLongAge: longAge,
    hasImpairmentSign: hasSign,
    highlight: longAge || hasSign || n(row.provisionAmount) > 0,
  }
}

export function enrichObsoleteItems(rows: ObsoleteInventoryItem[]): EnrichedObsoleteItem[] {
  return rows.map(enrichObsoleteItem)
}

export function calcObsoleteTotals(rows: EnrichedObsoleteItem[]): ObsoleteColumnTotals {
  return {
    qty: calcSubtotal(rows.map((r) => r.qty)),
    endingAmount: calcSubtotal(rows.map((r) => r.endingAmount)),
    agingWithin1y: calcSubtotal(rows.map((r) => r.aging.within1y)),
    agingY1to2: calcSubtotal(rows.map((r) => r.aging.y1to2)),
    agingY2to3: calcSubtotal(rows.map((r) => r.aging.y2to3)),
    agingOver3y: calcSubtotal(rows.map((r) => r.aging.over3y)),
    provisionAmount: calcSubtotal(rows.map((r) => r.provisionAmount)),
  }
}

function agingFromDays(qty: number, ageDays: number): ImpairmentAging {
  const aging = emptyAging()
  if (!qty || !ageDays) return aging
  if (ageDays <= 365) aging.within1y = qty
  else if (ageDays <= 730) aging.y1to2 = qty
  else if (ageDays <= 1095) aging.y2to3 = qty
  else aging.over3y = qty
  return aging
}

export function migrateObsoleteSheet(legacy: unknown): ObsoleteInventorySheet | null {
  if (!legacy) return null

  if (typeof legacy === 'object' && legacy !== null && 'products' in legacy) {
    const sheet = legacy as ObsoleteInventorySheet
    return {
      products: pruneBlankObsoleteItems(Array.isArray(sheet.products) ? sheet.products : []),
    }
  }

  if (Array.isArray(legacy) && legacy.length) {
    const first = legacy[0] as Record<string, unknown>
    if ('rowId' in first || 'itemName' in first) {
      return {
        products: pruneBlankObsoleteItems((legacy as Array<Record<string, unknown>>).map((r) => {
          const qty = Number(r.qty || 0)
          const bookCost = Number(r.bookCost || 0)
          const unitPrice = qty ? bookCost / qty : 0
          const signs: string[] = []
          if (r.isObsolete) signs.push('呆滞')
          if (r.expired) signs.push('超保质期')
          return {
            ...emptyObsoleteItem(),
            id: String(r.rowId || newObsoleteItemId()),
            itemName: String(r.itemName || ''),
            qty,
            unitPrice,
            aging: agingFromDays(qty, Number(r.ageDays || 0)),
            impairmentSigns: signs.join('、') || String(r.impairmentSigns || r.remark || ''),
            provisionAmount: Number(r.provisionAmount || r.impairmentSuggestion || 0),
          }
        })),
      }
    }
  }

  return null
}
