/**
 * F2-25 抽盘结果汇总表 / F2-26 盘点倒轧表 —— 行计算（纯函数，组件与对拍守卫共用）。
 *
 * 公式按权威模板「F2-21至F2-26 存货及跌价准备 - 盘点类」逐列：
 *   F2-25：J 抽盘与账面差异 = I − F；K 抽盘与企业盘点差异 = I − H；L 企业盘点与账面差异 = H − F
 *   F2-26：J 资产负债表日实存数量 = G + H − I；L 数量差异 = J − K；M 金额差异 = L × E
 *          日后表 H 是「加：资产负债表日至监盘日发出数量」、I 是「减：…入库数量」；
 *          日前表 H 是「加：监盘日至资产负债表日入库数量」、I 是「减：…发出数量」。
 *          前端两张表都存 inboundQty / outboundQty（入库 / 发出实物量），按表别取加减方向。
 */
import type {
  StocktakeRollMode,
  StocktakeRollforwardRow,
  StocktakeSampleRow,
} from './f2StocktakeConfigs'

export type StocktakeSampleEnrichedRow = StocktakeSampleRow & {
  sampleVsBook: number
  sampleVsClient: number
  clientVsBook: number
  hasVariance: boolean
}

export type StocktakeRollforwardEnrichedRow = StocktakeRollforwardRow & {
  calcBsQty: number
  qtyDiff: number
  amtDiff: number
  hasVariance: boolean
}

export function emptyStocktakeSampleRow(): StocktakeSampleRow {
  return {
    id: `st-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    itemCode: '',
    itemName: '',
    spec: '',
    unit: '',
    unitPrice: 0,
    bookQty: 0,
    bookAmount: 0,
    clientCountQty: 0,
    sampleQty: 0,
    qualityStatus: '',
    varianceReason: '',
    remark: '',
  }
}

export function emptyStocktakeRollforwardRow(): StocktakeRollforwardRow {
  return {
    id: `st-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    category: '',
    itemCode: '',
    itemName: '',
    spec: '',
    unit: '',
    unitPrice: 0,
    warehouse: '',
    countDayQty: 0,
    inboundQty: 0,
    outboundQty: 0,
    bookQty: 0,
    varianceReason: '',
    needAdjust: '',
    remark: '',
  }
}

export function normalizeStocktakeSampleRow(
  r: Partial<StocktakeSampleRow> & { id: string },
): StocktakeSampleRow {
  return {
    ...emptyStocktakeSampleRow(),
    ...r,
    itemCode: r.itemCode ?? '',
    unitPrice: Number(r.unitPrice ?? 0),
    bookAmount: Number(r.bookAmount ?? 0),
    clientCountQty: Number(r.clientCountQty ?? 0),
    qualityStatus: r.qualityStatus ?? '',
  }
}

export function enrichStocktakeSampleRow(raw: StocktakeSampleRow): StocktakeSampleEnrichedRow {
  const r = normalizeStocktakeSampleRow(raw)
  const sampleVsBook = r.sampleQty - r.bookQty
  const sampleVsClient = r.sampleQty - r.clientCountQty
  const clientVsBook = r.clientCountQty - r.bookQty
  return {
    ...r,
    sampleVsBook,
    sampleVsClient,
    clientVsBook,
    hasVariance:
      Math.abs(sampleVsBook) > 0.001
      || Math.abs(sampleVsClient) > 0.001
      || Math.abs(clientVsBook) > 0.001,
  }
}

export function enrichStocktakeRollforwardRow(
  r: StocktakeRollforwardRow,
  mode: StocktakeRollMode,
): StocktakeRollforwardEnrichedRow {
  const calcBsQty =
    mode === 'after'
      ? r.countDayQty + r.outboundQty - r.inboundQty
      : r.countDayQty + r.inboundQty - r.outboundQty
  const qtyDiff = calcBsQty - r.bookQty
  const amtDiff = qtyDiff * (r.unitPrice || 0)
  return {
    ...r,
    category: r.category || '',
    itemCode: r.itemCode || '',
    spec: r.spec || '',
    unit: r.unit || '',
    unitPrice: r.unitPrice || 0,
    warehouse: r.warehouse || '',
    varianceReason: r.varianceReason || '',
    needAdjust: r.needAdjust || '',
    calcBsQty,
    qtyDiff,
    amtDiff,
    hasVariance: Math.abs(qtyDiff) > 0.001,
  }
}
