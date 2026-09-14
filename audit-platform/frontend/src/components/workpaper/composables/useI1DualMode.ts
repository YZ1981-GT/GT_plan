/**
 * useI1DualMode — I1 无形资产 HTML ↔ OnlyOffice 双模式切换
 *
 * - el-segmented 双模式: 结构化视图 / 在线编辑(OnlyOffice)
 * - OO 健康检查 (GET /api/workpapers/onlyoffice/health)
 * - 如果 OO 不健康则隐藏切换按钮，强制 HTML 模式
 * - localStorage 持久化 (per wpId)
 * - Follow useH1DualMode pattern
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Task: 3.7
 * Requirements: 14.1-14.4
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export type I1RenderMode = 'html' | 'onlyoffice'

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_PREFIX = 'i1-dual-mode:'

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseI1DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1DualMode(options: UseI1DualModeOptions) {
  const { wpId, autoSave, reloadAll } = options

  const currentMode = ref<I1RenderMode>('html')
  const isOoAvailable = ref(false)
  const checking = ref(false)

  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  // ─── localStorage 持久化 ───────────────────────────────────────────────────

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: I1RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  // ─── OO 健康检查 ──────────────────────────────────────────────────────────

  /**
   * GET /api/workpapers/onlyoffice/health
   * 双层兼容: result.data?.data?.healthy 或 result.data?.healthy 或 result.healthy
   * 如果 OO 不健康，隐藏 toggle，强制 HTML 模式。
   */
  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const res = await http.get('/workpapers/onlyoffice/health', { _silent: true } as any)
      // http axios response: res.data is the response body (may be wrapped)
      const result = res.data
      // 双层兼容: result.data?.healthy 或 result.healthy
      const healthy = result?.data?.healthy ?? result?.healthy ?? false
      isOoAvailable.value = healthy
      return healthy
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  // ─── 切换逻辑 ─────────────────────────────────────────────────────────────

  /**
   * 切换模式。切换前 autoSave，切回 HTML 后 reloadAll。
   * OO 不可用时禁止切换到 onlyoffice。
   */
  async function switchMode(target: I1RenderMode): Promise<void> {
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

  /**
   * el-segmented change handler
   */
  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as I1RenderMode)
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────────

  onMounted(() => {
    loadPersistedMode()
    void checkOOHealth()
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    currentMode,
    isOoAvailable,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOOHealth,
  }
}

export default useI1DualMode
