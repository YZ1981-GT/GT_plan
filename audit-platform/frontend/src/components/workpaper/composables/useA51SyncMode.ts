/**
 * useA51SyncMode — A5-1 现金流量表审计 的统一 sync bridge 接桥 composable。
 *
 * 🔴 改线自 useA51EditorMode（legacy），参照 D4 的 useD4SyncMode 模式。
 *
 * ═══ 改线动机（spec: a-cycle-sync-foundation-and-first-canary · Task 13）═══
 *
 * A5-1 此前用 useA51EditorMode（legacy 健康检查 + 直挂 GtOnlyOfficeSheet），
 * 与 D4 的 20+ 张 sheet 各自 copy-paste 60 行接桥的碎片化一样，是双向回写
 * 改线的阻塞点。本 composable 把健康探测、descriptor、mode 管理收敛到
 * sync bridge 统一架构。
 *
 * ═══ mode 载体：形态 2（label/value 分离）═══
 *
 * 🔴 依 AC-41：A 域 17 条 entry 把中文界面文案直接作 mode 逻辑值（形态 1），
 * 改文案即破坏逻辑。本 composable 采用形态 2——{label, value} 分离，
 * 抄 a112/a38 已有正面样板。OO 值是 'excel'（非 'onlyoffice'，依 AF-P18）。
 *
 * ═══ 与 useD4SyncMode 的差异 ═══
 *
 * - D4 共享一个 entry（20+ sheet 全归 xlsx/gt-d4-operating-revenue）；
 *   A5-1 是独立 entry（xlsx/gt-a51-cashflow-audit）
 * - D4 已有后端 adapter（capability=bidirectional）；
 *   A5-1 当前 capability=single_onlyoffice（adapter 未注册，BP-5 成立）
 * - 因此本 composable **暂走 single_onlyoffice 路径**——
 *   sync bridge 在该 capability 下仍能管理 descriptor + forcesave + leave，
 *   不做 store projection 投影（那需要 bidirectional）
 */
import { computed, ref, toRef, type Ref } from 'vue'
import {
  useWorkpaperSyncBridge,
  WP_BRIDGE_IN_FLIGHT_STATES,
  type WorkpaperSyncFlushResult,
} from '../sync/useWorkpaperSyncBridge'
import { capabilityForEntry } from '../sync/workpaperSyncCapability'
export {
  fetchOnlyOfficeHealthy,
  __resetOoHealthCacheForTests,
  OO_HEALTH_TTL_MS,
} from '../sync/onlyOfficeHealth'
import { fetchOnlyOfficeHealthy } from '../sync/onlyOfficeHealth'

/** A5-1 独立 entry id。 */
export const A51_SYNC_ENTRY_ID = 'xlsx/gt-a51-cashflow-audit'

/**
 * 🔴 形态 2 mode 值（AC-41）——逻辑值与显示标签分离。
 * 改文案不再破坏逻辑（形态 1 的核心缺陷）。
 * OO 值用 'excel'（非 'onlyoffice'，依 AF-P18——A 域 'onlyoffice' 字面量 = 0）。
 */
const MODE_STRUCTURED = 'structured' as const
const MODE_EXCEL = 'excel' as const
const MODE_LABEL_STRUCTURED = '结构化视图'
const MODE_LABEL_EXCEL = '在线编辑'

export interface UseA51SyncModeOptions {
  /** A5-1 的 sheetKey（默认 'a51-managed'）。 */
  readonly sheetKey?: string
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  readonly isReadonly: Ref<boolean>
  /** flush 钩子：清 debounce + 读 store projection。 */
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  /** 重载钩子：切回结构化视图后重新加载数据。 */
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
}

export function useA51SyncMode(options: UseA51SyncModeOptions) {
  const sheetKey = options.sheetKey ?? 'a51-managed'
  const entryId = A51_SYNC_ENTRY_ID

  const ooHealthy = ref(false)
  async function checkOoHealth(forceRefresh = false): Promise<boolean> {
    ooHealthy.value = await fetchOnlyOfficeHealthy(forceRefresh)
    return ooHealthy.value
  }
  // mount 期先探一次
  void checkOoHealth()

  const syncSwitching = ref(false)
  const syncHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

  const syncBridge = useWorkpaperSyncBridge({
    entryId: ref(entryId),
    wpId: options.wpId,
    projectId: options.projectId,
    sheetKey: ref(sheetKey),
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

  /**
   * 🔴 形态 2 editorMode（label/value 分离）——依 AC-41 从形态 1 收敛。
   * 逻辑值是 'structured' / 'excel'，中文标签仅用于 modeOptions 的 label。
   */
  const editorMode = computed<string>({
    get: () => (syncBridge.mode.value === 'oo' ? MODE_EXCEL : MODE_STRUCTURED),
    set: (target: string) => { void switchMode(target) },
  })

  const modeOptions = computed(() =>
    [
      { label: MODE_LABEL_STRUCTURED, value: MODE_STRUCTURED },
      { label: MODE_LABEL_EXCEL, value: MODE_EXCEL },
    ].map(opt => ({
      ...opt,
      disabled:
        (busy.value && !(opt.value === MODE_STRUCTURED && String(syncBridge.state.value) === 'applied'))
        || (opt.value === MODE_EXCEL && options.isReadonly.value),
    })),
  )

  async function switchMode(target: string): Promise<void> {
    if (busy.value && !(target === MODE_STRUCTURED && String(syncBridge.state.value) === 'applied')) return
    if (target === MODE_EXCEL) {
      if (options.isReadonly.value) return
      if (syncBridge.mode.value === 'oo') return
      if (!ooHealthy.value) await checkOoHealth(true)
      if (!ooHealthy.value) return
      syncSwitching.value = true
      try { await syncBridge.switchToOnlyOffice() } catch { /* 已记入 lastError */ } finally { syncSwitching.value = false }
      return
    }
    if (target !== MODE_STRUCTURED) return
    if (syncBridge.mode.value === 'oo') {
      syncSwitching.value = true
      try {
        if (String(syncBridge.state.value) === 'applied') await syncBridge.reloadAfterApplied()
        else if (!syncBridge.dirty.value) await syncBridge.leaveWithoutSaving()
        else await syncBridge.switchToHtml()
      } catch { /* 已记入 lastError */ }
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
