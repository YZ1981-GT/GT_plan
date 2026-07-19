/**
 * useG6EclDualMode — G6 其他债权投资(ECL组) HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 4.2 / Req 6.6
 * 模式状态(html/onlyoffice) + 健康检查 + 切换 + localStorage 持久化(per wpId)
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import { dualModeHtmlOoOptions } from './dualModeLabels'

export type G6EclRenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g6-ecl-dual-mode:'

export interface UseG6EclDualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useG6EclDualMode(options: UseG6EclDualModeOptions) {
  const { wpId, reloadAll } = options

  const currentMode = ref<G6EclRenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

  const modeOptions = computed(() => dualModeHtmlOoOptions({ onlineDisabled: !isOoAvailable.value }))

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: G6EclRenderMode): void {
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

  async function switchMode(target: G6EclRenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) {
      currentMode.value = 'html'
      return
    }

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
    void switchMode(val as G6EclRenderMode)
  }

  onMounted(() => {
    void checkOOHealth().then((healthy) => {
      if (healthy) {
        loadPersistedMode()
      } else {
        currentMode.value = 'html'
        persistMode('html')
      }
    })
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

export default useG6EclDualMode
