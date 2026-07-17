/**
 * useF2ImpairmentReversal — F2-49 存货跌价准备转回核对表
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  defaultReversalSheet,
  enrichReversalItems,
  calcReversalTotals,
  migrateReversalSheet,
  emptyReversalItem,
  type ImpairmentReversalSheet,
  type ImpairmentReversalItem,
  type IssuanceBreakdown,
  type ReversalAccountSplit,
  type ImpairmentAging,
} from './useF2ImpairmentReversalFormulas'

/** @deprecated 兼容旧引用 */
export type ImpairmentReversalRow = ImpairmentReversalItem & { rowId?: string }

const ROWS_KEY = 'F2-49-rows'
const NOTE_KEY = 'F2-49-note'

export function useF2ImpairmentReversal(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<ImpairmentReversalSheet>(defaultReversalSheet())
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateReversalSheet(parsed)
        if (migrated) sheet.value = migrated
      } catch { /* ignore */ }
    }
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })
  watch(() => allResponses.value.get(NOTE_KEY)?.remark, (v) => { auditNote.value = v || '' }, { immediate: true })

  const enrichedProducts = computed(() => enrichReversalItems(sheet.value.products))
  const enrichedRows = enrichedProducts

  const columnTotals = computed(() => calcReversalTotals(enrichedProducts.value))

  const summary = computed(() => ({
    reverseCount: enrichedProducts.value.filter((r) => r.reversalTotal > 0).length,
    reverseTotal: columnTotals.value.reversalTotal,
    verifyFailCount: enrichedProducts.value.filter((r) => !r.verifyOk && r.reversalTotal > 0).length,
    issuanceMismatchCount: enrichedProducts.value.filter((r) => r.issuanceMismatch).length,
    agingMismatchCount: enrichedProducts.value.filter((r) => r.agingMismatch).length,
    missingRationale: 0,
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

  function updateProduct(id: string, patch: Partial<ImpairmentReversalItem>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: sheet.value.products.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }
    persist()
  }

  function updateRow(rowId: string, patch: Partial<ImpairmentReversalRow>): void {
    const mapped: Partial<ImpairmentReversalItem> = { ...patch }
    if (patch.rowId) mapped.id = patch.rowId
    if (patch.bookCost != null && patch.openingQty == null) {
      const row = sheet.value.products.find((p) => p.id === rowId)
      const qty = row?.openingQty || 1
      mapped.openingUnitPrice = patch.bookCost / qty
    }
    updateProduct(rowId, mapped)
  }

  function updateAging(id: string, patch: Partial<ImpairmentAging>): void {
    const row = sheet.value.products.find((p) => p.id === id)
    if (!row || readonly.value) return
    updateProduct(id, { aging: { ...row.aging, ...patch } })
  }

  function updateIssuance(id: string, patch: Partial<IssuanceBreakdown>): void {
    const row = sheet.value.products.find((p) => p.id === id)
    if (!row || readonly.value) return
    updateProduct(id, { issuance: { ...row.issuance, ...patch } })
  }

  function updateAccountSplit(id: string, patch: Partial<ReversalAccountSplit>): void {
    const row = sheet.value.products.find((p) => p.id === id)
    if (!row || readonly.value) return
    updateProduct(id, { accountSplit: { ...row.accountSplit, ...patch } })
  }

  function addProduct(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: [...sheet.value.products, emptyReversalItem()],
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
    updateIssuance,
    updateAccountSplit,
    addProduct,
    addRow,
    removeProduct,
    removeRow,
  }
}

export default useF2ImpairmentReversal
