/**
 * F2-47 存货跌价准备测试表（对齐致同源模板）
 *
 * 逻辑：成本与可变现净值孰低；NRV = 估计售价×数量 − 至完工成本 − 销售费用 − 税费
 */
import { calcNRV, calcImpairmentProvision, calcSubtotal } from './useF2InvValFormulaEngine'

export interface ImpairmentAging {
  within1y: number
  y1to2: number
  y2to3: number
  over3y: number
}

export interface ImpairmentSamplingMeta {
  auditObject: string
  sampleCriteria: string
  samplingMethod: string
  samplingProcess: string
}

export interface ImpairmentTestProductRow {
  id: string
  category: string
  itemCode: string
  itemName: string
  unit: string
  qty: number
  bookCost: number
  aging: ImpairmentAging
  inventoryStatus: string
  holdingPurpose: string
  sellingExpenseRate: number
  taxRate: number
  pricePreContract: number
  priceContract: number
  priceBasisIndex: string
  completionCost: number
  sellingExpense: number
  relatedTax: number
  bookedProvision: number
  remark: string
}

export interface ImpairmentTestSheet {
  sampling: ImpairmentSamplingMeta
  auditProcedure: string
  products: ImpairmentTestProductRow[]
}

export interface EnrichedImpairmentProduct extends ImpairmentTestProductRow {
  bookUnitCost: number
  effectiveUnitPrice: number
  computedSellingExpense: number
  computedRelatedTax: number
  nrv: number
  requiredProvision: number
  auditedAmount: number
  additionalProvision: number
  reversal: number
  agingTotal: number
  agingMismatch: boolean
  needsRemark: boolean
}

export interface ImpairmentColumnTotals {
  qty: number
  bookCost: number
  nrv: number
  requiredProvision: number
  auditedAmount: number
  bookedProvision: number
  additionalProvision: number
}

export interface ImpairmentCategorySummary {
  category: string
  bookCost: number
  auditedProvision: number
  auditAdjustment: number
  provisionRatio: number
}

export const F2_47_OBJECTIVES = [
  '获取被审计单位年末存货明细，确保存货计价正确、计量恰当。',
  '选取样本重新测算可变现净值，与账面成本比较，评价跌价准备计提的充分性与准确性。',
]

export const F2_47_DEFAULT_PROCEDURE = [
  '1. 了解被审计单位存货跌价准备计提政策，评价其是否符合企业会计准则的规定；',
  '2. 获取存货跌价准备计算表，检查计提依据、计算过程及审批记录；',
  '3. 对原材料与产成品分别选取样本，重新计算可变现净值；',
  '4. 结合库龄分析、盘点结果，关注长库龄、呆滞、毁损及超过保质期存货；',
  '5. 比较样本账面已计提跌价准备与应计提金额，确定应补提或应转回金额；',
  '6. 检查存货跌价准备的披露是否充分、适当。',
].join('\n')

export const F2_47_TIPS = [
  '存货期末按成本与可变现净值孰低计量，每年末均须进行减值测试，不仅限于存在减值迹象时。',
  '可变现净值 = 估计售价 − 至完工时估计将要发生的成本 − 估计的销售费用 − 相关税费；有合同的按合同价，无合同的按资产负债表日前后的市场售价。',
  '跌价准备通常按单个存货项目计提；数量多、单价低的存货可按类别计提。',
  '结合库龄分析、盘点结果识别呆滞、毁损、过期存货；关注存货余额与订单、期后销售及下年度预算的匹配性。',
  '以前减记因素消失的，在原已计提金额内转回；合并报表须抵消集团内购进存货已计提的跌价准备。',
]

export const SAMPLING_METHOD_OPTIONS = ['随机抽样', '系统抽样', '判断抽样', '全查', '其他']

export const INVENTORY_STATUS_OPTIONS = ['正常', '呆滞', '毁损', '过期', '滞销', '其他']
export const HOLDING_PURPOSE_OPTIONS = ['出售', '生产领用', '加工', '其他']

