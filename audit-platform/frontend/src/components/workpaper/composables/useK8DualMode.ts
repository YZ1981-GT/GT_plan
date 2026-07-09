/**
 * useK8DualMode — K8 销售费用 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/k8-selling-expenses/
 * Task: 3.3
 * Requirements: 3.3
 *
 * - el-segmented 切换 结构化视图(html) / 在线编辑(onlyoffice)
 * - OO 健康检查（`/workpapers/onlyoffice/health` 双层兼容）
 * - 切换前 autoSave
 * - localStorage 持久化 (per wpId)
 *
 * K8 销售费用损益类底稿（实质性分析+截止双向），
 * 结构化视图为主要交互模式，OnlyOffice 作为降级/偏好切换备选。
 */
import { ref, onMounted, type Ref } from 'vue'

export type K8RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'k8-dual-mode:'

export interface UseK8DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useK8DualMode(options: UseK8DualModeOptions) {
  const { wpId, autoSave, reloadAll } = options

  const currentMode = ref<K8RenderMode>('html')
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

  function persistMode(mode: K8RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  /**
   * OO 健康检查 — GET /workpapers/onlyoffice/health
   * 双层兼容: result.data?.data?.healthy 或 result.data?.healthy 或 result.healthy
   */
  async function checkOoHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) {
        isOoAvailable.value = false
        return false
      }
      const result = await response.json()
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

  /**
   * 切换模式
   * - 切换前 autoSave
   * - 切回 HTML 时调 reloadAll 刷新数据
   */
  async function switchMode(target: K8RenderMode): Promise<void> {
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

  /** el-segmented @change 回调 */
  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as K8RenderMode)
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

export default useK8DualMode
