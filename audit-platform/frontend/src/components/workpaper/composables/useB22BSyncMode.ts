/**
 * useB22BSyncMode — B22B 系列底稿（控制矩阵 + 缺陷评价）的统一在线编辑接桥。
 *
 * spec: b-class-shared-base-carrier-lanes · Task 2/5
 *
 * 🔴 B22B 被两条 entry 共用（BC-45 对偶形态）：
 *   - xlsx/gt-b22-b-control-matrix → B22B 控制矩阵
 *   - xlsx/gt-b22-b-deficiency-evaluation → B22B 缺陷评价
 * 本 composable 接收 entryId 参数区分两者。
 */
import { computed, ref, type Ref } from 'vue'
import {
  useWorkpaperSyncBridge,
  WP_BRIDGE_IN_FLIGHT_STATES,
  type WorkpaperSyncFlushResult,
} from '../sync/useWorkpaperSyncBridge'
import { capabilityForEntry } from '../sync/workpaperSyncCapability'
import { fetchOnlyOfficeHealthy } from '../sync/onlyOfficeHealth'

export const B22B_CM_ENTRY_ID = 'xlsx/gt-b22-b-control-matrix'
export const B22B_DE_ENTRY_ID = 'xlsx/gt-b22-b-deficiency-evaluation'
const ONLINE_EDIT_LABEL = '在线编辑'

export interface UseB22BSyncModeOptions {
  readonly entryId: string
  readonly sheetKey: string
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  readonly isReadonly: Ref<boolean>
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
}

export function useB22BSyncMode(options: UseB22BSyncModeOptions) {
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
    return target === '结构化视图' && syncBridge.mode.value === 'oo' && String(syncBridge.state.value) === 'applied'
  }

  const editorMode = computed<string>({
    get: () => (syncBridge.mode.value === 'oo' ? ONLINE_EDIT_LABEL : '结构化视图'),
    set: (target: string) => { void switchMode(target) },
  })

  const modeOptions = computed(() =>
    ['结构化视图', ONLINE_EDIT_LABEL].map(value => ({
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
    if (target !== '结构化视图') return
    if (syncBridge.mode.value === 'oo') {
      syncSwitching.value = true
      try {
        if (String(syncBridge.state.value) === 'applied') await syncBridge.reloadAfterApplied()
        else if (!syncBridge.dirty.value) await syncBridge.leaveWithoutSaving()
        else await syncBridge.switchToHtml()
      } catch { /* lastError */ } finally { syncSwitching.value = false }
    }
  }

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

  return { entryId: options.entryId, syncBridge, descriptor, ooHealthy, checkOoHealth, editorMode, modeOptions, switchMode, busy, feedback, syncStateTag, syncHostRef }
}
