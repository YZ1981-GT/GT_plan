/**
 * useF2CostAllocation — F2-44 生产成本分配
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import { readSourceTotals } from './useF2ProductionCostFormulas'
import {
  defaultAllocationSheet,
  effectivePool,
  poolGrandTotal,
  enrichAllocationProducts,
  calcAllocationTotals,
  migrateAllocationSheet,
  emptyAllocationProduct,
  type CostAllocationSheet,
  type CostAllocationProduct,
  type CostAllocationPool,
} from './useF2CostAllocationFormulas'

const ROWS_KEY = 'F2-44-rows'
const NOTE_KEY = 'F2-44-note'

export function useF2CostAllocation(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<CostAllocationSheet>(defaultAllocationSheet())
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateAllocationSheet(parsed)
        if (migrated) sheet.value = migrated
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const sourceTotals = computed(() => {
    const map = opts.allResponses.value
    void map.get('F2-41-rows')?.remark
    void map.get('F2-42-rows')?.remark
    void map.get('F2-43-rows')?.remark
    return readSourceTotals(map)
  })

  const activePool = computed(() =>
    effectivePool(sheet.value.pool, {
      material: sourceTotals.value.material,
      labor: sourceTotals.value.labor,
      overhead: sourceTotals.value.overhead,
    }),
  )

  const enrichedProducts = computed(() =>
    enrichAllocationProducts(sheet.value.products, activePool.value),
  )

  const columnTotals = computed(() => calcAllocationTotals(enrichedProducts.value))

  const poolTotal = computed(() => poolGrandTotal(activePool.value))

  const verifyFailCount = computed(() =>
    enrichedProducts.value.filter((r) => !r.verifyOk && r.verify !== '—').length,
  )

  const allocGrandTotal = computed(() => columnTotals.value.totalAlloc)

  const allocationMismatch = computed(() => {
    const diff = Math.abs(allocGrandTotal.value - poolTotal.value)
    return diff > 0.01 && poolTotal.value > 0
  })

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(sheet.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function updateSheet(patch: Partial<CostAllocationSheet>): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, ...patch }
    persist()
  }

  function updatePool(patch: Partial<CostAllocationPool>): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, pool: { ...sheet.value.pool, ...patch } }
    persist()
  }

  function updateProduct(id: string, patch: Partial<CostAllocationProduct>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: sheet.value.products.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }
    persist()
  }

  function addProduct(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: [...sheet.value.products, emptyAllocationProduct()],
    }
    persist()
  }

  function removeProduct(id: string): void {
    if (readonly.value || sheet.value.products.length <= 1) return
    sheet.value = {
      ...sheet.value,
      products: sheet.value.products.filter((p) => p.id !== id),
    }
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    sheet,
    activePool,
    sourceTotals,
    enrichedProducts,
    columnTotals,
    poolTotal,
    allocGrandTotal,
    allocationMismatch,
    verifyFailCount,
    auditNote,
    updateSheet,
    updatePool,
    updateProduct,
    addProduct,
    removeProduct,
  }
}

export default useF2CostAllocation
