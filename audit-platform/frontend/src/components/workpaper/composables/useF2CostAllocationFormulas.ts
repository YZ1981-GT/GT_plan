/**
 * F2-44 抽查×月×车间生产成本分配表（对齐致同源模板）
 *
 * 上部：本期发生成本（材料/人工/制造费用/其他）
 * 下部：各产品按分配标准占比分摊 → 应计单位成本 → 与入库单价核对
 */
import { calcSubtotal, calcAllocationRatio } from './useF2InvValFormulaEngine'

export interface CostAllocationPool {
  material: number
  labor: number
  overhead: number
  other: number
  /** 为 true 时材料/人工/费用取自 F2-41/42/43 联动（可手工覆盖） */
  linkSource: boolean
}

export interface CostAllocationProduct {
  id: string
  productName: string
  outputQty: number
  bookUnitCost: number
  allocationBase: number
  baseNote: string
}

export interface CostAllocationSheet {
  sampleMonth: string
  workshop: string
  pool: CostAllocationPool
  products: CostAllocationProduct[]
}

export interface EnrichedAllocationProduct extends CostAllocationProduct {
  materialRate: number
  materialAmt: number
  laborRate: number
  laborAmt: number
  overheadRate: number
  overheadAmt: number
  otherRate: number
  otherAmt: number
  totalAlloc: number
  accruedUnitCost: number
  verify: string
  verifyOk: boolean
}

export interface AllocationColumnTotals {
  outputQty: number
  materialAmt: number
  laborAmt: number
  overheadAmt: number
  otherAmt: number
  totalAlloc: number
}

