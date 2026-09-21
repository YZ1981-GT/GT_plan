/**
 * useD4SyncMode — D4 dedicated sync sheet 的**统一**在线编辑接桥 composable。
 *
 * ═══ 为什么存在（治本，消灭一整类复发 bug）═══════════════════════════════════
 *
 * D4 有 20+ 张 dedicated sync 底稿，此前**每张各自 copy-paste** 同一套 60 行接桥：
 * `ooHealthy` ref + `checkOoHealth()` + `useWorkpaperSyncBridge(...)` + `syncOoDescriptor`
 * computed + `syncBusy` + `editorMode`/`modeOptions`/`switchMode`。每份拷贝都是一次独立
 * 写错的机会——2026-09-21 一次会话就在这堆拷贝里踩了 **6 类真 bug**：
 *   ① `checkOoHealth` 打错端点 `/api/onlyoffice/health`（404，5 处）+ 读错字段
 *      `status==='healthy'`（正确是 `.healthy`）→ ooHealthy 恒 false → 在线编辑锁死；
 *   ② switchMode/activateOnlineEdit 读初始 false 的 ooHealthy 静默 return → 点击后
 *      从不触发 store-projection/materialize（L1 hits.length=0 真因）；
 *   ③ modeOptions 用 `disabled: !ooHealthy` 在健康未就绪时锁死切换器，点击被忽略；
 *   ④ 漏声明 `descriptor` computed → OO 宿主永不挂载；
 *   ⑤/⑥ 其余渲染/TDZ 崩溃虽非本 composable 直辖，但同源于「每张各写一遍」的碎片化。
 *
 * 本 composable 把这 4 处（健康 / 竞态 / 门禁 / descriptor）**收敛到单一正确实现**：
 * 组件只提供 `sheetKey` + `flushHtml`/`reloadHtml` 钩子 + HTML 侧视图标签，其余全内聚。
 * 新增第 21 张只需调它，从**结构上**不可能再犯上述 6 类 bug。
 *
 * 与既有 `d4/ipo/useD4InterviewSync.ts::useD4InterviewMode` 的关系：那个是**多视图**
 * （卡片/矩阵 + 在线编辑）的早期专用版、且**不建桥/不管健康**（由 D4-30/31 组件另建桥）。
 * 本 composable 是**全量统一版**：建桥 + 健康 + descriptor 一体，覆盖 2 模式与多视图两种
 * 形态（`views` 给几个 HTML 视图就有几个），后续可让 interview 组件迁到本 composable。
 */
import { computed, ref, toRef, type Ref } from 'vue'
import http from '@/utils/http'
import {
  useWorkpaperSyncBridge,
  WP_BRIDGE_IN_FLIGHT_STATES,
  type WorkpaperSyncFlushResult,
} from '../../sync/useWorkpaperSyncBridge'
import { capabilityForEntry } from '../../sync/workpaperSyncCapability'

/** D4 全部 dedicated sync 底稿共享同一 entry（并入 phase5_d4_revenue_detail）。 */
export const D4_SYNC_ENTRY_ID = 'xlsx/gt-d4-operating-revenue'

/** 在线编辑视图标签（统一常量，避免各组件字面量漂移）。 */
export const D4_ONLINE_EDIT_LABEL = '在线编辑'

/**
 * OnlyOffice 健康检查的**唯一正确端点 + 唯一正确字段**。
 *
 * 🔴 单一真源：此前 5 处组件误用 `/api/onlyoffice/health`（404）并读 `status==='healthy'`。
 *    正确端点是 `/api/workpapers/onlyoffice/health`，返回 `{ data: { healthy: boolean } }`。
 *    所有 D4 sync 组件必须经本函数取健康，禁止各自再 http.get 一遍。
 */
export async function fetchOnlyOfficeHealthy(): Promise<boolean> {
  try {
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    return (res.data?.data?.healthy ?? res.data?.healthy ?? false) as boolean
  } catch {
    return false
  }
}

export interface UseD4SyncModeOptions {
  /** 本 sheet 的 sync sheet_key（如 `d424-managed`）。 */
  readonly sheetKey: string
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  /** 只读态（切在线编辑禁用）。 */
  readonly isReadonly: Ref<boolean>
  /**
   * HTML 侧视图标签。2 模式给 `['表格视图']`（或 `['结构化视图']`）；多视图给
   * `['卡片视图','矩阵视图']`。`在线编辑` 由本 composable 追加，不要自己塞进来。
   */
  readonly views: readonly string[]
  /** flush 钩子：只交回 projection 与 expected revision，不打端点（同 bridge 约定）。 */
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  /** 重载钩子：切回 HTML 后重新加载结构化数据。 */
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
  /** 覆盖 entryId（默认 D4 共享 entry）；测试或特殊 entry 用。 */
  readonly entryId?: string
}

