/**
 * useARenderModeSwitch — A 循环（报表 / 调整 / 沟通类底稿）统一在线编辑双模式接桥。
 *
 * spec: `a-cycle-online-edit-driver-closure`
 *
 * ═══ 为什么存在 ═══════════════════════════════════════════════════════════════
 *
 * commit `f20789453`「a-lane2-docx：mode 收敛 14 宿主」只把各 A 宿主的 `mode` ref 收敛成
 * `'html' | 'docx'` 并接了 `el-segmented`，但**没有一个组件调用 `switchToOnlyOffice()`**。
 * 结果：各宿主都建了 `useWorkpaperSyncBridge`、挂了 `<WorkpaperSyncEditorHost
 * v-if="syncOoDescriptor">`，但 `bridge.descriptor` 恒 null（无人驱动 materialize）⇒
 * 用户切「在线编辑」后**永远停在「正在打开同步编辑器…」**。所有静态门全绿，只有运行时
 * 守卫 `sync/__tests__/bridgeMaterializeDriven.spec.ts` 能抓到这个空壳形态。
 *
 * 本 composable 把「健康 / 竞态 / 门禁 / descriptor / 四分支保存 / 失败可见」六件事收敛到
 * 单一正确实现，15 个 A 宿主各接几行即可（与 G 循环 `useGRenderModeSwitch`、H 循环
 * `useHSyncMode` 同机制）。
 *
 * ═══ 与 useHSyncMode 的差异（为什么不直接复用）═══════════════════════════════
 *
 * H/G 循环「一册多 sheet、部分受管」，需要 `hManagedSheetOf` / `isManagedSheet` /
 * `legacyMode` 三态分派 + `sheetKey` 派生 + mode 值 `'onlyoffice'`。A 循环**整册单一 OO
 * 文档**（docx/xlsx 权威册），整个 entry 要么结构化视图要么在线编辑，没有「部分 sheet
 * 走桥、部分走 legacy」的问题，mode 值是 `'docx'`。故本 driver 裁掉 sheet 分派，
 * **四分支保存 / 健康竞态兜底 / fail-visible 逐条照抄 useHSyncMode 的已验证实现**
 * （H 注释里写明的 D4 六类 bug 规避全部继承）。
 *
 * ═══ 四分支保存协议（OO → HTML，与 useHSyncMode 逐条同构）═══════════════════
 *
 * | 分支 | 条件 | 动作 | 用户感知 |
 * |---|---|---|---|
 * | ① | `state==='applied'`（改动已落库） | `reloadAfterApplied()` | **秒切** |
 * | ② | `!dirty`（未改动） | `leaveWithoutSaving()` | **丝滑**（不发强制保存） |
 * | ③ | dirty 且 `canForcesave` 且有 editorHostRef | `editorHost.forceSave()` | 慢但不丢改动 |
 * | ④ | dirty 但桥不放行 | `persistMode('html')` + **明示未同步**（sticky notice） | 放人走，不静默 |
 */
import { computed, ref, toRef, type Ref, type ComputedRef, type WritableComputedRef } from 'vue'
import {
  useWorkpaperSyncBridge,
  WP_BRIDGE_IN_FLIGHT_STATES,
  type WorkpaperSyncBridge,
  type WorkpaperSyncFlushResult,
} from './useWorkpaperSyncBridge'
import { capabilityForEntry } from './workpaperSyncCapability'
import { fetchOnlyOfficeHealthy } from './onlyOfficeHealth'

/** 双模式取值域 —— 与 A 各宿主既有 `el-segmented` 的 value 形态一致（不是 'onlyoffice'）。 */
export type ARenderMode = 'html' | 'docx'

/** 工具栏标签（各宿主一致，避免字面量漂移）。 */
export const A_HTML_MODE_LABEL = '结构化视图'
export const A_ONLINE_EDIT_LABEL = '在线编辑'

/** 宿主里 `WorkpaperSyncEditorHost` 的 ref 形态（只用到 forceSave）。 */
export interface ASyncEditorHostRef {
  forceSave: () => Promise<{ operationId: string }>
}

