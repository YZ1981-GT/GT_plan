/**
 * useH7DualMode — H7 生产性生物资产 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 3.3
 * Requirements: 3.4
 *
 * - el-segmented 切换 HTML / OnlyOffice
 * - OO 健康检查（`health.data?.data?.healthy` 双层兼容）
 * - OO 不健康时降级为 HTML-only
 * - 切换前 autoSave
 * - localStorage 持久化 (per wpId)
 */
import { ref, onMounted, type Ref } from 'vue'

export type H7RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'h7-dual-mode:'

export interface UseH7DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  autoSave?: () => Promise<void>
  reloadAll?: () => Promise<void>
}

export function useH7DualMode(options: UseH7DualModeOptions) {
  const { wpId, autoSave, reloadAll } = options

  const currentMode = ref<H7RenderMode>('html')
  const isOoHealthy = ref(false)
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

  function persistMode(mode: H7RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  async function checkHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) { isOoHealthy.value = false; return false }
      const result = await response.json()
      const healthy = result.data?.data?.healthy ?? result.data?.healthy ?? result.healthy ?? false
      isOoHealthy.value = healthy
      return healthy
    } catch {
      isOoHealthy.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: H7RenderMode): Promise<void> {
    if (currentMode.value === target) return
    if (target === 'onlyoffice' && !isOoHealthy.value) return

    if (autoSave) await autoSave()
    currentMode.value = target
    persistMode(target)

    if (target === 'html' && reloadAll) await reloadAll()
  }

  onMounted(async () => {
    loadPersistedMode()
    await checkHealth()
    if (currentMode.value === 'onlyoffice' && !isOoHealthy.value) {
      currentMode.value = 'html'
      persistMode('html')
    }
  })

  return {
    currentMode,
    isOoHealthy,
    checking,
    modeOptions,
    switchMode,
    checkHealth,
  }
}

export default useH7DualMode
