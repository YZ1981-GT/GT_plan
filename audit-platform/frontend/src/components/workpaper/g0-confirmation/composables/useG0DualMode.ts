/**
 * useG0DualMode — G0 投资循环函证 HTML ↔ OnlyOffice 双模式
 *
 * 模式状态(html/onlyoffice) + 切换逻辑 + localStorage 持久化（比照 useF2DualMode）。
 * G0-3S(证券差异)/G0-6(替代程序) 专属组件默认 HTML；OnlyOffice 作为降级/偏好切换。
 * OO 健康检查响应双层兼容：health.data?.data?.healthy。
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

export type G0RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g0-dual-mode:'

export interface UseG0DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useG0DualMode(options: UseG0DualModeOptions) {
  const { wpId, sheetName, reloadAll } = options

  const currentMode = ref<G0RenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  function storageKey(): string {
    return STORAGE_PREFIX + wpId.value
  }

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(storageKey())
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch {
      /* ignore */
    }
  }

  function persistMode(mode: G0RenderMode): void {
    try {
      localStorage.setItem(storageKey(), mode)
    } catch {
      /* ignore */
    }
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

  async function switchMode(target: G0RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice') {
      const sn = sheetName?.value || 'G0'
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
    void switchMode(val as G0RenderMode)
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
    loadPersistedMode,
    persistMode,
  }
}

export default useG0DualMode
