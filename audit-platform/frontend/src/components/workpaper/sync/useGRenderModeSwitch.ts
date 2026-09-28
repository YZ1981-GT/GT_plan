/**
 * G 循环双模式切换器 —— 把「受管 sheet 必须经桥」这件事收在一处。
 *
 * ═══ 为什么必须有这一层 ═══════════════════════════════════════════════════
 *
 * G 循环 13 个宿主（G4×3 / G5 / G6×2 / G8 / G9 / G10 / G11 / G12 / G13 / G14）都已经
 * **建好了** `useWorkpaperSyncBridge`、声明了 `syncOoDescriptor` / `syncBusy` /
 * `syncSwitching`、模板里也挂了 `<WorkpaperSyncEditorHost>` —— 但**没有一个调过**
 * `bridge.switchToOnlyOffice()`。它们的 `isOoMode` 读的是 legacy `useG*DualMode` 那个
 * 本地 ref：
 *
 *     const isOoMode = computed(() => … && dualMode.currentMode.value === 'onlyoffice')
 *
 * 于是桥的 `mode` 永远停在 `html_idle`，`descriptor` 恒 `null`，而
 * `WorkpaperSyncEditorHost` 只在 `descriptor !== null && bridge.mode === 'oo'` 时才创建
 * DocEditor（它刻意不自己请求 config）⇒ 用户点「在线编辑」后永远停在
 * 「正在打开同步编辑器…」那行字上，**而所有静态门都是绿的**：import 齐、组件挂了、
 * 桥建了、契约有、类型过。这就是 `sync/__tests__/bridgeMaterializeDriven.spec.ts`
 * 钉住的「空壳」形态。
 *
 * 13 份同构缺陷 ⇒ 修法也必须只有一份。每个宿主接 3 行，而不是各自抄一遍四分支
 * （抄 13 遍的下场看 F 循环：4 条 lane 各内联一张 `F*_SHEET_KEY_BY_CODE`，注释都写着
 * 「从 provider 派生」而实现是硬编码，没有任何判据能报红）。
 *
 * ═══ 受管 / 非受管的分派不得合并 ═══════════════════════════════════════════
 *
 * 受管 sheet 走桥（真双向），非受管 sheet 保留 legacy `GtOnlyOfficeSheet`（假双向，
 * 已如实登记）。两条路**不能并进同一个布尔** —— D4-35 / D4-13 踩过「切错桥 + 工具条
 * 叠加」。故 `renderMode` 按当前 sheet 是否受管**分别取源**，与 G7 宿主同构。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { dualModeHtmlOoOptions, type DualModeSegmentedOption } from '../composables/dualModeLabels'
import type { WorkpaperSyncBridge } from './useWorkpaperSyncBridge'

export type GRenderMode = 'html' | 'onlyoffice'

/** `WorkpaperSyncEditorHost` 暴露的 `forceSave`（宿主 ref 的最小形状）。 */
export interface GSyncEditorHostHandle {
  forceSave: () => Promise<{ operationId: string }>
}

/** legacy `useG*DualMode` 里本切换器真正用到的部分（宽松取子集，各宿主签名略有差异）。 */
export interface GLegacyDualMode {
  currentMode: Ref<GRenderMode> | { value: GRenderMode }
  onModeChange: (val: string | number | boolean) => void | Promise<void>
}

export interface GRenderModeSwitchOptions {
  /** 宿主已建好的桥。 */
  readonly bridge: WorkpaperSyncBridge
  /** legacy 双模式（非受管 sheet 仍走它）。 */
  readonly legacy: GLegacyDualMode
  /** 当前 sheet 是否走桥（受管 **且** 已接 OO 直写宿主）。 */
  readonly isManagedSheet: Ref<boolean> | ComputedRef<boolean>
  /** 模板里 `<WorkpaperSyncEditorHost ref="…">` 的引用（④分支要它的 forceSave）。 */
  readonly editorHostRef: Ref<GSyncEditorHostHandle | null>
  /**
   * 切到 OO 之前把 HTML 侧待写落库。
   *
   * 🔴 桥的 `flushHtml` 回调本身会做一次，但 G 循环各宿主的 `flushHtml` 写的是
   * `formData.flushPending()`（**同步、不 await**）后紧接 `readStoreProjection` ——
   * 若宿主的落库是异步的，必须在这里额外给一个可 await 的门禁，否则 materialize 出的
   * xlsx 会少掉最后那批编辑且无任何提示。宿主的 flush 已经是同步的就不用传。
   */
  readonly flushBeforeSwitch?: () => void | Promise<void>
}

