/**
 * useG14ExternalCross — G14-2 与 D1/D2/D5/D6/F1/G4/G5/G6 源科目 ECL 勾稽
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  type G14DetailRowLike,
  findG14EclMismatches,
  formatG14EclCrossMessage,
  parseExternalAmountCache,
} from './gCycleExternalCross'
import {
  G_CYCLE_SOURCE_ECL_EVENT,
  resolveG14EclRowKey,
} from './gCycleSourceEcl'
import type { ChecklistResponse } from './useF1FormData'

const CACHE_ITEM_ID = 'G14-ext-source-ecl'

export interface UseG14ExternalCrossOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  detailRows: Ref<G14DetailRowLike[]> | ComputedRef<G14DetailRowLike[]>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}

export function useG14ExternalCross(options: UseG14ExternalCrossOptions) {
  const externalByRowKey = ref<Record<string, number>>({})

  function loadCache(): void {
    externalByRowKey.value = parseExternalAmountCache(
      options.allResponses.value.get(CACHE_ITEM_ID)?.remark,
    )
  }

  watch(() => options.allResponses.value.get(CACHE_ITEM_ID)?.remark, loadCache, { immediate: true })

  function persistCache(): void {
    options.debouncedSave(CACHE_ITEM_ID, { remark: JSON.stringify(externalByRowKey.value) })
  }

  function applySourceAmount(rowKey: string, amount: number): void {
    if (!rowKey) return
    externalByRowKey.value = { ...externalByRowKey.value, [rowKey]: amount }
    persistCache()
  }

  function onSourceEclEvent(e: Event): void {
    const d = (e as CustomEvent<{ rowKey?: string; source?: string; amount?: number }>).detail
    if (d?.amount == null) return
    const rowKey = resolveG14EclRowKey(String(d.rowKey || d.source || ''))
    if (!rowKey) return
    applySourceAmount(rowKey, d.amount)
  }

  onMounted(() => {
    window.addEventListener(G_CYCLE_SOURCE_ECL_EVENT, onSourceEclEvent)
  })
  onBeforeUnmount(() => {
    window.removeEventListener(G_CYCLE_SOURCE_ECL_EVENT, onSourceEclEvent)
  })

  const mismatches = computed(() =>
    findG14EclMismatches(options.detailRows.value, externalByRowKey.value),
  )

  const crossMessage = computed(() => formatG14EclCrossMessage(mismatches.value))

  const hasExternalData = computed(() =>
    Object.keys(externalByRowKey.value).length > 0,
  )

  const isReconciled = computed(() => hasExternalData.value && mismatches.value.length === 0)

  return {
    externalByRowKey,
    mismatches,
    crossMessage,
    hasExternalData,
    isReconciled,
    applySourceAmount,
  }
}
