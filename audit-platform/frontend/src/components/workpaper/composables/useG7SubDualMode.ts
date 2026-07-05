/**
 * useG7SubDualMode — G7 长期股权投资(子公司组) HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/ Task 1.12 / Req 7.6
 * 模式状态(html/onlyoffice) + 健康检查 + 切换 + localStorage 持久化(per wpId)
 */
import { ref, onMounted, type Ref } from 'vue'

export type G7SubRenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g7-sub-mode-'

export interface UseG7SubDualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useG7SubDualMode(options: UseG7SubDualModeOptions) {
  const { wpId, reloadAll } = options

  const currentMode = ref<G7SubRenderMode>('html')
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

  function persistMode(mode: G7SubRenderMode): void {
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

  async function switchMode(target: G7SubRenderMode): Promise<void> {
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
    void switchMode(val as G7SubRenderMode)
  }

  // Convenience computed-like getters
  const isHtml = () => currentMode.value === 'html'
  const isOO = () => currentMode.value === 'onlyoffice'

  onMounted(() => {
    loadPersistedMode()
    void checkOOHealth()
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

export default useG7SubDualMode
