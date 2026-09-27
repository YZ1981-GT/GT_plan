/**
 * useHSyncMode — H 循环（固定资产）全部受管 sheet 的**统一**双模式接桥 composable。
 *
 * spec: `h-cycle-sync-foundation-and-first-canary`（canary H9-2 首用）
 *
 * ═══ 为什么存在 ═══════════════════════════════════════════════════════════════
 *
 * 仓库里同一套接桥已被抄了 10+ 份（D4 曾 20+ 张各抄一遍、F1~F5 五条 lane 各抄一份、
 * G2 一份）。每份拷贝都是一次独立写错的机会，实证代价：
 *   · D4 一次会话在这堆拷贝里踩 **6 类真 bug**（健康端点 404 / 读错字段 / 竞态静默
 *     return / `disabled: !ooHealthy` 锁死切换器 / 漏声明 descriptor / 渲染崩溃）；
 *   · F1 接桥落地后被查出 **4 处致命缺陷**（见 commit `055b7a5a6`）；
 *   · F2 四个宿主各 47 行几乎逐字相同，其中 `catch {}` 静默吞掉保存失败 —— 强制保存
 *     失败时用户界面毫无反应，以为已保存。
 *
 * H 有 **9 条独立 entry + 5 条子入口**。照 F 的做法就是 9~14 份拷贝。本 composable 从
 * 第一条（canary H9）就走统一实现，把健康 / 竞态 / 门禁 / descriptor / 四分支保存
 * / 失败可见**六件事收敛到单一正确实现**，新增 entry 只提供钩子。
 *
 * ═══ 用户要求 → 实现映射（丝滑切换的判据）═══════════════════════════════════
 *
 * 「用户点保存后切换应丝滑；编辑后未保存则可在切换时保存（允许慢）」⇒ OO→HTML 四分支：
 *   ① `state==='applied'`（改动已落库）→ `reloadAfterApplied()`：只重载 HTML，**不**再
 *      发保存请求 ⇒ 秒切；
 *   ② 未改动（`!dirty`）→ `leaveWithoutSaving()`：clean close 直接回表单，**不**发强制
 *      保存 ⇒ 丝滑。改这一处之前这条最常见路径必然走到「冻结 forcesave → Command
 *      Service 返无改动 → 界面红字 + 人留在 OO 里」；
 *   ③ 有改动且可强制保存 → `hostRef.forceSave()`：真保存，**允许慢**（正是用户说的
 *      「切换时保存」）；
 *   ④ 有改动但桥不放行强制保存 → 放人走并**明确告知未同步**（见 `lastNotice`），绝不
 *      静默假装已保存，也绝不把人关在 OO 里没有出口。
 *
 * 切 HTML→OO 侧的丝滑靠 `sync/onlyOfficeHealth` 的 15s TTL 缓存 + 并发去重：切一张底稿
 * 不再多打一次健康探针。
 */
import { computed, ref, toRef, type Ref } from 'vue'
import {
  useWorkpaperSyncBridge,
  WP_BRIDGE_IN_FLIGHT_STATES,
  type WorkpaperSyncFlushResult,
} from '../sync/useWorkpaperSyncBridge'
import { capabilityForEntry } from '../sync/workpaperSyncCapability'
import { fetchOnlyOfficeHealthy } from '../sync/onlyOfficeHealth'
import { hManagedSheetOf, isHOoWiredRowsSheet, type HManagedSheet } from '../sync/hManagedSheets'

/**
 * 受管判定 —— 三个条件同时成立才算「本宿主此刻可切 OO」：
 *   ① 该短码在受管清单里且属**本 entry**（跨 entry 同码会切错桥）；
 *   ② `kind==='rows'`（审定表逐格 mask 走另一套桥，不合并）；
 *   ③ 已真正接桥（受管面会先于接桥面增长，见 `H_OO_WIRED_ROWS_CODES`）。
 */
function hManagedOf(code: string, entryId: string): HManagedSheet | null {
  const s = hManagedSheetOf(code)
  return s && s.entryId === entryId && s.kind === 'rows' && isHOoWiredRowsSheet(code) ? s : null
}

/** 双模式取值域 —— 与 H 各宿主既有 `el-segmented` 的 value 形态一致（不是中文标签）。 */
export type HRenderMode = 'html' | 'onlyoffice'

/** 工具栏标签默认值（各宿主一致，避免字面量漂移）。 */
export const H_HTML_MODE_LABEL = '结构化视图'
export const H_ONLINE_EDIT_LABEL = '在线编辑'

/** 宿主里 `WorkpaperSyncEditorHost` 的 ref 形态（只用到 forceSave）。 */
export interface HSyncEditorHostRef {
  forceSave: () => Promise<{ operationId: string }>
}

