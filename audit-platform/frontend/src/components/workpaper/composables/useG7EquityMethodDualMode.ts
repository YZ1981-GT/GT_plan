/**
 * useG7EquityMethodDualMode — G7 权益法组 HTML ↔ OnlyOffice 双模式
 * 比照 useF2DualMode / useG7DualMode
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'
import { dualModeHtmlOoOptions } from './dualModeLabels'

export type G7EquityMethodRenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g7-equity-method-mode-'

export interface UseG7EquityMethodDualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useG7EquityMethodDualMode(options: UseG7EquityMethodDualModeOptions) {
  const { wpId, sheetName, reloadAll } = options

  const currentMode = ref<G7EquityMethodRenderMode>('html')
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

  function persistMode(mode: G7EquityMethodRenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      const result = res.data?.data ?? res.data ?? {}
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

  async function switchMode(target: G7EquityMethodRenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) {
      currentMode.value = 'html'
      return
    }

    if (target === 'onlyoffice') {
      const sn = sheetName?.value || 'G7'
      try {
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { _silent: true } as any,
        )
        const result = res.data?.data ?? res.data ?? {}
        ooConfig.value = result.data || result
        currentMode.value = 'onlyoffice'
        persistMode('onlyoffice')
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
    void switchMode(val as G7EquityMethodRenderMode)
  }

  const isHtml = () => currentMode.value === 'html'
  const isOO = () => currentMode.value === 'onlyoffice'

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
    mode: currentMode,
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    toggleMode: switchMode,
    isHtml,
    isOO,
    checkOOHealth,
  }
}

export default useG7EquityMethodDualMode