export interface UseARenderModeSwitchOptions {
  /** entry id（如 `xlsx/gt-a91-deficiency-letter`）。 */
  readonly entryId: string
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  /** 只读态（切在线编辑禁用）。 */
  readonly isReadonly: Ref<boolean>
  /** flush 钩子：只交回 projection 与 expected revision，不打端点（同 bridge 约定）。 */
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  /** 重载钩子：切回 HTML 后重载结构化数据（Property 14：须加载到不低于 minimumRevision）。 */
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
  /** 切 docx 前的可 await flush（宿主的 flushPendingSaves）。 */
  readonly flushBeforeSwitch?: () => void | Promise<void>
  /**
   * 切 docx 前的预处理（B 类 A177：先生成 Word）。返回 false ⇒ 中止切换（不进 OO）。
   * 预处理自身的 loading / 错误提示由宿主负责；driver 只据返回值决定是否继续。
   */
  readonly beforeEnterOo?: () => Promise<boolean>
  /** 切回 html 后的额外清理（A177 的 ooReady=false 等）。 */
  readonly afterLeaveOo?: () => void | Promise<void>
  /** HTML 侧标签（默认「结构化视图」）。 */
  readonly htmlLabel?: string
}

export interface UseARenderModeSwitch {
  /** 当前渲染模式。以**桥**为真源（本地 ref 会与桥漂移）。`v-model` 直接绑它。 */
  readonly renderMode: WritableComputedRef<ARenderMode>
  /** 切换器选项（不带 `disabled: !ooHealthy`；门禁在 switchMode 内 await 兜底）。 */
  readonly modeOptions: ComputedRef<{ label: string; value: ARenderMode; disabled: boolean }[]>
  /** `<WorkpaperSyncEditorHost>` 的 descriptor（模板 v-if / :descriptor）。 */
  readonly descriptor: ComputedRef<WorkpaperSyncBridge['descriptor']['value']>
  /** 宿主已建好的桥（模板 :bridge）。 */
  readonly syncBridge: WorkpaperSyncBridge
  /** 正在切换 / 在途（供 UI 加 loading、禁重复点击）。 */
  readonly busy: ComputedRef<boolean>
  /** 统一同步状态标签（工具栏用）。 */
  readonly syncStateTag: ComputedRef<{ text: string; type: 'info' | 'success' | 'warning' | 'danger' }>
  /** `<WorkpaperSyncEditorHost ref="…">` 的引用（四分支③要它的 forceSave）。 */
  readonly syncHostRef: Ref<ASyncEditorHostRef | null>
  /** 需要让用户看见的 sticky 提示（失败 / 未同步；切换成功时清空）。 */
  readonly lastNotice: Ref<{ text: string; type: 'warning' | 'danger' } | null>
  /** OO 健康（供宿主需要时读）。 */
  readonly ooHealthy: Ref<boolean>
  /** 显式切换入口（宿主也可直接绑 renderMode 的 setter）。 */
  readonly switchMode: (target: ARenderMode) => Promise<void>
}

