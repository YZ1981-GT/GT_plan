/**
 * useF5QuantityRecon — F5-6 销售数量与结转成本数量核对明细表
 *
 * 源表逻辑：分厂 → 产品 × (1~12月 + 总计)，三块平行表
 *  1. 本期销售数量（输入）
 *  2. 本期结转销售成本数量（输入）
 *  3. 差异 = 销售 − 结转（各月及总计，只读）
 *  分厂行 = Σ产品；总计行 = Σ分厂
 */
import { computed, ref, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5QuantityReconOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface QuantitySeries {
  months: number[]
  total: number
}

export interface QuantityProductView {
  id: string
  name: string
  sales: QuantitySeries
  cost: QuantitySeries
  diff: QuantitySeries
}

export interface QuantityPlantView {
  id: string
  name: string
  products: QuantityProductView[]
  sales: QuantitySeries
  cost: QuantitySeries
  diff: QuantitySeries
}

interface StoredProduct {
  id: string
  name: string
  salesMonths: number[]
  costMonths: number[]
}

interface StoredPlant {
  id: string
  name: string
  products: StoredProduct[]
}

const STORAGE_KEY = 'F5-6-quantity-recon-plants'
const LEGACY_STORAGE_KEY = 'F5-6-quantity-recon-rows'
const LEGACY_IE_KEY = 'F5-6-rows'
const NOTE_KEY = 'F5-6-audit-note'
const CONCLUSION_KEY = 'F5-6-audit-conclusion'

export const F5_QTY_MONTH_LABELS = [
  '1月', '2月', '3月', '4月', '5月', '6月',
  '7月', '8月', '9月', '10月', '11月', '12月',
] as const

/** 差异绝对值超过此阈值标黄（按年总计） */
export const F5_QTY_DIFF_THRESHOLD = 0

function emptyMonths(): number[] {
  return new Array(12).fill(0)
}

function normalizeMonths(raw: unknown): number[] {
  if (Array.isArray(raw)) {
    return [...raw.map(parseNum), ...emptyMonths()].slice(0, 12)
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>
    return Array.from({ length: 12 }, (_, i) =>
      parseNum(obj[`m${i + 1}`] ?? obj[`month${i + 1}`]),
    )
  }
  return emptyMonths()
}

function seriesFromMonths(months: number[]): QuantitySeries {
  const m = normalizeMonths(months)
  return { months: m, total: calcSubtotal(m) }
}

function diffSeries(sales: QuantitySeries, cost: QuantitySeries): QuantitySeries {
  const months = sales.months.map((v, i) => v - (cost.months[i] || 0))
  return { months, total: sales.total - cost.total }
}

function sumSeries(list: QuantitySeries[]): QuantitySeries {
  const months = emptyMonths()
  for (const s of list) {
    for (let i = 0; i < 12; i++) months[i] += s.months[i] || 0
  }
  return seriesFromMonths(months)
}

function newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyF5QtyProduct(name = ''): StoredProduct {
  return {
    id: newId('qp'),
    name,
    salesMonths: emptyMonths(),
    costMonths: emptyMonths(),
  }
}

export function emptyF5QtyPlant(name = '', productCount = 4): StoredPlant {
  return {
    id: newId('plant'),
    name,
    products: Array.from({ length: productCount }, (_, i) =>
      emptyF5QtyProduct(`产品${i + 1}`),
    ),
  }
}

export function defaultF5QtyPlants(): StoredPlant[] {
  return [emptyF5QtyPlant('分厂1'), emptyF5QtyPlant('分厂2')]
}

/** 扁平导入行 → 嵌套（按 plant 分组） */
function plantsFromFlatRows(rows: any[]): StoredPlant[] {
  const plantMap = new Map<string, StoredPlant>()
  const plantOrder: string[] = []
  for (const r of rows) {
    const plantKey = String(r?.plantId ?? r?.plant ?? r?.plantName ?? r?.factory ?? '默认分厂').trim() || '默认分厂'
    let plant = plantMap.get(plantKey)
    if (!plant) {
      plant = {
        id: String(r?.plantId ?? newId('plant')),
        name: String(r?.plant ?? r?.plantName ?? r?.factory ?? plantKey),
        products: [],
      }
      plantMap.set(plantKey, plant)
      plantOrder.push(plantKey)
    }
    const name = String(r?.product ?? r?.name ?? r?.variety ?? r?.label ?? '')

    let salesMonths = emptyMonths()
    let costMonths = emptyMonths()

    if (Array.isArray(r?.salesMonths) || Array.isArray(r?.sales)) {
      salesMonths = normalizeMonths(r?.salesMonths ?? r?.sales)
    } else if (r?.sm1 != null || r?.sm12 != null) {
      salesMonths = Array.from({ length: 12 }, (_, i) => parseNum(r[`sm${i + 1}`]))
    } else if (r?.section === 'sales' || r?.section === '销售') {
      salesMonths = normalizeMonths(r)
    }

    if (Array.isArray(r?.costMonths) || Array.isArray(r?.cost)) {
      costMonths = normalizeMonths(r?.costMonths ?? r?.cost)
    } else if (r?.cm1 != null || r?.cm12 != null) {
      costMonths = Array.from({ length: 12 }, (_, i) => parseNum(r[`cm${i + 1}`]))
    } else if (r?.section === 'cost' || r?.section === '结转') {
      costMonths = normalizeMonths(r)
    }

    // 旧年累计：salesQty/costQty → 12月
    if (!salesMonths.some((v) => v !== 0) && (r?.salesQty != null || r?.qtySold != null)) {
      salesMonths = emptyMonths()
      salesMonths[11] = parseNum(r?.salesQty ?? r?.qtySold)
    }
    if (!costMonths.some((v) => v !== 0) && (r?.costQty != null || r?.qtyCost != null)) {
      costMonths = emptyMonths()
      costMonths[11] = parseNum(r?.costQty ?? r?.qtyCost)
    }

    // 同产品多行（分 section 导入）合并
    const existing = plant.products.find(
      (p) => p.name === name && name !== '',
    )
    if (existing && (r?.section || r?.sm1 == null)) {
      if (salesMonths.some((v) => v !== 0)) existing.salesMonths = salesMonths
      if (costMonths.some((v) => v !== 0)) existing.costMonths = costMonths
      continue
    }

    plant.products.push({
      id: String(r?.id ?? r?.productId ?? newId('qp')),
      name: name || `产品${plant.products.length + 1}`,
      salesMonths,
      costMonths,
    })
  }
  return plantOrder.map((k) => plantMap.get(k)!)
}

export function migrateF5QuantityPlants(jsonStr: string | null | undefined): StoredPlant[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    // 新格式 { plants: [...] }
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && Array.isArray(parsed.plants)) {
      return parsed.plants.map((p: any, pi: number) => ({
        id: String(p?.id ?? `plant-${pi}`),
        name: String(p?.name ?? p?.plant ?? `分厂${pi + 1}`),
        products: Array.isArray(p?.products)
          ? p.products.map((pr: any, i: number) => ({
              id: String(pr?.id ?? `qp-${pi}-${i}`),
              name: String(pr?.name ?? pr?.product ?? ''),
              salesMonths: normalizeMonths(pr?.salesMonths ?? pr?.sales),
              costMonths: normalizeMonths(pr?.costMonths ?? pr?.cost),
            }))
          : [],
      }))
    }
    // 数组：plant 嵌套 或 扁平产品行（含 sm1..cm12 / plant）
    if (Array.isArray(parsed)) {
      if (parsed.length === 0) return []
      if (parsed[0]?.products && Array.isArray(parsed[0].products)) {
        return migrateF5QuantityPlants(JSON.stringify({ plants: parsed }))
      }
      return plantsFromFlatRows(parsed)
    }
    return []
  } catch {
    return []
  }
}

