/**
 * useF2ProductionCostDetail — F2-41 生产成本明细表（项目×月度矩阵）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  defaultProdCostBlocks,
  enrichProdCostBlock,
  migrateToProdCostBlocks,
  emptyProdCostBlock,
  sumBlocksYearEnd,
  type ProdCostProductBlock,
  type ProdCostMatrixRow,
  type ProdCostRowKey,
  type ProdCostMonthKey,
} from './useF2ProductionCostMatrixFormulas'

const ROWS_KEY = 'F2-41-rows'
const NOTE_KEY = 'F2-41-note'

export function useF2ProductionCostDetail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const blocks = ref<ProdCostProductBlock[]>(defaultProdCostBlocks())
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateToProdCostBlocks(parsed)
        if (migrated?.length) blocks.value = migrated
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedBlocks = computed(() => blocks.value.map((b) => enrichProdCostBlock(b)))

  const totals = computed(() => {
    const eb = enrichedBlocks.value
    return {
      yearEndTotal: sumBlocksYearEnd(eb),
      rawMaterial: eb.reduce((s, b) => s + (b.rows.find((r) => r.key === 'rawMaterial')?.total ?? 0), 0),
      labor: eb.reduce((s, b) => s + (b.rows.find((r) => r.key === 'labor')?.total ?? 0), 0),
      overhead: eb.reduce((s, b) => s + (b.rows.find((r) => r.key === 'overhead')?.total ?? 0), 0),
    }
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
      remark: JSON.stringify(blocks.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function updateBlock(id: string, patch: Partial<ProdCostProductBlock>): void {
    if (readonly.value) return
    blocks.value = blocks.value.map((b) => (b.id === id ? { ...b, ...patch } : b))
    persist()
  }

  function updateCell(
    blockId: string,
    rowKey: ProdCostRowKey,
    monthKey: ProdCostMonthKey,
    value: number,
  ): void {
    if (readonly.value) return
    blocks.value = blocks.value.map((b) => {
      if (b.id !== blockId) return b
      return {
        ...b,
        rows: b.rows.map((r) => {
          if (r.key !== rowKey) return r
          return { ...r, months: { ...r.months, [monthKey]: value } }
        }),
      }
    })
    persist()
  }

  function updateRowMeta(
    blockId: string,
    rowKey: ProdCostRowKey,
    patch: Partial<Pick<ProdCostMatrixRow, 'priorYear' | 'changeReason'>>,
  ): void {
    if (readonly.value) return
    blocks.value = blocks.value.map((b) => {
      if (b.id !== blockId) return b
      return {
        ...b,
        rows: b.rows.map((r) => (r.key === rowKey ? { ...r, ...patch } : r)),
      }
    })
    persist()
  }

  function addBlock(): void {
    if (readonly.value) return
    blocks.value = [...blocks.value, emptyProdCostBlock('')]
    persist()
  }

  function removeBlock(id: string): void {
    if (readonly.value || blocks.value.length <= 1) return
    blocks.value = blocks.value.filter((b) => b.id !== id)
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
    enrichedBlocks,
    totals,
    auditNote,
    updateBlock,
    updateCell,
    updateRowMeta,
    addBlock,
    removeBlock,
  }
}

export default useF2ProductionCostDetail
