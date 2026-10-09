/**
 * useB1OrphanSyncMode — B1 系列孤儿载体底稿的真双向接桥。
 *
 * spec: b-class-orphan-carrier-and-host-inline-lanes · Task 2/8
 *
 * 🔴 承接 useWpDualMode.ts 上的 3 条 entry（b1-evaluation / b1-kaa-check /
 *    b1-risk-assessment）。改线完成后 useWpDualMode.ts 成孤儿须删除（Task 22/23）。
 *
 * 与 useB22BSyncMode 的差异：mode 标签是中文（结构化视图/在线编辑），
 * 对齐 useWpDualMode 的原接口，便于宿主最小改动。
 */
import { computed, ref, type Ref } from 'vue'
import {
  useWorkpaperSyncBridge,
  WP_BRIDGE_IN_FLIGHT_STATES,
  type WorkpaperSyncFlushResult,
} from '../sync/useWorkpaperSyncBridge'
import { capabilityForEntry } from '../sync/workpaperSyncCapability'
import { fetchOnlyOfficeHealthy } from '../sync/onlyOfficeHealth'

const STRUCTURED_LABEL = '结构化视图'
const ONLINE_EDIT_LABEL = '在线编辑'

export interface UseB1OrphanSyncModeOptions {
  readonly entryId: string
  readonly sheetKey: string
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  readonly isReadonly: Ref<boolean>
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
}

export function useB1OrphanSyncMode(options: UseB1OrphanSyncModeOptions) {
  const ooHealthy = ref(false)
  async function checkOoHealth(forceRefresh = false): Promise<boolean> {
    ooHealthy.value = await fetchOnlyOfficeHealthy(forceRefresh)
    return ooHealthy.value
  }
  void checkOoHealth()

  const syncSwitching = ref(false)
  const syncHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

  const syncBridge = useWorkpaperSyncBridge({
    entryId: ref(options.entryId),
    wpId: options.wpId,
    projectId: options.projectId,
    sheetKey: ref(options.sheetKey),
    capability: capabilityForEntry(options.entryId),
    flushHtml: options.flushHtml,
    reloadHtml: options.reloadHtml,
  })

  const descriptor = computed(() => syncBridge.descriptor.value)
  const busy = computed(() =>
    syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
  )

  function isAppliedHtmlReturn(target: string): boolean {
    return target === STRUCTURED_LABEL && syncBridge.mode.value === 'oo' && String(syncBridge.state.value) === 'applied'
  }

  /** mode：中文标签（对齐 useWpDualMode 接口）。 */
  const mode = computed<string>({
    get: () => (syncBridge.mode.value === 'oo' ? ONLINE_EDIT_LABEL : STRUCTURED_LABEL),
    set: (target: string) => { void switchMode(target) },
  })

  const modeOptions = computed(() =>
    [STRUCTURED_LABEL, ONLINE_EDIT_LABEL].map(value => ({
      label: value,
      value,
      disabled: (busy.value && !isAppliedHtmlReturn(value)) || (value === ONLINE_EDIT_LABEL && options.isReadonly.value),
    })),
  )

  async function switchMode(target: string): Promise<void> {
    if (busy.value && !isAppliedHtmlReturn(target)) return
    if (target === ONLINE_EDIT_LABEL) {
      if (options.isReadonly.value || syncBridge.mode.value === 'oo') return
      if (!ooHealthy.value) await checkOoHealth(true)
      if (!ooHealthy.value) return
      syncSwitching.value = true
      try { await syncBridge.switchToOnlyOffice() } catch { /* lastError */ } finally { syncSwitching.value = false }
      return
    }
    if (target !== STRUCTURED_LABEL) return
    if (syncBridge.mode.value === 'oo') {
      syncSwitching.value = true
      try {
        if (String(syncBridge.state.value) === 'applied') await syncBridge.reloadAfterApplied()
        else if (!syncBridge.dirty.value) await syncBridge.leaveWithoutSaving()
        else await syncBridge.switchToHtml()
      } catch { /* lastError */ } finally { syncSwitching.value = false }
    }
  }

  const descriptorReady = computed(() => descriptor.value !== null)
  const feedback = computed(() => syncBridge.feedback.value.message)
  const syncStateTag = computed(() => {
    if (busy.value) return { text: '同步中…', type: 'info' as const }
    if (syncBridge.dirty?.value) {
      return syncBridge.mode.value === 'oo'
        ? { text: 'Excel 侧有未同步改动', type: 'warning' as const }
        : { text: 'HTML 侧有未同步改动', type: 'warning' as const }
    }
    if (String(syncBridge.state.value).includes('error') || String(syncBridge.lastError?.value || '')) {
      return { text: '同步失败，请重试', type: 'danger' as const }
    }
    return { text: syncBridge.mode.value === 'oo' ? 'Excel 在线编辑' : '已同步', type: 'success' as const }
  })

  return {
    entryId: options.entryId, syncBridge, descriptor, descriptorReady,
    ooHealthy, checkOoHealth, mode, modeOptions, switchMode,
    busy, feedback, syncStateTag, syncHostRef,
  }
}
