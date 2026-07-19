/**
 * useG12DualMode — G12 HTML ↔ OnlyOffice 双模式
 * 比照 useF2DualMode / useG11DualMode：http 健康检查 + onlyoffice-config + reloadAll
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'
import { dualModeHtmlOoOptions } from './dualModeLabels'

export type G12RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g12-dual-mode:'

export function useG12DualMode(options: {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}) {
  const { wpId, sheetName, reloadAll } = options

  const currentMode = ref<G12RenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

  const modeOptions = dualModeHtmlOoOptions()

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: G12RenderMode): void {
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

  async function switchMode(target: G12RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice') {
      const sn = sheetName?.value || 'G12'
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
    void switchMode(val as G12RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void (async () => {
      let saved: string | null = null
      try {
        saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      } catch { /* ignore */ }

      if (saved === 'onlyoffice') {
        const healthy = await checkOOHealth()
        if (healthy) {
          await switchMode('onlyoffice')
        } else {
          currentMode.value = 'html'
          persistMode('html')
        }
      } else {
        void checkOOHealth()
      }
    })()
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

export { useG12DualMode as useG12NetHedDualMode }
export default useG12DualMode