export function computeF5QtyProduct(stored: StoredProduct): QuantityProductView {
  const sales = seriesFromMonths(stored.salesMonths)
  const cost = seriesFromMonths(stored.costMonths)
  return {
    id: stored.id,
    name: stored.name,
    sales,
    cost,
    diff: diffSeries(sales, cost),
  }
}

export function computeF5QtyPlant(stored: StoredPlant): QuantityPlantView {
  const products = stored.products.map(computeF5QtyProduct)
  const sales = sumSeries(products.map((p) => p.sales))
  const cost = sumSeries(products.map((p) => p.cost))
  return {
    id: stored.id,
    name: stored.name,
    products,
    sales,
    cost,
    diff: diffSeries(sales, cost),
  }
}

export function buildF5QtyGrandTotal(plants: QuantityPlantView[]): {
  sales: QuantitySeries
  cost: QuantitySeries
  diff: QuantitySeries
} {
  const sales = sumSeries(plants.map((p) => p.sales))
  const cost = sumSeries(plants.map((p) => p.cost))
  return { sales, cost, diff: diffSeries(sales, cost) }
}

export function useF5QuantityRecon(options: UseF5QuantityReconOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastPersisted = ''

  const storedPlants = ref<StoredPlant[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function rawJson(): string | null | undefined {
    return allResponses.value.get(STORAGE_KEY)?.remark
      ?? allResponses.value.get(LEGACY_STORAGE_KEY)?.remark
      ?? allResponses.value.get(LEGACY_IE_KEY)?.remark
  }

  function loadRows(): void {
    const migrated = migrateF5QuantityPlants(rawJson())
    storedPlants.value = migrated.length ? migrated : defaultF5QtyPlants()
  }

  watch(() => rawJson(), (raw) => {
    if (raw && raw === lastPersisted) return
    loadRows()
  }, { immediate: true })

  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    ([note, conclusion]) => {
      auditNote.value = typeof note === 'string' ? note : ''
      auditConclusion.value = typeof conclusion === 'string' ? conclusion : ''
    },
    { immediate: true },
  )

  const plants: ComputedRef<QuantityPlantView[]> = computed(() =>
    storedPlants.value.map(computeF5QtyPlant),
  )
  const grandTotal = computed(() => buildF5QtyGrandTotal(plants.value))

  const significantDiffs = computed(() => {
    const out: Array<{ plant: string; product: string; diffTotal: number }> = []
    for (const plant of plants.value) {
      for (const prod of plant.products) {
        if (Math.abs(prod.diff.total) > F5_QTY_DIFF_THRESHOLD) {
          out.push({ plant: plant.name, product: prod.name, diffTotal: prod.diff.total })
        }
      }
    }
    return out
  })

  /** 扁平化以便导入导出宽表 round-trip */
  function toPersistRows(): Array<Record<string, string | number>> {
    const out: Array<Record<string, string | number>> = []
    for (const plant of storedPlants.value) {
      for (const prod of plant.products) {
        const row: Record<string, string | number> = {
          id: prod.id,
          plantId: plant.id,
          plant: plant.name,
          product: prod.name,
          name: prod.name,
        }
        for (let i = 0; i < 12; i++) {
          row[`sm${i + 1}`] = prod.salesMonths[i] || 0
          row[`cm${i + 1}`] = prod.costMonths[i] || 0
        }
        out.push(row)
      }
    }
    return out
  }

  function persist(): void {
    const json = JSON.stringify(toPersistRows())
    lastPersisted = json
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: json })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get(NOTE_KEY),
      allResponses.value.get(CONCLUSION_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items } }))
    }
  }

  function findProduct(plantId: string, productId: string): StoredProduct | null {
    const plant = storedPlants.value.find((p) => p.id === plantId)
    return plant?.products.find((pr) => pr.id === productId) ?? null
  }

  function updatePlantName(plantId: string, name: string): void {
    if (readonly.value) return
    const plant = storedPlants.value.find((p) => p.id === plantId)
    if (!plant) return
    plant.name = String(name ?? '')
    persist()
  }

  function updateProductName(plantId: string, productId: string, name: string): void {
    if (readonly.value) return
    const prod = findProduct(plantId, productId)
    if (!prod) return
    prod.name = String(name ?? '')
    persist()
  }

  function updateMonth(
    plantId: string,
    productId: string,
    series: 'sales' | 'cost',
    monthIndex: number,
    value: number | string,
  ): void {
    if (readonly.value) return
    if (monthIndex < 0 || monthIndex > 11) return
    const prod = findProduct(plantId, productId)
    if (!prod) return
    const arr = series === 'sales' ? prod.salesMonths : prod.costMonths
    arr[monthIndex] = parseNum(value)
    persist()
  }

  function addPlant(name = ''): void {
    if (readonly.value) return
    storedPlants.value.push(
      emptyF5QtyPlant(name || `分厂${storedPlants.value.length + 1}`),
    )
    persist()
  }

  function removePlant(plantId: string): void {
    if (readonly.value) return
    const next = storedPlants.value.filter((p) => p.id !== plantId)
    storedPlants.value = next.length ? next : defaultF5QtyPlants()
    persist()
  }

  function addProduct(plantId: string, name = ''): void {
    if (readonly.value) return
    const plant = storedPlants.value.find((p) => p.id === plantId)
    if (!plant) return
    plant.products.push(
      emptyF5QtyProduct(name || `产品${plant.products.length + 1}`),
    )
    persist()
  }

  /** OCR 出库单回填：按产品名定位（或新建），写入结转数量对应月份 */
  function applyOcrOutbound(fields: {
    product?: string
    quantity?: number | string
    date?: string
    voucherNo?: string
  }, plantId?: string): { plantId: string; productId: string; monthIndex: number } | null {
    if (readonly.value) return null
    if (!storedPlants.value.length) addPlant('分厂1')
    const plant = (plantId && storedPlants.value.find((p) => p.id === plantId))
      || storedPlants.value[0]
    if (!plant) return null
    const productName = String(fields.product || '').trim() || 'OCR产品'
    let prod = plant.products.find((p) => p.name.trim() === productName)
    if (!prod) {
      prod = emptyF5QtyProduct(productName)
      plant.products.push(prod)
    }
    let monthIndex = 0
    const dateStr = String(fields.date || '')
    const m = dateStr.match(/(\d{4})-(\d{1,2})/)
    if (m) monthIndex = Math.min(11, Math.max(0, Number(m[2]) - 1))
    const qty = parseNum(fields.quantity)
    if (Math.abs(qty) >= 0.0005) {
      prod.costMonths[monthIndex] = qty
    }
    persist()
    return { plantId: plant.id, productId: prod.id, monthIndex }
  }

  function removeProduct(plantId: string, productId: string): void {
    if (readonly.value) return
    const plant = storedPlants.value.find((p) => p.id === plantId)
    if (!plant) return
    if (plant.products.length <= 1) {
      plant.products = [emptyF5QtyProduct('产品1')]
    } else {
      plant.products = plant.products.filter((p) => p.id !== productId)
    }
    persist()
  }

  function isDiffHighlighted(diffTotal: number): boolean {
    return Math.abs(diffTotal) > F5_QTY_DIFF_THRESHOLD
  }

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    plants,
    grandTotal,
    significantDiffs,
    auditNote,
    auditConclusion,
    updatePlantName,
    updateProductName,
    updateMonth,
    addPlant,
    removePlant,
    addProduct,
    applyOcrOutbound,
    removeProduct,
    isDiffHighlighted,
    saveAuditNote,
    saveAuditConclusion,
    loadRows,
  }
}

export default useF5QuantityRecon
