import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import {
  readEntrySyncReadiness,
  type EntrySyncReadiness,
  type WorkpaperSyncEntryScope,
} from './workpaperSyncApi'
import { WORKPAPER_SYNC_MANIFEST, type WorkpaperSyncManifestEntry } from './workpaperSyncManifest.generated'

// 消费完整能力合同，不把生成清单当前快照的字面量联合作为永久能力边界。
const manifestEntries: readonly WorkpaperSyncManifestEntry[] = WORKPAPER_SYNC_MANIFEST
import {
  deriveEntrySyncPresentation,
  type EntrySyncLoadState,
} from './entrySyncPresentation'

export interface UseEntrySyncReadinessOptions {
  projectId: MaybeRefOrGetter<string>
  wpId: MaybeRefOrGetter<string>
  entryId: MaybeRefOrGetter<string>
}

const IN_FLIGHT = new Map<string, Promise<EntrySyncReadiness>>()

function scopeKey(scope: WorkpaperSyncEntryScope): string {
  return `${scope.projectId}\u0000${scope.wpId}\u0000${scope.entryId}`
}

function fetchSingleFlight(scope: WorkpaperSyncEntryScope): Promise<EntrySyncReadiness> {
  const key = scopeKey(scope)
  const existing = IN_FLIGHT.get(key)
  if (existing) return existing
  const request = readEntrySyncReadiness(scope).finally(() => {
    if (IN_FLIGHT.get(key) === request) IN_FLIGHT.delete(key)
  })
  IN_FLIGHT.set(key, request)
  return request
}

function modes(capability: EntrySyncReadiness['capability'], counterpart: string | null) {
  if (capability === 'bidirectional') return ['html', 'oo'] as const
  if (capability === 'single_html') return ['html'] as const
  if (capability === 'single_onlyoffice') return ['oo'] as const
  if (capability === 'unreachable') return [] as const
  return counterpart === 'exists' ? (['html', 'oo'] as const) : (['oo'] as const)
}

function staticReadiness(entryId: string): EntrySyncReadiness | null {
  const entry = manifestEntries.find((row) => row.entryId === entryId)
  if (!entry) return null
  const pending = entry.capability === null
  const runtimeReady = entry.capability === 'single_html' || entry.capability === 'single_onlyoffice'
  return {
    entry_id: entry.entryId,
    effective_entry_id: entry.effectiveEntryId,
    capability: entry.capability,
    adjudication_state: entry.adjudicationState,
    allowed_modes: modes(entry.capability, entry.htmlCounterpartVerdict),
    can_claim_bidirectional: false,
    runtime: {
      ready: runtimeReady,
      adapter_id: null,
      authority_model: null,
      definition_bundle_id: null,
      definition_bundle_sha256: null,
      typed_slots_complete: false,
      typed_slots: [],
      representation_id: null,
      representation_generation: null,
    },
    acceptance: {
      state: runtimeReady ? 'not_applicable' : 'missing',
      stale: false,
      run_id: null,
      required_scenario_set_digest: null,
    },
    reason: pending
      ? {
          code: 'ENTRY_UNADJUDICATED',
          message: '该底稿尚未完成双向能力裁决。',
          next_action: `待处理：${entry.capabilityTargetBlockedBy.join('、') || '逐项核对'}`,
        }
      : entry.capability === 'bidirectional'
        ? {
            code: 'RUNTIME_STATUS_REQUIRED',
            message: '尚未读取当前项目底稿的运行时同步状态。',
            next_action: '进入项目底稿后重新检查。',
          }
        : null,
  }
}

export function useEntrySyncReadiness(options: UseEntrySyncReadinessOptions) {
  const readiness = ref<EntrySyncReadiness | null>(null)
  const loadState = ref<EntrySyncLoadState>('loading')
  const errorMessage = ref('')
  let epoch = 0

  async function refresh(): Promise<void> {
    const currentEpoch = ++epoch
    const entryId = String(toValue(options.entryId) ?? '').trim()
    const projectId = String(toValue(options.projectId) ?? '').trim()
    const wpId = String(toValue(options.wpId) ?? '').trim()
    const fallback = staticReadiness(entryId)
    if (!entryId || !projectId || !wpId) {
      readiness.value = fallback
      loadState.value = fallback ? 'ready' : 'error'
      errorMessage.value = fallback ? '' : '缺少底稿同步身份'
      return
    }

    // 🔴 首帧就给出可展示的裁决（generated manifest 的静态结果），并把状态标成
    //    `revalidating` 而不是 `loading`：宿主的模式开关可见性因此不会在运行时结果到达前
    //    先消失再出现（闪跳）。没有任何可展示值时才落 `loading`。
    if (readiness.value === null && fallback !== null) readiness.value = fallback
    loadState.value = readiness.value === null ? 'loading' : 'revalidating'
    errorMessage.value = ''
    try {
      const result = await fetchSingleFlight({ projectId, wpId, entryId })
      if (currentEpoch !== epoch) return
      readiness.value = result
      loadState.value = 'ready'
    } catch (error) {
      if (currentEpoch !== epoch) return
      readiness.value = fallback
      loadState.value = 'error'
      errorMessage.value = error instanceof Error ? error.message : '同步状态读取失败'
    }
  }

  watch(
    () => [toValue(options.projectId), toValue(options.wpId), toValue(options.entryId)],
    () => { void refresh() },
    { immediate: true },
  )

  const presentation = computed(() =>
    deriveEntrySyncPresentation(readiness.value, loadState.value),
  )

  return {
    readiness,
    loadState,
    errorMessage,
    presentation,
    refresh,
  }
}
