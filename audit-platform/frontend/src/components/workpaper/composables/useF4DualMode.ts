/**
 * useF4DualMode — F4 HTML ↔ OnlyOffice 双模式（比照 useF3DualMode）
 *
 * localStorage 持久化 key: 'f4-ap-mode:{wpId}'
 * Spec: .kiro/specs/f4-accounts-payable/ Task 8.2
 */
import { ref, onMounted, type Ref } from 'vue'

export type F4RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'f4-ap-mode:'

export interface UseF4DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useF4DualMode(options: UseF4DualModeOptions) {
  const { wpId, sheetName, reloadAll } = options

  const currentMode = ref<F4RenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: F4RenderMode): void {
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

  async function switchMode(target: F4RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice') {
      const sn = sheetName?.value || 'F4'
      try {
        const response = await fetch(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
        )
        if (response.ok) {
          const result = await response.json()
          ooConfig.value = result.data || result
          currentMode.value = 'onlyoffice'
          persistMode('onlyoffice')
        }
      } catch {
        isOoAvailable.value = false
      }
    } else {
      currentMode.value = 'html'
      ooConfig.value = null
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as F4RenderMode)
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

export default useF4DualMode
