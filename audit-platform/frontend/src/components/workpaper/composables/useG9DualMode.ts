/**
 * useG9DualMode — G9 HTML ↔ OnlyOffice 双模式
 */
import { ref, onMounted, type Ref } from 'vue'

export type G9RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g9-dual-mode:'

export function useG9DualMode(options: {
  wpId: Ref<string>
  reloadAll?: () => Promise<void>
}) {
  const currentMode = ref<G9RenderMode>('html')
  const isOoAvailable = ref(false)

  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + options.wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  async function checkOOHealth(): Promise<boolean> {
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
    }
  }

  async function onModeChange(val: string | number | boolean): Promise<void> {
    const target = val as G9RenderMode
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return
    currentMode.value = target
    try {
      localStorage.setItem(STORAGE_PREFIX + options.wpId.value, target)
    } catch { /* ignore */ }
    if (target === 'html' && options.reloadAll) await options.reloadAll()
  }

  onMounted(() => {
    loadPersistedMode()
    void checkOOHealth()
  })

  return { currentMode, isOoAvailable, modeOptions, onModeChange, checkOOHealth }
}

export { useG9DualMode as useG9OthNonDualMode }
