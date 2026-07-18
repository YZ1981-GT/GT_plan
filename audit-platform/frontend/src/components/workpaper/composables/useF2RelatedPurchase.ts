/**
 * useF2RelatedPurchase — F2-52 存货关联采购分析表
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  defaultRelatedPurchaseSheet,
  enrichRelatedPurchases,
  calcRelatedPurchaseTotals,
  migrateRelatedPurchaseSheet,
  emptyRelatedPurchaseItem,
  type RelatedPurchaseSheet,
  type RelatedPurchaseItem,
  type RelatedPurchaseAuditNotes,
} from './useF2RelatedPurchaseFormulas'

/** @deprecated 兼容旧引用 */
export type RelatedPurchaseRow = RelatedPurchaseItem & {
  rowId?: string
  relatedParty?: string
  itemName?: string
  relatedPrice?: number
  comparablePrice?: number
  quantity?: number
  amount?: number
  fairnessEval?: string
}

const ROWS_KEY = 'F2-52-rows'
const NOTE_KEY = 'F2-52-note'

export function useF2RelatedPurchase(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<RelatedPurchaseSheet>(defaultRelatedPurchaseSheet())
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(allResponses.value.get(ROWS_KEY))
    // 自回声守卫：persist() 写回后 watcher 会再次触发 load，
    // 若内容与内存一致则跳过，避免 migrate 的空行裁剪吃掉刚新增的空行。
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateRelatedPurchaseSheet(parsed)
        if (migrated) {
          const beforeCount = Array.isArray(parsed?.products)
            ? parsed.products.length
            : (Array.isArray(parsed) ? parsed.length : 0)
          sheet.value = migrated
          // 清理历史预留空行并写回，避免刷新后再次出现。
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
            }, 300)
          }
        }
      } catch { /* ignore */ }
    }
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })
  watch(() => allResponses.value.get(NOTE_KEY)?.remark, (v) => { auditNote.value = v || '' }, { immediate: true })

  const enrichedProducts = computed(() => enrichRelatedPurchases(sheet.value.products))
  const enrichedRows = enrichedProducts

  const columnTotals = computed(() => calcRelatedPurchaseTotals(enrichedProducts.value))

  const highDeviationCount = computed(() =>
    enrichedProducts.value.filter((r) => r.isHighVariance).length,
  )

  const totalAmount = computed(() => columnTotals.value.relatedAmount)

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

  function updateAuditNotes(patch: Partial<RelatedPurchaseAuditNotes>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      auditNotes: { ...sheet.value.auditNotes, ...patch },
    }
    persist()
  }

  function updateProduct(id: string, patch: Partial<RelatedPurchaseItem>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: sheet.value.products.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }
    persist()
  }

  function updateRow(rowId: string, patch: Partial<RelatedPurchaseRow>): void {
    const mapped: Partial<RelatedPurchaseItem> = { ...patch }
    if (patch.rowId) mapped.id = patch.rowId
    if (patch.relatedParty) mapped.relatedPartyName = patch.relatedParty
    if (patch.itemName) mapped.itemNameSpec = patch.itemName
    if (patch.comparablePrice != null) mapped.nonRelatedAvgPrice = patch.comparablePrice
    if (patch.quantity != null) mapped.relatedQty = patch.quantity
    if (patch.relatedPrice != null && patch.quantity != null) {
      mapped.relatedAmount = patch.relatedPrice * patch.quantity
    }
    updateProduct(rowId, mapped)
  }

  function addProduct(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: [...sheet.value.products, emptyRelatedPurchaseItem()],
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
    highDeviationCount,
    totalAmount,
    auditNote,
    updateAuditNotes,
    updateProduct,
    updateRow,
    addProduct,
    addRow,
    removeProduct,
    removeRow,
  }
}

export default useF2RelatedPurchase