export function useARenderModeSwitch(options: UseARenderModeSwitchOptions): UseARenderModeSwitch {
  const { entryId } = options
  const htmlLabel = options.htmlLabel ?? A_HTML_MODE_LABEL

  // ─── 健康（共享 TTL 缓存，切底稿不重打）───────────────────────────────────
  const ooHealthy = ref(false)
  const ooHealthChecking = ref(true)
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

  // ─── 桥 ───────────────────────────────────────────────────────────────────
  const syncSwitching = ref(false)
  const syncHostRef = ref<ASyncEditorHostRef | null>(null)
  /** 四分支里「放人走但未同步」等需要让用户看见的提示（sticky，切换成功时清空）。 */
  const lastNotice = ref<{ text: string; type: 'warning' | 'danger' } | null>(null)

  const syncBridge = useWorkpaperSyncBridge({
    entryId: ref(entryId),
    wpId: options.wpId,
    projectId: options.projectId,
    // A 循环整册单一 OO，sheetKey 用 entry 级稳定键（宿主不内联 SHEET_KEY_BY_CODE）。
    sheetKey: ref(`${entryId}:managed`),
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
  function isAppliedHtmlReturn(target: ARenderMode): boolean {
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
      value: 'html' as ARenderMode,
      disabled: busy.value && !isAppliedHtmlReturn('html'),
    },
    {
      label: A_ONLINE_EDIT_LABEL,
      value: 'docx' as ARenderMode,
      disabled: busy.value || options.isReadonly.value,
    },
  ])

  /**
   * 当前模式。以**桥**为唯一真源（本地 ref 会与桥漂移）。`v-model` 直接绑它，
   * setter 走 `switchMode`。
   */
  const renderMode = computed<ARenderMode>({
    get: () => (syncBridge.mode.value === 'oo' ? 'docx' : 'html'),
    set: (target: ARenderMode) => { void switchMode(target) },
  })

  async function switchMode(target: ARenderMode): Promise<void> {
    // applied→HTML 是完成重载的合法出口，不得被 busy 短路。
    if (busy.value && !isAppliedHtmlReturn(target)) return
    if (target === renderMode.value && !isAppliedHtmlReturn(target)) return

    if (target === 'docx') {
      if (options.isReadonly.value) return
      // 竞态兜底：点击可能早于 mount 期健康响应到达，此时 ooHealthy 仍为初始 false。
      // 健康未就绪则**当场 await 一次**（绕过 TTL 取最新）再判定，绝不因「还没探到」
      // 静默吞掉用户这次真实点击。
      if (!ooHealthy.value) await checkOoHealth(true)
      if (!ooHealthy.value) {
        lastNotice.value = { text: 'OnlyOffice 服务不可用，暂时只能用结构化视图', type: 'warning' }
        return
      }
      if (syncBridge.mode.value === 'oo') return
      syncSwitching.value = true
      lastNotice.value = null
      try {
        // B 类预处理（如先生成 Word）；返回 false ⇒ 中止，不进 OO。
        if (options.beforeEnterOo) {
          const ok = await options.beforeEnterOo()
          if (!ok) return
        }
        // 切 OO 前把 HTML 侧待写落库（桥内部还会再 flushHtml 一次；此处给可 await 门禁）。
        if (options.flushBeforeSwitch) await options.flushBeforeSwitch()
        await syncBridge.switchToOnlyOffice()
      } catch {
        // 桥失败时已把错误写进 `lastError`（sticky）。本函数是 computed setter 的落点，
        // 调用方拿不到这个 promise ⇒ 不吞就是 unhandled rejection（控制台报红 + 污染测试）。
        // 错误已可见，这里补一条人能看懂的提示，不抛第二遍。
        lastNotice.value = { text: '进入在线编辑失败，请重试', type: 'danger' }
      } finally {
        syncSwitching.value = false
      }
      return
    }

    // ─── target === 'html' ───────────────────────────────────────────────────
    if (syncBridge.mode.value !== 'oo') {
      syncBridge.persistMode('html')
      if (options.afterLeaveOo) await options.afterLeaveOo()
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
        // ④ 有改动但桥不放行强制保存 ⇒ 放人走避免「关在 OO 里没出口」，但**必须明说未同步**。
        syncBridge.persistMode('html')
        lastNotice.value = {
          text: '在线编辑侧改动未能同步回结构化视图，请重新进入在线编辑并保存',
          type: 'danger',
        }
      }
    } catch {
      // 错误已记入 `lastError`；这里补一条人能看懂的提示，不静默。
      lastNotice.value = { text: '保存回写失败，改动仍在在线编辑侧，请重试', type: 'danger' }
    } finally {
      syncSwitching.value = false
      if (options.afterLeaveOo) await options.afterLeaveOo()
    }
  }

  /** 统一同步状态标签（工具栏用）。`lastNotice` 优先 —— 失败必须盖过「已同步」。 */
  const syncStateTag = computed<{ text: string; type: 'info' | 'success' | 'warning' | 'danger' }>(() => {
    if (busy.value) return { text: '同步中…', type: 'info' }
    if (lastNotice.value) return { text: lastNotice.value.text, type: lastNotice.value.type }
    if (syncBridge.dirty?.value) {
      return syncBridge.mode.value === 'oo'
        ? { text: '在线编辑侧有未同步改动', type: 'warning' }
        : { text: '结构化视图有未同步改动', type: 'warning' }
    }
    if (String(syncBridge.state.value).includes('error') || syncBridge.lastError?.value) {
      return { text: '同步失败，请重试', type: 'danger' }
    }
    return {
      text: syncBridge.mode.value === 'oo' ? '在线编辑' : '已同步',
      type: 'success',
    }
  })

  return {
    renderMode,
    modeOptions,
    descriptor,
    syncBridge,
    busy,
    syncStateTag,
    syncHostRef,
    lastNotice,
    ooHealthy,
    switchMode,
  }
}

/** `toRef(props, 'x')` 便捷别名（组件传 props 字段时用）。 */
export { toRef }
