/**
 * useB22ASyncMode — B22A 控制矩阵的统一在线编辑接桥 composable。
 *
 * spec: b-cycle-sync-foundation-and-first-canary · Task 19
 *
 * 参照 D4 的 useD4SyncMode 范式，消灭 legacy useWorkpaperEntryDualMode 的 6 类 bug：
 *   ① 健康端点 → fetchOnlyOfficeHealthy 模块级缓存
 *   ② 竞态兜底 → switchMode 内 await checkOoHealth(true)
 *   ③ 门禁 → 不在 modeOptions disabled，移入 switchMode
 *   ④ descriptor → syncBridge.descriptor
 *   ⑤ busy 态 → WP_BRIDGE_IN_FLIGHT_STATES
 *   ⑥ clean close → leaveWithoutSaving
 *
 * 🔴 BC-50 制约：B22A 有 11 本候选册，不可依赖 finder 排序。
 *    sheetKey 固定为 'b22a-managed'，由后端 adapter 指定权威册。
 */
import { computed, ref, toRef, type Ref } from 'vue'
import {
  useWorkpaperSyncBridge,
  WP_BRIDGE_IN_FLIGHT_STATES,
  type WorkpaperSyncFlushResult,
} from '../sync/useWorkpaperSyncBridge'
import { capabilityForEntry } from '../sync/workpaperSyncCapability'
import { fetchOnlyOfficeHealthy } from '../sync/onlyOfficeHealth'

export {
  fetchOnlyOfficeHealthy,
} from '../sync/onlyOfficeHealth'

/** B22A entry ID（manifest 登记值）。 */
export const B22A_SYNC_ENTRY_ID = 'xlsx/gt-b22-a-control-matrix'

/** B22A managed sheet key（后端 adapter 对应 key）。 */
export const B22A_SHEET_KEY = 'b22a-managed'

/** 在线编辑视图标签。 */
export const B22A_ONLINE_EDIT_LABEL = '在线编辑'

export interface UseB22ASyncModeOptions {
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  readonly isReadonly: Ref<boolean>
  /** flush 钩子：序列化 allResponses 为 projection。 */
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  /** 重载钩子：loadAll + initialize。 */
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
}

export function useB22ASyncMode(options: UseB22ASyncModeOptions) {
  const entryId = B22A_SYNC_ENTRY_ID

  const ooHealthy = ref(false)

  async function checkOoHealth(forceRefresh = false): Promise<boolean> {
    ooHealthy.value = await fetchOnlyOfficeHealthy(forceRefresh)
    return ooHealthy.value
  }
  // mount 期首探（命中缓存时零成本）
  void checkOoHealth()

  const syncSwitching = ref(false)
  const syncHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

  const syncBridge = useWorkpaperSyncBridge({
    entryId: ref(entryId),
    wpId: options.wpId,
    projectId: options.projectId,
    sheetKey: ref(B22A_SHEET_KEY),
    capability: capabilityForEntry(entryId),
    flushHtml: options.flushHtml,
    reloadHtml: options.reloadHtml,
  })

  const descriptor = computed(() => syncBridge.descriptor.value)

  const busy = computed(
    () =>
      syncSwitching.value
      || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
  )

  /** applied→HTML 是完成重载的合法出口。 */
  function isAppliedHtmlReturn(target: string): boolean {
    return (
      target === '结构化视图'
      && syncBridge.mode.value === 'oo'
      && String(syncBridge.state.value) === 'applied'
    )
  }

  const editorMode = computed<string>({
    get: () => (syncBridge.mode.value === 'oo' ? B22A_ONLINE_EDIT_LABEL : '结构化视图'),
    set: (target: string) => { void switchMode(target) },
  })

  const modeOptions = computed(() =>
    ['结构化视图', B22A_ONLINE_EDIT_LABEL].map(value => ({
      label: value,
      value,
      disabled:
        (busy.value && !isAppliedHtmlReturn(value))
        || (value === B22A_ONLINE_EDIT_LABEL && options.isReadonly.value),
    })),
  )

  async function switchMode(target: string): Promise<void> {
    if (busy.value && !isAppliedHtmlReturn(target)) return
    if (target === B22A_ONLINE_EDIT_LABEL) {
      if (options.isReadonly.value) return
      if (syncBridge.mode.value === 'oo') return
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
      } catch { /* lastError */ }
      finally { syncSwitching.value = false }
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
    return {
      text: syncBridge.mode.value === 'oo' ? 'Excel 在线编辑' : '已同步',
      type: 'success' as const,
    }
  })

  return {
    entryId,
    syncBridge,
    descriptor,
    ooHealthy,
    checkOoHealth,
    editorMode,
    modeOptions,
    switchMode,
    busy,
    feedback,
    syncStateTag,
    syncHostRef,
  }
}

export { toRef }
