/**
 * useI2DualMode — I2 开发支出 HTML ↔ OnlyOffice 双模式切换
 *
 * el-segmented 切换 HTML / OnlyOffice
 * - OO 健康检查（`health.data?.data?.healthy` 双层兼容）
 * - 切换前 autoSave
 * - localStorage 持久化 (per wpId)
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.7
 * Requirements: 专属组件复盘3查 — 主入口HTML sheet顶部必须放el-segmented(HTML/OO)+useXDualMode
 */
import { ref, onMounted, type Ref } from 'vue'

export type I2RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'i2-dual-mode:'

export interface UseI2DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useI2DualMode(options: UseI2DualModeOptions) {
  const { wpId, autoSave, reloadAll } = options

  const mode = ref<I2RenderMode>('html')
  const isOoHealthy = ref(false)
  const checking = ref(false)

  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') mode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(m: I2RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, m)
    } catch { /* ignore */ }
  }

  /** OO 健康检查 — 双层兼容 health.data?.data?.healthy */
  async function checkOoHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) {
        isOoHealthy.value = false
        return false
      }
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

  async function switchMode(target: I2RenderMode): Promise<void> {
    if (target === mode.value) return
    if (target === 'onlyoffice' && !isOoHealthy.value) return

    // autoSave before switching
    if (autoSave) {
      try { await autoSave() } catch { /* best effort */ }
    }

    if (target === 'onlyoffice') {
      mode.value = 'onlyoffice'
      persistMode('onlyoffice')
    } else {
      mode.value = 'html'
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as I2RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void checkOoHealth()
  })

  return {
    mode,
    isOoHealthy,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
  }
}

export default useI2DualMode
