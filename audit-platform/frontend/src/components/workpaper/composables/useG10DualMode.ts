/**
 * useG10DualMode — G10 HTML ↔ OnlyOffice 双模式
 * 对齐 G8：健康检查 + reloadAll + 不可用时强制 HTML
 */
import { ref, onMounted, type Ref } from 'vue'
import { dualModeHtmlOoOptions } from './dualModeLabels'

export type G10RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g10-dual-mode:'

export function useG10DualMode(options: {
  wpId: Ref<string>
  reloadAll?: () => Promise<void>
}) {
  const currentMode = ref<G10RenderMode>('html')
  const isOoAvailable = ref(false)
  const checking = ref(false)

  const modeOptions = dualModeHtmlOoOptions()

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + options.wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: G10RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + options.wpId.value, mode)
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

  async function switchMode(target: G10RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return
    currentMode.value = target
    persistMode(target)
    if (target === 'html' && options.reloadAll) await options.reloadAll()
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as G10RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void checkOOHealth().then((healthy) => {
      if (!healthy && currentMode.value === 'onlyoffice') {
        currentMode.value = 'html'
        persistMode('html')
      }
    })
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

export { useG10DualMode as useG10TraFinDualMode }
export default useG10DualMode
