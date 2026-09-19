/**
 * useF2ContractCost — F2-55 合同履约成本构成明细表
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  debouncedPublishF2SpeDisclosureNote,
  publishF2SpeSubstantiveAdjudicated,
} from './useF2SpeEventBus'
import {
  defaultContractCostSheet,
  enrichContractCostProjects,
  calcContractCostTotals,
  migrateContractCostSheet,
  emptyContractCostProject,
  type ContractCostSheet,
  type ContractCostProject,
  type CostCategoryKey,
} from './useF2ContractCostFormulas'

/** @deprecated 兼容旧类型名 */
export type ContractCostRow = ContractCostProject
export type ContractCostSegment =
  | 'basic' | 'opening' | 'increase' | 'decrease' | 'end' | 'audit'

const ROWS_KEY = 'F2-55-rows'
const NOTE_KEY = 'F2-55-note'

export function useF2ContractCost(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let adjudicatedTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<ContractCostSheet>(defaultContractCostSheet())
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    // 自回声守卫：persist() 写回后 watcher 会再次触发 load，
    // 若内容与内存一致则跳过，避免 migrate 的空行裁剪吃掉刚新增的空行。
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateContractCostSheet(parsed)
        if (migrated) {
          const beforeCount = Array.isArray(parsed?.products)
            ? parsed.products.length
            : (Array.isArray(parsed) ? parsed.length : 0)
          sheet.value = migrated
          // 裁掉历史预留空行并写回，避免刷新后再次出现。
          if (!readonly.value && beforeCount > migrated.products.length) {
            opts.allResponses.value.set(ROWS_KEY, {
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
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedProducts = computed(() => enrichContractCostProjects(sheet.value.products))
  const enrichedRows = enrichedProducts

  const columnTotals = computed(() => calcContractCostTotals(enrichedProducts.value))

  const totals = computed(() => ({
    end_subtotal: columnTotals.value.end_subtotal,
    audited_subtotal: columnTotals.value.audited_subtotal,
  }))

  const highlightCount = computed(() =>
    enrichedProducts.value.filter((r) => r.highlight).length,
  )

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
    }
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

  function updateProduct(id: string, patch: Partial<ContractCostProject>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: sheet.value.products.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }
    persist()
  }

  function updateRow(id: string, patch: Partial<ContractCostProject>): void {
    updateProduct(id, patch)
  }

  function updatePeriodAmount(
    id: string,
    period: 'opening' | 'increase' | 'decrease' | 'adj',
    key: CostCategoryKey,
    value: number,
  ): void {
    updateProduct(id, { [`${period}_${key}`]: value } as Partial<ContractCostProject>)
  }

  function addProduct(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      products: [...sheet.value.products, emptyContractCostProject()],
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

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debouncedPublishF2SpeDisclosureNote('contract-cost', val)
    persist()
  })

  watch(
    () => totals.value.audited_subtotal,
    (amount) => {
      if (adjudicatedTimer) clearTimeout(adjudicatedTimer)
      adjudicatedTimer = setTimeout(() => {
        adjudicatedTimer = null
        publishF2SpeSubstantiveAdjudicated({
          wpCode: 'F2-special',
          accountCode: '1410',
          auditedAmount: amount,
        })
      }, 2000)
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
    if (adjudicatedTimer) clearTimeout(adjudicatedTimer)
  })

  return {
    sheet,
    enrichedProducts,
    enrichedRows,
    columnTotals,
    totals,
    highlightCount,
    auditNote,
    updateProduct,
    updateRow,
    updatePeriodAmount,
    addProduct,
    addRow,
    removeProduct,
    removeRow,
  }
}

export default useF2ContractCost
