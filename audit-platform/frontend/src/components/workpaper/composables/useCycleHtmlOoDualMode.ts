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
}

export function useCycleHtmlOoDualMode(options: UseCycleHtmlOoDualModeOptions) {
  const { wpId, storagePrefix, reloadAll } = options

  const currentMode = ref<CycleHtmlOoMode>('html')
  const isOoAvailable = ref(false)
  const checking = ref(false)

  const modeOptions = computed(() =>
    dualModeHtmlOoOptions({ onlineDisabled: !isOoAvailable.value }),
  )

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
    switchMode,
    onModeChange,
    checkOOHealth,
  }
}

export default useCycleHtmlOoDualMode
