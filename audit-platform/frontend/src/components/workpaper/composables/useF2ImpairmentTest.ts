/**
 * useF2ImpairmentTest — F2-47 跌价准备 NRV 测试
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  defaultImpairmentSheet,
  enrichImpairmentProducts,
  calcImpairmentTotals,
  calcCategorySummaries,
  migrateImpairmentSheet,
  emptyImpairmentProduct,
  type ImpairmentTestSheet,
  type ImpairmentTestProductRow,
  type ImpairmentSamplingMeta,
} from './useF2ImpairmentTestFormulas'

/** @deprecated 兼容 OCR；新代码请使用 ImpairmentTestProductRow */
export type ImpairmentTestRow = ImpairmentTestProductRow & {
  rowId?: string
  unitCost?: number
  sellingPrice?: number
  tax?: number
  existingProvision?: number
  conclusion?: string
}

const ROWS_KEY = 'F2-47-rows'
const PARAMS_KEY = 'F2-47-sampling'
const CONCLUSION_KEY = 'F2-47-conclusion'

export function useF2ImpairmentTest(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<ImpairmentTestSheet>(defaultImpairmentSheet())
  const testConclusion = ref('')

  function load(): void {
    const raw = readValRowJson(allResponses.value.get(ROWS_KEY))
    const params = allResponses.value.get(PARAMS_KEY)?.remark || ''
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateImpairmentSheet(parsed, params)
        if (migrated) {
          const beforeCount = Array.isArray(parsed?.products)
            ? parsed.products.length
            : (Array.isArray(parsed) ? parsed.length : 0)
          sheet.value = migrated
          // 裁掉历史预留空行后写回，避免刷新又还原
          if (!readonly.value && beforeCount > migrated.products.length) {
            allResponses.value.set(ROWS_KEY, {
              item_id: ROWS_KEY,
              conclusion: null,
              remark: JSON.stringify(migrated),
            })
            debounceSave()
          }
        }
      } catch { /* ignore */ }
    } else if (params) {
      sheet.value = {
        ...sheet.value,
        sampling: { ...sheet.value.sampling, auditObject: params },
      }
    }
    testConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark || ''
  }

  watch(() => allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })
  watch(() => allResponses.value.get(PARAMS_KEY)?.remark, load)

  const enrichedProducts = computed(() => enrichImpairmentProducts(sheet.value.products))
  const enrichedRows = enrichedProducts

  const columnTotals = computed(() => calcImpairmentTotals(enrichedProducts.value))
  const totalSummary = computed(() => ({
    bookCost: columnTotals.value.bookCost,
    nrv: columnTotals.value.nrv,
    requiredProvision: columnTotals.value.requiredProvision,
    existingProvision: columnTotals.value.bookedProvision,
    netDiff: columnTotals.value.additionalProvision,
  }))

  const categorySummaries = computed(() => calcCategorySummaries(enrichedProducts.value))

  const needsConclusionCount = computed(() =>
    enrichedProducts.value.filter((r) => r.needsRemark).length,
  )

  const agingMismatchCount = computed(() =>
    enrichedProducts.value.filter((r) => r.agingMismatch).length,
  )

  function flushSave(): void {
    const items = [
      allResponses.value.get(ROWS_KEY),
      allResponses.value.get(PARAMS_KEY),
      allResponses.value.get(CONCLUSION_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function publishImpairmentCalculated(): void {
    const total = columnTotals.value.requiredProvision
    try {
      window.dispatchEvent(new CustomEvent('impairment:calculated', {
        detail: {
          wpCode: 'F2',
          sheetCode: 'F2-47',
          totalRequiredProvision: total,
          rows: enrichedProducts.value.map((r) => ({
            itemName: r.itemName,
            requiredProvision: r.requiredProvision,
          })),
        },
      }))
    } catch { /* silent */ }
  }

  function persist(): void {
    if (readonly.value) return
    allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(sheet.value),
    })
    const samplingText = sheet.value.sampling.auditObject
    allResponses.value.set(PARAMS_KEY, {
      item_id: PARAMS_KEY,
      conclusion: null,
      remark: samplingText,
    })
    debounceSave()
    publishImpairmentCalculated()
  }

  function updateSheet(patch: Partial<ImpairmentTestSheet>): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, ...patch }
    persist()
  }

  function updateSampling(patch: Partial<ImpairmentSamplingMeta>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      sampling: { ...sheet.value.sampling, ...patch },
    }
    persist()
  }

  function setProcedure(val: string): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, auditProcedure: val }
    persist()
  }

  function updateProduct(id: string, patch: Partial<ImpairmentTestProductRow>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: sheet.value.products.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }
    persist()
  }

  function updateRow(id: string, patch: Partial<ImpairmentTestRow>): void {
    const mapped: Partial<ImpairmentTestProductRow> = { ...patch }
    if (patch.rowId) mapped.id = patch.rowId
    if (patch.sellingPrice != null) mapped.pricePreContract = patch.sellingPrice
    if (patch.tax != null) mapped.relatedTax = patch.tax
    if (patch.existingProvision != null) mapped.bookedProvision = patch.existingProvision
    if (patch.conclusion != null) mapped.remark = patch.conclusion
    if (patch.unitCost != null && patch.qty == null) {
      const row = sheet.value.products.find((p) => p.id === id)
      if (row) mapped.bookCost = row.qty * patch.unitCost
    }
    if (patch.qty != null && patch.unitCost != null) {
      mapped.bookCost = patch.qty * patch.unitCost
    }
    updateProduct(id, mapped)
  }

  function addProduct(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: [...sheet.value.products, emptyImpairmentProduct()],
    }
    persist()
  }

  function addRow(): void {
    addProduct()
  }

  function removeProduct(id: string): void {
    if (readonly.value || sheet.value.products.length <= 1) return
    sheet.value = {
      ...sheet.value,
      products: sheet.value.products.filter((p) => p.id !== id),
    }
    persist()
  }

  function removeRow(id: string): void {
    removeProduct(id)
  }

  watch(testConclusion, (val) => {
    if (readonly.value) return
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  const samplingNote = computed({
    get: () => sheet.value.sampling.auditObject,
    set: (val: string) => updateSampling({ auditObject: val }),
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    sheet,
    enrichedProducts,
    enrichedRows,
    columnTotals,
    categorySummaries,
    totalSummary,
    needsConclusionCount,
    agingMismatchCount,
    testConclusion,
    samplingNote,
    updateSheet,
    updateSampling,
    setProcedure,
    updateProduct,
    updateRow,
    addProduct,
    addRow,
    removeProduct,
    removeRow,
    publishImpairmentCalculated,
  }
}

export default useF2ImpairmentTest
