/**
 * useG14DualMode — G14 HTML ↔ OnlyOffice 双模式
 * Spec: .kiro/specs/g14-credit-impairment-loss/ Task 4.2
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import { dualModeHtmlOoOptions } from './dualModeLabels'

export type G14RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g14-dual-mode:'

export function useG14DualMode(options: {
  wpId: Ref<string>
  reloadAll?: () => Promise<void>
}) {
  const currentMode = ref<G14RenderMode>('html')
  const isOoAvailable = ref(false)

  const modeOptions = computed(() => dualModeHtmlOoOptions({ onlineDisabled: !isOoAvailable.value }))

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
    const target = val as G14RenderMode
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) {
      currentMode.value = 'html'
      return
    }
    currentMode.value = target
    try {
      localStorage.setItem(STORAGE_PREFIX + options.wpId.value, target)
    } catch { /* ignore */ }
    if (target === 'html' && options.reloadAll) await options.reloadAll()
  }

  onMounted(() => {
    void checkOOHealth().then((healthy) => {
      if (healthy) {
        loadPersistedMode()
      } else {
        currentMode.value = 'html'
        try {
          localStorage.setItem(STORAGE_PREFIX + options.wpId.value, 'html')
        } catch { /* ignore */ }
      }
    })
  })

  return { currentMode, isOoAvailable, modeOptions, onModeChange, checkOOHealth }
}