export function newImpairmentProductId(): string {
  return `f2imp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyAging(): ImpairmentAging {
  return { within1y: 0, y1to2: 0, y2to3: 0, over3y: 0 }
}

export function emptyImpairmentProduct(): ImpairmentTestProductRow {
  return {
    id: newImpairmentProductId(),
    category: '',
    itemCode: '',
    itemName: '',
    unit: '',
    qty: 0,
    bookCost: 0,
    aging: emptyAging(),
    inventoryStatus: '',
    holdingPurpose: '',
    sellingExpenseRate: 0,
    taxRate: 0,
    pricePreContract: 0,
    priceContract: 0,
    priceBasisIndex: '',
    completionCost: 0,
    sellingExpense: 0,
    relatedTax: 0,
    bookedProvision: 0,
    remark: '',
  }
}

export function defaultImpairmentSheet(): ImpairmentTestSheet {
  return {
    sampling: {
      auditObject: '',
      sampleCriteria: '',
      samplingMethod: '',
      samplingProcess: '',
    },
    auditProcedure: F2_47_DEFAULT_PROCEDURE,
    /** 不预留空行；需要时由「+ 样本」添加 */
    products: [emptyImpairmentProduct()],
  }
}

/** 是否为尚未录入的空白样本行 */
export function isBlankProduct(row: ImpairmentTestProductRow): boolean {
  return !(
    row.category.trim()
    || row.itemCode.trim()
    || row.itemName.trim()
    || row.unit.trim()
    || n(row.qty)
    || n(row.bookCost)
    || n(row.aging.within1y)
    || n(row.aging.y1to2)
    || n(row.aging.y2to3)
    || n(row.aging.over3y)
    || row.inventoryStatus.trim()
    || row.holdingPurpose.trim()
    || n(row.sellingExpenseRate)
    || n(row.taxRate)
    || n(row.pricePreContract)
    || n(row.priceContract)
    || row.priceBasisIndex.trim()
    || n(row.completionCost)
    || n(row.sellingExpense)
    || n(row.relatedTax)
    || n(row.bookedProvision)
    || row.remark.trim()
  )
}

/**
 * 裁剪预留空行：只保留已填样本；若全部空白则仅保留 1 行。
 * 不再预留多行空壳，需要时由「+ 样本」添加。
 */
export function pruneBlankProducts(products: ImpairmentTestProductRow[]): ImpairmentTestProductRow[] {
  const filled = products.filter((p) => !isBlankProduct(p))
  return filled.length ? filled : [emptyImpairmentProduct()]
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

export function agingTotal(aging: ImpairmentAging): number {
  return n(aging.within1y) + n(aging.y1to2) + n(aging.y2to3) + n(aging.over3y)
}

export function effectiveUnitPrice(row: ImpairmentTestProductRow): number {
  const contract = n(row.priceContract)
  const market = n(row.pricePreContract)
  return contract > 0 ? contract : market
}

export function resolveSellingExpense(row: ImpairmentTestProductRow, unitPrice: number): number {
  const manual = n(row.sellingExpense)
  if (manual > 0) return manual
  const rate = n(row.sellingExpenseRate)
  if (rate > 0 && unitPrice > 0 && n(row.qty) > 0) {
    return unitPrice * n(row.qty) * (rate / 100)
  }
  return 0
}

export function resolveRelatedTax(row: ImpairmentTestProductRow, unitPrice: number): number {
  const manual = n(row.relatedTax)
  if (manual > 0) return manual
  const rate = n(row.taxRate)
  if (rate > 0 && unitPrice > 0 && n(row.qty) > 0) {
    return unitPrice * n(row.qty) * (rate / 100)
  }
  return 0
}

export function enrichImpairmentProduct(row: ImpairmentTestProductRow): EnrichedImpairmentProduct {
  const qty = n(row.qty)
  const bookCost = n(row.bookCost)
  const bookUnitCost = qty ? bookCost / qty : 0
  const unitPrice = effectiveUnitPrice(row)
  const grossRevenue = unitPrice * qty
  const sellingExp = resolveSellingExpense(row, unitPrice)
  const tax = resolveRelatedTax(row, unitPrice)
  const nrv = calcNRV(grossRevenue, n(row.completionCost), sellingExp, tax)
  const requiredProvision = calcImpairmentProvision(bookCost, nrv)
  const auditedAmount = bookCost - requiredProvision
  const booked = n(row.bookedProvision)
  const additionalProvision = Math.max(0, requiredProvision - booked)
  const reversal = Math.max(0, booked - requiredProvision)
  const agTotal = agingTotal(row.aging)
  const agingMismatch = qty > 0 && agTotal > 0 && Math.abs(agTotal - qty) > 0.01

  return {
    ...row,
    bookUnitCost,
    effectiveUnitPrice: unitPrice,
    computedSellingExpense: sellingExp,
    computedRelatedTax: tax,
    nrv,
    requiredProvision,
    auditedAmount,
    additionalProvision,
    reversal,
    agingTotal: agTotal,
    agingMismatch,
    needsRemark: requiredProvision > 0 && !row.remark.trim(),
  }
}

export function enrichImpairmentProducts(rows: ImpairmentTestProductRow[]): EnrichedImpairmentProduct[] {
  return rows.map(enrichImpairmentProduct)
}

export function calcImpairmentTotals(rows: EnrichedImpairmentProduct[]): ImpairmentColumnTotals {
  return {
    qty: calcSubtotal(rows.map((r) => r.qty)),
    bookCost: calcSubtotal(rows.map((r) => r.bookCost)),
    nrv: calcSubtotal(rows.map((r) => r.nrv)),
    requiredProvision: calcSubtotal(rows.map((r) => r.requiredProvision)),
    auditedAmount: calcSubtotal(rows.map((r) => r.auditedAmount)),
    bookedProvision: calcSubtotal(rows.map((r) => r.bookedProvision)),
    additionalProvision: calcSubtotal(rows.map((r) => r.additionalProvision)),
  }
}

export function calcCategorySummaries(rows: EnrichedImpairmentProduct[]): ImpairmentCategorySummary[] {
  const map = new Map<string, ImpairmentCategorySummary>()
  for (const r of rows) {
    if (isBlankProduct(r)) continue
    const cat = r.category.trim() || '未分类'
    const cur = map.get(cat) || {
      category: cat,
      bookCost: 0,
      auditedProvision: 0,
      auditAdjustment: 0,
      provisionRatio: 0,
    }
    cur.bookCost += r.bookCost
    cur.auditedProvision += r.requiredProvision
    cur.auditAdjustment += r.additionalProvision - r.reversal
    map.set(cat, cur)
  }
  return [...map.values()].map((s) => ({
    ...s,
    provisionRatio: s.bookCost ? s.auditedProvision / s.bookCost : 0,
  }))
}

/** 旧扁平行 / 新 sheet 格式迁移 */
export function migrateImpairmentSheet(legacy: unknown, samplingNote = ''): ImpairmentTestSheet | null {
  if (!legacy) return null

  if (typeof legacy === 'object' && legacy !== null && 'products' in legacy) {
    const sheet = legacy as ImpairmentTestSheet
    const products = Array.isArray(sheet.products) ? sheet.products : []
    return {
      ...defaultImpairmentSheet(),
      ...sheet,
      sampling: { ...defaultImpairmentSheet().sampling, ...sheet.sampling },
      products: pruneBlankProducts(products),
    }
  }

  if (Array.isArray(legacy) && legacy.length) {
    const first = legacy[0] as Record<string, unknown>
    if ('rowId' in first || 'itemName' in first) {
      const sheet = defaultImpairmentSheet()
      if (samplingNote) sheet.sampling.auditObject = samplingNote
      sheet.products = pruneBlankProducts(
        (legacy as Array<Record<string, unknown>>).map((r) => {
          const qty = Number(r.qty || 0)
          const unitCost = Number(r.unitCost || 0)
          const bookCost = qty * unitCost || Number(r.bookCost || 0)
          return {
            ...emptyImpairmentProduct(),
            id: String(r.rowId || newImpairmentProductId()),
            itemName: String(r.itemName || ''),
            qty,
            bookCost,
            pricePreContract: Number(r.sellingPrice || r.pricePreContract || 0),
            completionCost: Number(r.completionCost || 0),
            sellingExpense: Number(r.sellingExpense || 0),
            relatedTax: Number(r.tax || r.relatedTax || 0),
            bookedProvision: Number(r.existingProvision || r.bookedProvision || 0),
            remark: String(r.conclusion || r.remark || ''),
          }
        }),
      )
      return sheet
    }
  }

  return null
}
