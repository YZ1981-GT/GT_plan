/**
 * useF5QuantityRecon — F5-6 销售数量与结转成本数量核对（16列，81行）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 5.4
 * 公式链：数量差异=销售-结转 / 差异率 / 可供销售=期初+产量+采购 / 理论结转=可供-期末 / 理论差异=理论结转-结转
 * 高亮：|差异率|>5% 橙色，>10% 红色
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcQuantityVariance,
  calcVarianceRate,
  calcSubtotal,
} from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5QuantityReconOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface QuantityReconRow {
  id: string
  seq: number
  product: string
  spec: string
  unit: string
  salesQty: number
  costQty: number
  qtyVariance: number // 公式=销售-结转
  varianceRate: number | 'N/A' // 公式
  varianceReason: string // 下拉
  openingInventory: number
  currentProduction: number
  currentPurchase: number
  availableForSale: number // 公式=期初+产量+采购
  closingInventory: number
  theoreticalCostQty: number // 公式=可供-期末
  theoreticalVariance: number // 公式=理论结转-结转
}

interface StoredQuantityReconRow {
  id: string
  product: string
  spec: string
  unit: string
  salesQty: number
  costQty: number
  varianceReason: string
  openingInventory: number
  currentProduction: number
  currentPurchase: number
  closingInventory: number
}

const STORAGE_KEY = 'F5-6-quantity-recon-rows'
const ORANGE_THRESHOLD = 5
const RED_THRESHOLD = 10

/** 差异原因分类下拉选项 */
export const VARIANCE_REASON_OPTIONS = [
  '正常损耗',
  '生产废品',
  '计量误差',
  '品种替换',
  '系统错误',
  '其他',
]

function safeParse(jsonStr: string | null | undefined): StoredQuantityReconRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any) => ({
      id: String(r.id ?? Date.now()),
      product: String(r.product ?? ''),
      spec: String(r.spec ?? ''),
      unit: String(r.unit ?? ''),
      salesQty: parseNum(r.salesQty),
      costQty: parseNum(r.costQty),
      varianceReason: String(r.varianceReason ?? ''),
      openingInventory: parseNum(r.openingInventory),
      currentProduction: parseNum(r.currentProduction),
      currentPurchase: parseNum(r.currentPurchase),
      closingInventory: parseNum(r.closingInventory),
    }))
  } catch {
    return []
  }
}

function computeRow(s: StoredQuantityReconRow, seq: number): QuantityReconRow {
  const qtyVariance = calcQuantityVariance(s.salesQty, s.costQty)
  const availableForSale = s.openingInventory + s.currentProduction + s.currentPurchase
  const theoreticalCostQty = availableForSale - s.closingInventory
  return {
    id: s.id,
    seq,
    product: s.product,
    spec: s.spec,
    unit: s.unit,
    salesQty: s.salesQty,
    costQty: s.costQty,
    qtyVariance,
    varianceRate: calcVarianceRate(qtyVariance, s.salesQty),
    varianceReason: s.varianceReason,
    openingInventory: s.openingInventory,
    currentProduction: s.currentProduction,
    currentPurchase: s.currentPurchase,
    availableForSale,
    closingInventory: s.closingInventory,
    theoreticalCostQty,
    theoreticalVariance: theoreticalCostQty - s.costQty,
  }
}

export function useF5QuantityRecon(options: UseF5QuantityReconOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? computed(() => false)

  const storedRows = computed<StoredQuantityReconRow[]>(() =>
    safeParse(allResponses.value.get(STORAGE_KEY)?.remark),
  )

  const rows: ComputedRef<QuantityReconRow[]> = computed(() =>
    storedRows.value.map((s, i) => computeRow(s, i + 1)),
  )

  /** 高亮等级：'red' | 'orange' | '' */
  function highlightLevel(row: QuantityReconRow): 'red' | 'orange' | '' {
    if (row.varianceRate === 'N/A') return ''
    const abs = Math.abs(row.varianceRate)
    if (abs > RED_THRESHOLD) return 'red'
    if (abs > ORANGE_THRESHOLD) return 'orange'
    return ''
  }

  /** 底部汇总：总销售/总结转/总差异/异常品种数/红色警告品种数 */
  const summary = computed(() => {
    const list = rows.value
    return {
      totalSales: calcSubtotal(list.map((r) => r.salesQty)),
      totalCost: calcSubtotal(list.map((r) => r.costQty)),
      totalVariance: calcSubtotal(list.map((r) => r.qtyVariance)),
      abnormalCount: list.filter((r) => highlightLevel(r) !== '').length,
      redCount: list.filter((r) => highlightLevel(r) === 'red').length,
    }
  })

  function persist(rows: StoredQuantityReconRow[]): void {
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(rows) })
  }

  function updateCell(id: string, key: string, value: number | string): void {
    if (readonly.value) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = stored.findIndex((r) => r.id === id)
    if (idx === -1) return
    const numericKeys = ['salesQty', 'costQty', 'openingInventory', 'currentProduction', 'currentPurchase', 'closingInventory']
    if (numericKeys.includes(key)) {
      ;(stored[idx] as any)[key] = parseNum(value)
    } else {
      ;(stored[idx] as any)[key] = String(value ?? '')
    }
    persist(stored)
  }

  /** OCR 识别的出库单数量 merge 进指定行 */
  function mergeOcrQuantity(id: string, ocrQty: number): void {
    if (readonly.value) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = stored.findIndex((r) => r.id === id)
    if (idx === -1) return
    stored[idx].salesQty = parseNum(ocrQty)
    persist(stored)
  }

  function addRow(product: string): void {
    if (readonly.value || !product) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark)
    stored.push({
      id: `qr-${Date.now()}`,
      product,
      spec: '',
      unit: '',
      salesQty: 0,
      costQty: 0,
      varianceReason: '',
      openingInventory: 0,
      currentProduction: 0,
      currentPurchase: 0,
      closingInventory: 0,
    })
    persist(stored)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    persist(safeParse(allResponses.value.get(STORAGE_KEY)?.remark).filter((r) => r.id !== id))
  }

  return {
    rows,
    summary,
    varianceReasonOptions: VARIANCE_REASON_OPTIONS,
    highlightLevel,
    updateCell,
    mergeOcrQuantity,
    addRow,
    removeRow,
  }
}

export default useF5QuantityRecon
