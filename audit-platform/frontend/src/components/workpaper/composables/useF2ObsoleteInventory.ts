/**
 * useF2ObsoleteInventory — F2-48 长库龄/呆滞/超过保质期存货明细表
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  defaultObsoleteSheet,
  enrichObsoleteItems,
  calcObsoleteTotals,
  migrateObsoleteSheet,
  emptyObsoleteItem,
  type ObsoleteInventorySheet,
  type ObsoleteInventoryItem,
  type ImpairmentAging,
} from './useF2ObsoleteInventoryFormulas'

/** @deprecated 兼容旧引用 */
export type ObsoleteInventoryRow = ObsoleteInventoryItem & { rowId?: string }
export const DISPOSAL_OPTIONS = ['正常销售', '促销', '报废', '退货', '转跌价'] as const

const ROWS_KEY = 'F2-48-rows'
const NOTE_KEY = 'F2-48-note'

export function useF2ObsoleteInventory(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<ObsoleteInventorySheet>(defaultObsoleteSheet())
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateObsoleteSheet(parsed)
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
            if (debounceTimer) clearTimeout(debounceTimer)
            debounceTimer = setTimeout(() => {
              debounceTimer = null
              flushSave()
            }, 2000)
          }
        }
      } catch { /* ignore */ }
    }
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })
  watch(() => allResponses.value.get(NOTE_KEY)?.remark, (v) => { auditNote.value = v || '' }, { immediate: true })

  const enrichedProducts = computed(() => enrichObsoleteItems(sheet.value.products))
  const enrichedRows = enrichedProducts

  const columnTotals = computed(() => calcObsoleteTotals(enrichedProducts.value))

  const summary = computed(() => ({
    longAgeCount: enrichedProducts.value.filter((r) => r.isLongAge).length,
    obsoleteCount: enrichedProducts.value.filter((r) =>
      r.impairmentSigns.includes('呆滞') || r.impairmentSigns.includes('冷背'),
    ).length,
    expiredCount: enrichedProducts.value.filter((r) =>
      r.impairmentSigns.includes('超保质期') || r.impairmentSigns.includes('过时'),
    ).length,
    impairmentTotal: columnTotals.value.provisionAmount,
    agingMismatchCount: enrichedProducts.value.filter((r) => r.agingMismatch).length,
  }))

  function flushSave(): void {
    const items = [
      allResponses.value.get(ROWS_KEY),
      allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function persist(): void {
    if (readonly.value) return
    allResponses.value.set(ROWS_KEY, {
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

  function updateProduct(id: string, patch: Partial<ObsoleteInventoryItem>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: sheet.value.products.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }
    persist()
  }

  function updateRow(rowId: string, patch: Partial<ObsoleteInventoryRow>): void {
    const mapped: Partial<ObsoleteInventoryItem> = { ...patch }
    if (patch.rowId) mapped.id = patch.rowId
    if (patch.bookCost != null && patch.qty != null && patch.qty > 0) {
      mapped.unitPrice = patch.bookCost / patch.qty
    }
    updateProduct(rowId, mapped)
  }

  function updateAging(id: string, patch: Partial<ImpairmentAging>): void {
    const row = sheet.value.products.find((p) => p.id === id)
    if (!row || readonly.value) return
    updateProduct(id, { aging: { ...row.aging, ...patch } })
  }

  function addProduct(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: [...sheet.value.products, emptyObsoleteItem()],
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

  function removeRow(rowId: string): void {
    removeProduct(rowId)
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    persist()
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
    summary,
    auditNote,
    updateProduct,
    updateRow,
    updateAging,
    addProduct,
    addRow,
    removeProduct,
    removeRow,
  }
}

export default useF2ObsoleteInventory
