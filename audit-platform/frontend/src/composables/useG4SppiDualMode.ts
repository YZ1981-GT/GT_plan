/**
 * useG4SppiDualMode — G4 债权投资(SPPI组) HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 1.4 / Req 8.6
 * 模式状态(html/onlyoffice) + 健康检查 + 切换 + localStorage 持久化(per wpId)
 */
import { ref, onMounted, type Ref } from 'vue'

export type G4SppiRenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g4-sppi-dual-mode:'

export interface UseG4SppiDualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useG4SppiDualMode(options: UseG4SppiDualModeOptions) {
  const { wpId, reloadAll } = options

  const currentMode = ref<G4SppiRenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

  const modeOptions = [
    { label: 'HTML', value: 'html' },
    { label: 'OnlyOffice', value: 'onlyoffice' },
  ]

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: G4SppiRenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
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

  async function switchMode(target: G4SppiRenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice') {
      currentMode.value = 'onlyoffice'
      persistMode('onlyoffice')
    } else {
      currentMode.value = 'html'
      ooConfig.value = null
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as G4SppiRenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void checkOOHealth()
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOOHealth,
  }
}

export default useG4SppiDualMode
