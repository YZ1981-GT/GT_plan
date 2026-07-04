/** 比照 useF2DualMode */
import { ref, onMounted, type Ref } from 'vue'

export type F2ValRenderMode = 'html' | 'onlyoffice'
const STORAGE_PREFIX = 'f2-val-dual-mode:'

export function useF2ValuationDualMode(options: {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}) {
  const { wpId, sheetName, reloadAll } = options
  const currentMode = ref<F2ValRenderMode>('html')
  const isOoAvailable = ref(false)
  const modeOptions = [
    { label: 'HTML', value: 'html' },
    { label: 'OnlyOffice', value: 'onlyoffice' },
  ]

  async function checkOOHealth(): Promise<boolean> {
    try {
      const res = await fetch('/api/workpapers/onlyoffice/health')
      if (!res.ok) { isOoAvailable.value = false; return false }
      const j = await res.json()
      isOoAvailable.value = j.data?.healthy ?? j.healthy ?? false
      return isOoAvailable.value
    } catch {
      isOoAvailable.value = false
      return false
    }
  }

  async function switchMode(target: F2ValRenderMode): Promise<void> {
    if (target === 'onlyoffice' && !isOoAvailable.value) return
    currentMode.value = target
    try { localStorage.setItem(STORAGE_PREFIX + wpId.value, target) } catch { /* ignore */ }
    if (target === 'html' && reloadAll) await reloadAll()
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as F2ValRenderMode)
  }

  onMounted(() => {
    try {
      const s = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (s === 'html' || s === 'onlyoffice') currentMode.value = s
    } catch { /* ignore */ }
    void checkOOHealth()
  })

  return { currentMode, isOoAvailable, modeOptions, onModeChange, checkOOHealth }
}

export default useF2ValuationDualMode
