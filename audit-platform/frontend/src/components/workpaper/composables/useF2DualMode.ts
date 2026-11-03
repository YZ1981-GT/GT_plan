/**
 * useF2DualMode — F2 HTML ↔ OnlyOffice 双模式（比照 useD4DualMode / useF3DualMode）
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'
import { runLegacyOnlyOfficeTransition } from '../sync/legacyPendingWriteBarrier'

export type F2RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'f2-dual-mode:'

export interface UseF2DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useF2DualMode(options: UseF2DualModeOptions) {
  const { wpId, sheetName, reloadAll } = options

  const currentMode = ref<F2RenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  function loadPersistedMode(): F2RenderMode | null {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') return saved
    } catch { /* ignore */ }
    return null
  }

  function persistMode(mode: F2RenderMode): void {
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

  async function switchMode(target: F2RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice') {
      await runLegacyOnlyOfficeTransition(async () => {
        const sn = sheetName?.value || 'F2'
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
      })
    } else {
      currentMode.value = 'html'
      ooConfig.value = null
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as F2RenderMode)
  }

  onMounted(() => {
    const saved = loadPersistedMode()
    // OO 健康检查不阻塞首屏；恢复偏好也必须走完整保存屏障，不能先挂 OO。
    void (async () => {
      if (saved === 'onlyoffice') {
        const healthy = await checkOOHealth()
        if (healthy) {
          await switchMode('onlyoffice')
        } else {
          currentMode.value = 'html'
          persistMode('html')
        }
      } else {
        // 结构化视图：后台轻量探测，失败不影响渲染
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

export default useF2DualMode
