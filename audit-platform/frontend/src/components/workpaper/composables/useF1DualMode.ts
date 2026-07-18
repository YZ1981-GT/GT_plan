/**
 * useF1DualMode — F1 预付账款 HTML ↔ OnlyOffice 双模式（对齐 useF3DualMode）
 * 外层 GtWpRenderer 通过 sheetName 切换 sheet，不再依赖内层 el-tabs。
 */
import { ref, onMounted, type Ref } from 'vue'

export type F1RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'f1-dual-mode:'

export interface UseF1DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useF1DualMode(options: UseF1DualModeOptions) {
  const { wpId, reloadAll } = options

  const currentMode = ref<F1RenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

  /** 兼容旧 UI 文案：结构化视图 / 在线编辑 */
  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  /** @deprecated 兼容旧调用方 */
  const ooHealthy = isOoAvailable

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
      // 旧值 structured → html
      if (saved === 'structured') currentMode.value = 'html'
    } catch { /* ignore */ }
  }

  function persistMode(mode: F1RenderMode): void {
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

  async function switchMode(target: F1RenderMode): Promise<void> {
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
    const mode = String(val) === 'onlyoffice' ? 'onlyoffice' : 'html'
    void switchMode(mode)
  }

  onMounted(() => {
    loadPersistedMode()
    void checkOOHealth()
  })

  return {
    currentMode,
    modeOptions,
    isOoAvailable,
    ooHealthy,
    ooConfig,
    checking,
    checkOOHealth,
    switchMode,
    onModeChange,
  }
}

export default useF1DualMode
