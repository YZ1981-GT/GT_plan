/**
 * useG13ExternalCross — G13-2 与 G1/G8/G9/G10 源科目 FV 变动勾稽
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  G13_FV_SOURCES,
  type G13FvSource,
  type G13DetailRowLike,
  findG13SourceFvMismatches,
  formatG13SourceFvCrossMessage,
  parseExternalAmountCache,
} from './gCycleExternalCross'
import type { ChecklistResponse } from './useF1FormData'

const CACHE_ITEM_ID = 'G13-ext-source-fv'
const EVENT_NAME = 'g-cycle:source-fv'

export interface UseG13ExternalCrossOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  detailRows: Ref<G13DetailRowLike[]> | ComputedRef<G13DetailRowLike[]>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}

function mergeSourceAmount(
  cache: Record<string, number>,
  source: G13FvSource,
  amount: number,
): Record<string, number> {
  return { ...cache, [source]: amount }
}

export function useG13ExternalCross(options: UseG13ExternalCrossOptions) {
  const externalBySource = ref<Partial<Record<G13FvSource, number>>>({})

  function loadCache(): void {
    externalBySource.value = parseExternalAmountCache(
      options.allResponses.value.get(CACHE_ITEM_ID)?.remark,
    ) as Partial<Record<G13FvSource, number>>
  }

  watch(() => options.allResponses.value.get(CACHE_ITEM_ID)?.remark, loadCache, { immediate: true })

  function persistCache(): void {
    options.debouncedSave(CACHE_ITEM_ID, { remark: JSON.stringify(externalBySource.value) })
  }

  function applySourceAmount(source: G13FvSource, amount: number): void {
    if (!G13_FV_SOURCES.includes(source)) return
    externalBySource.value = mergeSourceAmount(
      externalBySource.value as Record<string, number>,
      source,
      amount,
    )
    persistCache()
  }

  function onSourceFvEvent(e: Event): void {
    const d = (e as CustomEvent<{ source?: string; amount?: number }>).detail
    const source = String(d?.source ?? '').trim() as G13FvSource
    if (!source || d?.amount == null) return
    applySourceAmount(source, d.amount)
  }

  onMounted(() => {
    window.addEventListener(EVENT_NAME, onSourceFvEvent)
  })
  onBeforeUnmount(() => {
    window.removeEventListener(EVENT_NAME, onSourceFvEvent)
  })

  const mismatches = computed(() =>
    findG13SourceFvMismatches(options.detailRows.value, externalBySource.value),
  )

  const crossMessage = computed(() => formatG13SourceFvCrossMessage(mismatches.value))

  const hasExternalData = computed(() =>
    G13_FV_SOURCES.some((s) => externalBySource.value[s] != null),
  )

  const isReconciled = computed(() => hasExternalData.value && mismatches.value.length === 0)

  return {
    externalBySource,
    mismatches,
    crossMessage,
    hasExternalData,
    isReconciled,
    applySourceAmount,
  }
}