export interface UseHSyncModeOptions {
  /** entry id（如 `xlsx/gt-h9-lease-liabilities`）。 */
  readonly entryId: string
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  /**
   * 当前 sheet 短码（宿主 `currentSheet`）。受管判定与 `sheetKey` 全由它派生 ——
   * 宿主**不再**内联 `SHEET_KEY_BY_CODE`（见 `sync/hManagedSheets.ts`）。
   */
  readonly currentCode: Ref<string>
  /** 只读态（切在线编辑禁用）。 */
  readonly isReadonly: Ref<boolean>
  /** flush 钩子：只交回 projection 与 expected revision，不打端点（同 bridge 约定）。 */
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  /**
   * 重载钩子：切回 HTML 后重载结构化数据。
   *
   * 🔴 桥的约定是**必须**加载到不低于 `minimumRevision` 的内容（Property 14）。宿主若
   * 只是重打 render-config（读当前 store）通常已满足，但**不得**假设——若宿主有
   * revision 概念应据此等待。
   */
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
  /** HTML 侧标签（多视图宿主可给多个；默认 `['结构化视图']`）。 */
  readonly htmlLabel?: string
}

export function useHSyncMode(options: UseHSyncModeOptions) {
  const { entryId } = options
  const htmlLabel = options.htmlLabel ?? H_HTML_MODE_LABEL

  // ─── 健康（共享 TTL 缓存，切底稿不重打）───────────────────────────────────
  const ooHealthy = ref(false)
  const ooHealthChecking = ref(true)
  /** `forceRefresh=true` 仅用于 `switchMode` 的竞态兜底（用户已点击，需最新状态）。 */
  async function checkOoHealth(forceRefresh = false): Promise<boolean> {
    ooHealthChecking.value = true
    try {
      ooHealthy.value = await fetchOnlyOfficeHealthy(forceRefresh)
      return ooHealthy.value
    } finally {
      ooHealthChecking.value = false
    }
  }
  // mount 期先探一次；命中模块级缓存时几乎零成本。
  void checkOoHealth()

  // ─── 受管判定（从 `sync/hManagedSheets` 派生，宿主不内联 map）──────────────
  const managed = computed(() => hManagedOf(options.currentCode.value, entryId))
  const isManagedSheet = computed(() => managed.value != null)
  const sheetKey = computed(() => managed.value?.sheetKey ?? '')

  // ─── 桥 ───────────────────────────────────────────────────────────────────
  const syncSwitching = ref(false)
  const syncHostRef = ref<HSyncEditorHostRef | null>(null)
  /** 四分支里「放人走但未同步」等需要让用户看见的提示（sticky，切换成功时清空）。 */
  const lastNotice = ref<{ text: string; type: 'warning' | 'danger' } | null>(null)

  const syncBridge = useWorkpaperSyncBridge({
    entryId: ref(entryId),
    wpId: options.wpId,
    projectId: options.projectId,
    sheetKey,
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
   * `applied` 在 in-flight 集合里是为了拦离开/刷新（HTML 还没按 result revision 重载）。
   * 但切回结构化视图**正是**完成那次重载的路径。若 busy 连这项一起锁死，用户永远点不回
   * 表单 —— D4 真栈实测过：operation 已 applied、store 已是新值，分段器却 is-disabled。
   */
  function isAppliedHtmlReturn(target: HRenderMode): boolean {
    return (
      target === 'html'
      && syncBridge.mode.value === 'oo'
      && String(syncBridge.state.value) === 'applied'
    )
  }

  /**
   * 工具栏选项。
   *
   * 🔴 **不用** `disabled: !ooHealthy`：健康检查是 mount 期异步，disabled 在未就绪时
   *    锁死切换器 → 点击被彻底忽略、`switchMode` 根本不触发（D4 bug ③）。健康门禁移进
   *    `switchMode`（await 兜底），切换器保持可点；OO 真不可用时由桥/后端 fail-visible。
   */
  const modeOptions = computed(() => [
    {
      label: htmlLabel,
      value: 'html' as HRenderMode,
      disabled: busy.value && !isAppliedHtmlReturn('html'),
    },
    {
      label: H_ONLINE_EDIT_LABEL,
      value: 'onlyoffice' as HRenderMode,
      disabled: busy.value || options.isReadonly.value || !isManagedSheet.value,
    },
  ])

  /** 当前模式（桥为准）。`v-model` 直接绑它，setter 走 `switchMode`。 */
  const renderMode = computed<HRenderMode>({
    get: () => (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html'),
    set: (target: HRenderMode) => { void switchMode(target) },
  })

  async function switchMode(target: HRenderMode): Promise<void> {
    // applied→HTML 是完成重载的合法出口，不得被 busy 短路。
    if (busy.value && !isAppliedHtmlReturn(target)) return
    if (target === renderMode.value && !isAppliedHtmlReturn(target)) return

    if (target === 'onlyoffice') {
      if (options.isReadonly.value) return
      if (!isManagedSheet.value) return
      if (syncBridge.mode.value === 'oo') return
      // 竞态兜底：点击可能早于 mount 期健康响应到达，此时 ooHealthy 仍为初始 false。
      // 健康未就绪则**当场 await 一次**（绕过 TTL 取最新）再判定，绝不因「还没探到」
      // 静默吞掉用户这次真实点击。
      if (!ooHealthy.value) await checkOoHealth(true)
      if (!ooHealthy.value) {
        lastNotice.value = { text: 'OnlyOffice 服务不可用，暂时只能用结构化视图', type: 'warning' }
        return
      }
      syncSwitching.value = true
      lastNotice.value = null
      try {
        await syncBridge.switchToOnlyOffice()
      } catch {
        // 桥失败时已把错误写进 `lastError`（sticky，供 `syncStateTag` 展示）再 rethrow。
        // 本函数是 computed setter 的落点，调用方拿不到这个 promise ⇒ 不吞就是
        // unhandled rejection（控制台报红 + 污染测试）。错误已可见，不抛第二遍。
        lastNotice.value = { text: '进入在线编辑失败，请重试', type: 'danger' }
      } finally {
        syncSwitching.value = false
      }
      return
    }

    // ─── OO → HTML：四分支 ──────────────────────────────────────────────────
    if (syncBridge.mode.value !== 'oo') {
      syncBridge.persistMode('html')
      return
    }
    syncSwitching.value = true
    try {
      if (String(syncBridge.state.value) === 'applied') {
        // ① 已落库 ⇒ 只重载，不再发保存 ⇒ 秒切
        await syncBridge.reloadAfterApplied()
        lastNotice.value = null
      } else if (!syncBridge.dirty.value) {
        // ② 未改动 ⇒ clean close 直接回表单，不发强制保存 ⇒ 丝滑
        await syncBridge.leaveWithoutSaving()
        lastNotice.value = null
      } else if (syncBridge.canForcesave.value && syncHostRef.value) {
        // ③ 有改动 ⇒ 真保存（允许慢，正是「切换时保存」）
        await syncHostRef.value.forceSave()
        lastNotice.value = null
      } else {
        // ④ 有改动但桥不放行强制保存（`forcesaveUnlocked` 未拿到 / state 不在放行集合）。
        //    放人走避免「关在 OO 里没出口」，但**必须明说未同步** —— 静默 persistMode
        //    会让用户以为已保存（F2 各宿主当前形态即如此）。
        syncBridge.persistMode('html')
        lastNotice.value = {
          text: 'Excel 侧改动未能同步回结构化视图，请重新进入在线编辑并保存',
          type: 'danger',
        }
      }
    } catch {
      // 同上：错误已记入 `lastError`；这里补一条人能看懂的提示，不静默。
      lastNotice.value = { text: '保存回写失败，改动仍在 Excel 侧，请重试', type: 'danger' }
    } finally {
      syncSwitching.value = false
    }
  }

  const feedback = computed(() => syncBridge.feedback.value.message)

  /** 统一同步状态标签（工具栏用）。`lastNotice` 优先 —— 失败必须盖过「已同步」。 */
  const syncStateTag = computed<{ text: string; type: 'info' | 'success' | 'warning' | 'danger' }>(() => {
    if (busy.value) return { text: '同步中…', type: 'info' }
    if (lastNotice.value) return { text: lastNotice.value.text, type: lastNotice.value.type }
    if (syncBridge.dirty?.value) {
      return syncBridge.mode.value === 'oo'
        ? { text: 'Excel 侧有未同步改动', type: 'warning' }
        : { text: 'HTML 侧有未同步改动', type: 'warning' }
    }
    if (String(syncBridge.state.value).includes('error') || syncBridge.lastError?.value) {
      return { text: '同步失败，请重试', type: 'danger' }
    }
    return {
      text: syncBridge.mode.value === 'oo' ? 'Excel 在线编辑' : '已同步',
      type: 'success',
    }
  })

  return {
    entryId,
    syncBridge,
    descriptor,
    ooHealthy,
    ooHealthChecking,
    checkOoHealth,
    isManagedSheet,
    sheetKey,
    renderMode,
    modeOptions,
    switchMode,
    busy,
    feedback,
    lastNotice,
    syncStateTag,
    syncHostRef,
  }
}

/** `toRef(props, 'x')` 便捷别名（组件传 props 字段时用）。 */
export { toRef }