export function useD4SyncMode(options: UseD4SyncModeOptions) {
  const entryId = options.entryId ?? D4_SYNC_ENTRY_ID
  const views = options.views.length ? [...options.views] : ['表格视图']

  const ooHealthy = ref(false)
  async function checkOoHealth(): Promise<boolean> {
    ooHealthy.value = await fetchOnlyOfficeHealthy()
    return ooHealthy.value
  }
  // mount 期先探一次（异步；switchMode 内还会兜底 await，见下）。
  void checkOoHealth()

  const syncSwitching = ref(false)
  const syncHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

  const syncBridge = useWorkpaperSyncBridge({
    entryId: ref(entryId),
    wpId: options.wpId,
    projectId: options.projectId,
    sheetKey: ref(options.sheetKey),
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

  const htmlView = ref(views[0])

  const editorMode = computed<string>({
    get: () => (syncBridge.mode.value === 'oo' ? D4_ONLINE_EDIT_LABEL : htmlView.value),
    set: (target: string) => { void switchMode(target) },
  })

  // 🔴 不用 `disabled: !ooHealthy`：健康检查是 mount 期异步（端点 ~20ms 但仍可能晚于点击），
  //    disabled 在未就绪时锁死切换器 → 点击被忽略、switchMode 根本不触发（bug ③）。健康门禁
  //    移进 switchMode（await 兜底），切换器保持可点；OO 真不可用时由桥/后端 fail-visible。
  const modeOptions = computed(() =>
    [...views, D4_ONLINE_EDIT_LABEL].map(value => ({
      label: value,
      value,
      disabled: busy.value || (value === D4_ONLINE_EDIT_LABEL && options.isReadonly.value),
    })),
  )

  async function switchMode(target: string): Promise<void> {
    if (busy.value) return
    if (target === D4_ONLINE_EDIT_LABEL) {
      if (options.isReadonly.value) return
      if (syncBridge.mode.value === 'oo') return
      // 🔴 竞态兜底（bug ②）：点击可能早于 mount 期 checkOoHealth() 响应到达，此时
      //    ooHealthy 仍为初始 false。健康未就绪则**当场 await 一次**再判定，OO 真不可用
      //    才 return（fail-visible 由桥/后端给），绝不因「健康还没探到」静默吞掉点击。
      if (!ooHealthy.value) await checkOoHealth()
      if (!ooHealthy.value) return
      syncSwitching.value = true
      // 🔴 桥的 switchToOnlyOffice/switchToHtml 失败时会先把错误写进 `syncBridge.lastError`
      //    （sticky，供组件 fail-visible 展示）再 rethrow。本函数是 `editorMode` computed
      //    setter 的落点（`set: (target) => { void switchMode(target) }`），调用方拿不到
      //    这个 promise、也没有地方能 catch —— 若不在此吞掉，会变成 unhandled rejection
      //    （浏览器控制台报红 + 测试运行时污染其他用例）。错误已经通过 lastError 展示，
      //    这里 catch 后静默即可，不需要再抛第二遍。
      try { await syncBridge.switchToOnlyOffice() } catch { /* 已记入 lastError，见上 */ } finally { syncSwitching.value = false }
      return
    }
    if (!views.includes(target)) return
    htmlView.value = target
    if (syncBridge.mode.value === 'oo') {
      syncSwitching.value = true
      try {
        if (String(syncBridge.state.value) === 'applied') await syncBridge.reloadAfterApplied()
        else await syncBridge.switchToHtml()
      } catch { /* 已记入 lastError，见上 switchToOnlyOffice 分支同款说明 */ }
      finally { syncSwitching.value = false }
    }
  }

  /** 切在线编辑前立即 flush（清 debounce + 派发落库），供组件在 flushHtml 前调用。 */
  const feedback = computed(() => syncBridge.feedback.value.message)

  /** 统一同步状态标签（组件工具栏用，语义与旧各组件 syncStateTag 一致）。 */
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

/** `toRef(props, 'x')` 的便捷别名（组件传 props 字段时用），避免各组件重复 import toRef。 */
export { toRef }
