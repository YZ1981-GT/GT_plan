/**
 * useH5DualMode — H5 油气资产 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/ Task 3.3
 * Requirements: 3.3, 7.2-7.3
 *
 * - el-segmented 切换 HTML / OnlyOffice
 * - OO 健康检查（`health.data?.data?.healthy` 双层兼容）
 * - OO 不健康时降级为 HTML-only
 * - 切换前 autoSave
 * - localStorage 持久化 (per wpId)
 * - ~80 行，follow useH1DualMode pattern
 */
import { ref, onMounted, type Ref } from 'vue'

export type H5RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'h5-dual-mode:'

export interface UseH5DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useH5DualMode(options: UseH5DualModeOptions) {
  const { wpId, autoSave, reloadAll } = options

  const currentMode = ref<H5RenderMode>('html')
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

  function persistMode(mode: H5RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  /** OO 健康检查 — 双层兼容 health.data?.data?.healthy */
  async function checkHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) {
        isOoHealthy.value = false
        return false
      }
      const result = await response.json()
      // 双层兼容: result.data?.data?.healthy 或 result.data?.healthy 或 result.healthy
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

  /**
   * 切换模式
   * - 若目标为 onlyoffice 且 OO 不健康，拒绝切换
   * - 切换前自动保存
   * - 从 OO 切回 HTML 时重新加载数据
   */
  async function switchMode(target: H5RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoHealthy.value) return

    // autoSave before switching
    if (autoSave) {
      try { await autoSave() } catch { /* best effort */ }
    }

    if (target === 'onlyoffice') {
      currentMode.value = 'onlyoffice'
      persistMode('onlyoffice')
    } else {
      currentMode.value = 'html'
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  /** el-segmented change handler */
  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as H5RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void checkHealth()
  })

  return {
    currentMode,
    isOoHealthy,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkHealth,
  }
}

export default useH5DualMode
