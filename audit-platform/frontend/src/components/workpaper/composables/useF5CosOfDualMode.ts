/**
 * useF5CosOfDualMode — F5 营业成本 HTML ↔ OnlyOffice 双模式切换（比照 useF3DualMode）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 8.2 / Req 13.4
 * 模式状态(html/onlyoffice) + 健康检查 + 切换 + localStorage 持久化(per wpId)
 */
import { ref, onMounted, type Ref } from 'vue'

export type F5RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'f5-dual-mode:'

export interface UseF5DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useF5CosOfDualMode(options: UseF5DualModeOptions) {
  const { wpId, sheetName, reloadAll } = options

  const currentMode = ref<F5RenderMode>('html')
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

  function persistMode(mode: F5RenderMode): void {
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

  async function switchMode(target: F5RenderMode): Promise<void> {
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
    void switchMode(val as F5RenderMode)
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

export default useF5CosOfDualMode
