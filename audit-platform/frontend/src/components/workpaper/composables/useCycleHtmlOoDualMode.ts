/**
 * 循环底稿 HTML ↔ OnlyOffice 双模式（结构化视图 / 在线编辑）
 * 供 *A 程序表主入口与独立 a-program-console 路由复用。
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import { dualModeHtmlOoOptions } from './dualModeLabels'

export type CycleHtmlOoMode = 'html' | 'onlyoffice'

export interface UseCycleHtmlOoDualModeOptions {
  wpId: Ref<string>
  /** localStorage 前缀，建议含科目编码避免冲突 */
  storagePrefix: string
  reloadAll?: () => Promise<void>
  /**
   * 同步能力单源（`useEntrySyncReadiness()` 的返回值）。
   *
   * spec workpaper-html-onlyoffice-bidirectional-writeback-closure（AC 1.4 / task 3.5）：
   * 「能不能双向」是 entry 级事实（静态裁决 + 运行时 readiness + 真实验收三层），不是宿主
   * 或本 composable 的局部判断。传了它，`showModeSwitch` 就由单源决定；不传则恒 `true`
   * （保持改线前行为，供尚未接单源的宿主渐进迁移）。
   *
   * 🔴 只收「表现」，不收能力判断：本 composable 的 `isOoAvailable`（legacy
   * `/api/workpapers/onlyoffice/health` 探活）回答的是「OO 服务在不在」，与「这条 entry 两侧
   * 是否真的互通」是两件事，不能互相顶替 —— 后者才是 `showModeSwitch` 的依据。
   */
  entrySync?: {
    readonly presentation: { readonly value: { readonly showModeSwitch: boolean } }
  }
}

export function useCycleHtmlOoDualMode(options: UseCycleHtmlOoDualModeOptions) {
  const { wpId, storagePrefix, reloadAll, entrySync } = options

  const currentMode = ref<CycleHtmlOoMode>('html')
  const isOoAvailable = ref(false)
  const checking = ref(false)

  const modeOptions = computed(() =>
    dualModeHtmlOoOptions({ onlineDisabled: !isOoAvailable.value }),
  )

  /**
   * 模式开关该不该出现 —— 来自同步能力**单源**（传了 `entrySync` 才生效）。
   *
   * 宿主把它绑到模式开关的 `v-if` 上。没传 `entrySync` 时恒 `true`，等价于改线前行为。
   * 🔴 这里**不**掺入 `isOoAvailable`：那是「OO 侧能否拉起」，属 `modeOptions` 的
   * `onlineDisabled`（可用性），与「该不该露出开关」（可见性）是两层，混在一起就会出现
   * 「仅能打开 OO 却呈现成双向」或「真能双向却被服务探活抖动藏掉」。
   */
  const showModeSwitch = computed(() => {
    if (!entrySync) return true
    return entrySync.presentation.value.showModeSwitch
  })

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(storagePrefix + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: CycleHtmlOoMode): void {
    try {
      localStorage.setItem(storagePrefix + wpId.value, mode)
    } catch { /* ignore */ }
  }

  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) {
        isOoAvailable.value = false
        return false
      }
      const result = await response.json()
      const healthy = result.data?.healthy ?? result.healthy ?? false
      isOoAvailable.value = healthy
      return healthy
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: CycleHtmlOoMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice') {
      currentMode.value = 'onlyoffice'
      persistMode('onlyoffice')
    } else {
      currentMode.value = 'html'
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as CycleHtmlOoMode)
  }

  onMounted(async () => {
    await checkOOHealth()
    loadPersistedMode()
    if (currentMode.value === 'onlyoffice' && !isOoAvailable.value) {
      currentMode.value = 'html'
    }
  })

  return {
    currentMode,
    isOoAvailable,
    checking,
    modeOptions,
    showModeSwitch,
    switchMode,
    onModeChange,
    checkOOHealth,
  }
}

export default useCycleHtmlOoDualMode