export function newAllocationProductId(): string {
  return `f2ca-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyAllocationProduct(): CostAllocationProduct {
  return {
    id: newAllocationProductId(),
    productName: '',
    outputQty: 0,
    bookUnitCost: 0,
    allocationBase: 0,
    baseNote: '',
  }
}

/** 是否为尚未录入的空白产品行 */
export function isBlankAllocationProduct(row: CostAllocationProduct): boolean {
  return !(
    row.productName.trim()
    || n(row.outputQty)
    || n(row.bookUnitCost)
    || n(row.allocationBase)
    || row.baseNote.trim()
  )
}

/** 裁剪预留空行：只保留已填行；若全部空白则仅保留 1 行 */
export function pruneBlankAllocationProducts(
  rows: CostAllocationProduct[],
): CostAllocationProduct[] {
  const filled = rows.filter((r) => !isBlankAllocationProduct(r))
  return filled.length ? filled : [rows[0] ?? emptyAllocationProduct()]
}

/** 不预留空行；需要时由「+ 增行」添加 */
export function defaultAllocationSheet(): CostAllocationSheet {
  return {
    sampleMonth: '',
    workshop: '',
    pool: { material: 0, labor: 0, overhead: 0, other: 0, linkSource: true },
    products: [emptyAllocationProduct()],
  }
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

export function effectivePool(
  pool: CostAllocationPool,
  source: { material: number; labor: number; overhead: number },
): CostAllocationPool {
  if (!pool.linkSource) return pool
  return {
    ...pool,
    material: pool.material || source.material,
    labor: pool.labor || source.labor,
    overhead: pool.overhead || source.overhead,
  }
}

export function poolGrandTotal(pool: CostAllocationPool): number {
  return n(pool.material) + n(pool.labor) + n(pool.overhead) + n(pool.other)
}

function verifyUnitCost(accrued: number, book: number, qty: number): { verify: string; verifyOk: boolean } {
  if (!qty) return { verify: '—', verifyOk: true }
  if (!book && !accrued) return { verify: 'OK', verifyOk: true }
  const diff = Math.abs(accrued - book)
  if (diff < 0.01) return { verify: 'OK', verifyOk: true }
  if (!book) return { verify: '待核', verifyOk: false }
  const pct = diff / Math.abs(book)
  if (pct < 0.01) return { verify: 'OK', verifyOk: true }
  return { verify: `差${diff.toFixed(2)}`, verifyOk: false }
}

export function enrichAllocationProducts(
  products: CostAllocationProduct[],
  pool: CostAllocationPool,
): EnrichedAllocationProduct[] {
  const baseTotal = calcSubtotal(products.map((p) => n(p.allocationBase)))
  return products.map((p) => {
    const ratio = baseTotal ? calcAllocationRatio(n(p.allocationBase), baseTotal) / 100 : 0
    const materialAmt = ratio * n(pool.material)
    const laborAmt = ratio * n(pool.labor)
    const overheadAmt = ratio * n(pool.overhead)
    const otherAmt = ratio * n(pool.other)
    const totalAlloc = materialAmt + laborAmt + overheadAmt + otherAmt
    const qty = n(p.outputQty)
    const accruedUnitCost = qty ? totalAlloc / qty : 0
    const { verify, verifyOk } = verifyUnitCost(accruedUnitCost, n(p.bookUnitCost), qty)
    return {
      ...p,
      materialRate: ratio * 100,
      materialAmt,
      laborRate: ratio * 100,
      laborAmt,
      overheadRate: ratio * 100,
      overheadAmt,
      otherRate: ratio * 100,
      otherAmt,
      totalAlloc,
      accruedUnitCost,
      verify,
      verifyOk,
    }
  })
}

export function calcAllocationTotals(rows: EnrichedAllocationProduct[]): AllocationColumnTotals {
  return {
    outputQty: calcSubtotal(rows.map((r) => r.outputQty)),
    materialAmt: calcSubtotal(rows.map((r) => r.materialAmt)),
    laborAmt: calcSubtotal(rows.map((r) => r.laborAmt)),
    overheadAmt: calcSubtotal(rows.map((r) => r.overheadAmt)),
    otherAmt: calcSubtotal(rows.map((r) => r.otherAmt)),
    totalAlloc: calcSubtotal(rows.map((r) => r.totalAlloc)),
  }
}

function toNum(v: unknown): number {
  const num = typeof v === 'number' ? v : parseFloat(String(v ?? ''))
  return Number.isFinite(num) ? num : 0
}

/** 兼容导入行/旧数据：字段缺失补默认、数值字符串强转 */
function sanitizeProduct(r: Record<string, unknown>): CostAllocationProduct {
  return {
    id: String(r.id || r.rowId || '') || newAllocationProductId(),
    productName: String(r.productName ?? ''),
    outputQty: toNum(r.outputQty),
    bookUnitCost: toNum(r.bookUnitCost),
    allocationBase: toNum(r.allocationBase),
    baseNote: String(r.baseNote ?? ''),
  }
}

export function migrateAllocationSheet(legacy: unknown): CostAllocationSheet | null {
  if (!legacy) return null
  if (typeof legacy === 'object' && !Array.isArray(legacy) && 'products' in legacy) {
    const obj = legacy as Partial<CostAllocationSheet> & { products?: unknown }
    const base = defaultAllocationSheet()
    return {
      sampleMonth: String(obj.sampleMonth ?? ''),
      workshop: String(obj.workshop ?? ''),
      pool: { ...base.pool, ...(typeof obj.pool === 'object' && obj.pool ? obj.pool : {}) },
      products: pruneBlankAllocationProducts(
        Array.isArray(obj.products) && obj.products.length
          ? (obj.products as Record<string, unknown>[]).map(sanitizeProduct)
          : base.products,
      ),
    }
  }
  if (Array.isArray(legacy) && legacy.length) {
    const first = legacy[0] as Record<string, unknown>
    if ('allocationBase' in first || 'productName' in first) {
      return {
        ...defaultAllocationSheet(),
        products: pruneBlankAllocationProducts(
          (legacy as Record<string, unknown>[]).map(sanitizeProduct),
        ),
      }
    }
  }
  return null
}

export const F2_44_DEFAULT_OBJECTIVE =
  '验证抽查月份、车间生产成本在各产品间的分配基准是否合理、一贯，重新计算应计单位成本并与入库单价核对，为存货计价提供分配证据。'
