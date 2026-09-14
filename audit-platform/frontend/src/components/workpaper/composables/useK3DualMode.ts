/**
 * useK3DualMode — K3 其他应付款 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/k3-other-payables/ Task 3.3
 * Requirements: 3.4
 *
 * - el-segmented 切换 结构化视图(html) / 在线编辑(onlyoffice)
 * - OO 健康检查（`/workpapers/onlyoffice/health` 双层兼容）
 * - 切换前 autoSave
 * - localStorage 持久化 (per wpId)
 * - follow useK2DualMode pattern
 */
import { ref, onMounted, type Ref } from 'vue'

export type K3RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'k3-dual-mode:'

export interface UseK3DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useK3DualMode(options: UseK3DualModeOptions) {
  const { wpId, autoSave, reloadAll } = options

  const currentMode = ref<K3RenderMode>('html')
  const isOoAvailable = ref(false)
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

  function persistMode(mode: K3RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  /** OO 健康检查 — GET /workpapers/onlyoffice/health {_silent:true} 双层兼容 */
  async function checkOoHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) {
        isOoAvailable.value = false
        return false
      }
      const result = await response.json()
      // 双层兼容: result.data?.data?.healthy 或 result.data?.healthy 或 result.healthy
      const healthy = result.data?.data?.healthy ?? result.data?.healthy ?? result.healthy ?? false
      isOoAvailable.value = healthy
      return healthy
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: K3RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

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

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as K3RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void checkOoHealth()
  })

  return {
    currentMode,
    isOoAvailable,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
  }
}

export default useK3DualMode
