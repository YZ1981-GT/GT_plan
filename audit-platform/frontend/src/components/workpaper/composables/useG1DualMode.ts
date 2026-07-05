/**
 * useG1DualMode — G1 交易性金融资产 HTML ↔ OnlyOffice 双模式切换（比照 useF5CosOfDualMode）
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 8.2 / Req 15.4
 * 模式状态(html/onlyoffice) + 健康检查 + 切换 + localStorage 持久化(per wpId)
 */
import { ref, onMounted, type Ref } from 'vue'

export type G1RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g1-dual-mode:'

export interface UseG1DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useG1DualMode(options: UseG1DualModeOptions) {
  const { wpId, reloadAll } = options

  const currentMode = ref<G1RenderMode>('html')
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
    } catch {
      /* ignore */
    }
  }

  function persistMode(mode: G1RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch {
      /* ignore */
    }
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
      // 健康端点双层信封兼容：result.data?.data?.healthy / result.data?.healthy / result.healthy
      const healthy = result.data?.data?.healthy ?? result.data?.healthy ?? result.healthy ?? false
      isOoAvailable.value = healthy
      return healthy
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: G1RenderMode): Promise<void> {
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
    void switchMode(val as G1RenderMode)
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

export default useG1DualMode
