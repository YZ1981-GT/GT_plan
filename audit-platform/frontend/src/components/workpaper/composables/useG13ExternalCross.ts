/**
 * useG13ExternalCross — G13-2 与 G1/G8/G9/G10/H3 源科目 FV 变动勾稽
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  G13_FV_SOURCES,
  type G13FvSource,
  type G13DetailRowLike,
  findG13SourceFvMismatches,
  findG13PendingFvSources,
  formatG13SourceFvCrossMessage,
  formatG13PendingFvSourcesMessage,
  isG13SourceFvReconciled,
  parseExternalAmountCache,
  activeG13FvSourcesFromDetail,
} from './gCycleExternalCross'
import { G_CYCLE_SOURCE_FV_EVENT } from './gCycleSourceFv'
import { fetchG13SourcePullSeeds } from './g13SourceDetailPull'
import type { ChecklistResponse } from './useF1FormData'

const CACHE_ITEM_ID = 'G13-ext-source-fv'
const H3_FV_EVENT = 'h3:fair-value-changed'

export interface UseG13ExternalCrossOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  detailRows: Ref<G13DetailRowLike[]> | ComputedRef<G13DetailRowLike[]>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  /** 冷启动：从同项目源底稿拉取 FV 合计写入缓存 */
  projectId?: Ref<string> | ComputedRef<string>
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
  const pullLoading = ref(false)
  const pullMissing = ref<string[]>([])

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

  function onH3FairValueChanged(e: Event): void {
    const d = (e as CustomEvent<{ source?: string; totalFairValueChange?: number; amount?: number }>).detail
    const amount = d?.totalFairValueChange ?? d?.amount
    if (amount == null) return
    applySourceAmount('H3', Number(amount) || 0)
  }

  /** 打开 G13 时主动拉源 FV，不依赖对方底稿是否 mounted */
  async function pullSourceFvFromProject(): Promise<void> {
    const projectId = options.projectId?.value
    if (!projectId || pullLoading.value) return
    pullLoading.value = true
    try {
      const { seeds, missing } = await fetchG13SourcePullSeeds(projectId)
      pullMissing.value = missing
      const fromPull: Partial<Record<G13FvSource, number>> = {}
      for (const s of seeds) {
        const src = s.belongAccount as G13FvSource
        if (!G13_FV_SOURCES.includes(src)) continue
        fromPull[src] = (fromPull[src] ?? 0) + (Number(s.amountInPl) || 0)
      }
      // 有种子的源用拉取值覆盖（避免与事件缓存叠加）；无种子的源保留事件缓存
      for (const src of G13_FV_SOURCES) {
        if (fromPull[src] != null) {
          applySourceAmount(src, fromPull[src]!)
        }
      }
    } catch {
      /* 冷启动可选 */
    } finally {
      pullLoading.value = false
    }
  }

  onMounted(() => {
    window.addEventListener(G_CYCLE_SOURCE_FV_EVENT, onSourceFvEvent)
    window.addEventListener(H3_FV_EVENT, onH3FairValueChanged)
    void pullSourceFvFromProject()
  })
  onBeforeUnmount(() => {
    window.removeEventListener(G_CYCLE_SOURCE_FV_EVENT, onSourceFvEvent)
    window.removeEventListener(H3_FV_EVENT, onH3FairValueChanged)
  })

  const activeSources = computed(() => activeG13FvSourcesFromDetail(options.detailRows.value))

  const pendingSources = computed(() =>
    findG13PendingFvSources(options.detailRows.value, externalBySource.value),
  )

  const mismatches = computed(() =>
    findG13SourceFvMismatches(options.detailRows.value, externalBySource.value),
  )

  const crossMessage = computed(() => {
    const pendingMsg = formatG13PendingFvSourcesMessage(pendingSources.value)
    const mismatchMsg = formatG13SourceFvCrossMessage(mismatches.value)
    if (pendingMsg && mismatchMsg) return `${pendingMsg}；${mismatchMsg}`
    return pendingMsg || mismatchMsg
  })

  const hasExternalData = computed(() =>
    G13_FV_SOURCES.some((s) => externalBySource.value[s] != null),
  )

  const isReconciled = computed(() =>
    isG13SourceFvReconciled(options.detailRows.value, externalBySource.value),
  )

  return {
    externalBySource,
    activeSources,
    pendingSources,
    mismatches,
    crossMessage,
    hasExternalData,
    isReconciled,
    pullLoading,
    pullMissing,
    applySourceAmount,
    pullSourceFvFromProject,
  }
}