export interface GRenderModeSwitch {
  /** 当前渲染模式：受管 sheet 以**桥**为真源，非受管 sheet 读 legacy。 */
  readonly renderMode: ComputedRef<GRenderMode>
  /**
   * 切换器选项。
   *
   * 🔴 **不带 `disabled`**：legacy 的 `modeOptions` 会在 `isOoAvailable=false` 时把
   * 「在线编辑」置灰，而那个标志来自 legacy 自己 fetch 的 `/onlyoffice/health`
   * （与桥并行的第二条路径，异步且先于用户点击）。disabled 在未就绪时会把入口锁死、
   * 点击被彻底吞掉 —— D4 已实证的 bug ③。门禁改在 `switchRenderMode` 里 await 兜底。
   */
  readonly modeOptions: readonly DualModeSegmentedOption[]
  /** 正在切换（供宿主给切换器加 loading / 禁重复点击）。 */
  readonly switching: Ref<boolean>
  /** 切换入口 —— 直接接 `el-segmented` 的 `@change`。 */
  readonly switchRenderMode: (target: string | number | boolean) => Promise<void>
}

/**
 * 建立「受管走桥、非受管走 legacy」的双模式切换。
 *
 * 四分支保存协议（与 D3 / F3 / G2 / G7 / B60 逐条同构）：
 *
 * | 分支 | 条件 | 动作 | 用户感知 |
 * |---|---|---|---|
 * | ① | 切到 OO | `switchToOnlyOffice()`（内部先 flushHtml → pending → materialize） | 有等待 |
 * | ② | 回 HTML 且 `state==='applied'` | `reloadAfterApplied()` | **秒切**（改动已落库） |
 * | ③ | 回 HTML 且 `!dirty` | `leaveWithoutSaving()` | **丝滑**（不发强制保存） |
 * | ④ | 回 HTML 且 dirty | `editorHost.forceSave()` | 慢（用户没先保存，允许） |
 */
export function useGRenderModeSwitch(options: GRenderModeSwitchOptions): GRenderModeSwitch {
  const { bridge, legacy, isManagedSheet, editorHostRef, flushBeforeSwitch } = options
  const switching = ref(false)

  const renderMode = computed<GRenderMode>(() =>
    isManagedSheet.value
      ? bridge.mode.value === 'oo'
        ? 'onlyoffice'
        : 'html'
      : legacy.currentMode.value,
  )

  const modeOptions = Object.freeze(dualModeHtmlOoOptions())

  async function switchRenderMode(rawTarget: string | number | boolean): Promise<void> {
    const target = rawTarget as GRenderMode
    if (target !== 'html' && target !== 'onlyoffice') return
    if (switching.value) return

    // 非受管 sheet：保留 legacy 行为（legacy 自己判重、自己写 localStorage）。
    if (!isManagedSheet.value) {
      await legacy.onModeChange(target)
      return
    }
    if (target === renderMode.value) return

    switching.value = true
    try {
      if (target === 'onlyoffice') {
        // ① 可 await 的 flush 门禁（宿主按需提供）→ 桥内部再走一次 flushHtml
        if (flushBeforeSwitch) await flushBeforeSwitch()
        await bridge.switchToOnlyOffice()
        return
      }
      if (bridge.mode.value !== 'oo') return
      if (String(bridge.state.value) === 'applied') {
        await bridge.reloadAfterApplied() // ② 秒切
      } else if (!bridge.dirty.value) {
        await bridge.leaveWithoutSaving() // ③ 丝滑
      } else if (bridge.canForcesave.value && editorHostRef.value) {
        await editorHostRef.value.forceSave() // ④ 慢，但不丢改动
      } else {
        await bridge.switchToHtml()
      }
    } catch {
      // 失败保持当前视图；错误已由桥写入 lastError / feedback（fail visible）
    } finally {
      switching.value = false
    }
  }

  return { renderMode, modeOptions, switching, switchRenderMode }
}
