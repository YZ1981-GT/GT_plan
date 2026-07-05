/**
 * useG14ExternalCross — G14-2 与 D1/D2/D5/G4/G5 等源科目 ECL 勾稽
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  type G14DetailRowLike,
  findG14EclMismatches,
  formatG14EclCrossMessage,
  parseExternalAmountCache,
} from './gCycleExternalCross'
import type { ChecklistResponse } from './useF1FormData'

const CACHE_ITEM_ID = 'G14-ext-source-ecl'
const EVENT_NAME = 'g-cycle:source-ecl'

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
    const d = (e as CustomEvent<{ rowKey?: string; amount?: number }>).detail
    const rowKey = String(d?.rowKey ?? '').trim()
    if (!rowKey || d?.amount == null) return
    applySourceAmount(rowKey, d.amount)
  }

  onMounted(() => {
    window.addEventListener(EVENT_NAME, onSourceEclEvent)
  })
  onBeforeUnmount(() => {
    window.removeEventListener(EVENT_NAME, onSourceEclEvent)
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
