/**
 * createDualMode — 参数化工厂：HTML/OnlyOffice 双模式切换 composable
 *
 * Feature: platform-global-hardening
 * Requirements: 6.5, 6.6
 *
 * 用于收敛 useD2DualMode / useF1DualMode / useG1DualMode 等同构实现。
 * 每个循环底稿的 DualMode composable 结构相同：
 *   - 默认 HTML 模式
 *   - 检测 OnlyOffice 可用性
 *   - localStorage 持久化用户偏好
 *   - 模式切换（含 OO 不可用时回退到 HTML）
 */
import { ref, computed, onMounted, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DualModeType = 'html' | 'onlyoffice'

export interface DualModeConfig {
  /** 默认模式，默认 'html' */
  defaultMode?: DualModeType
  /** localStorage 持久化 key，如不提供则不持久化 */
  persistKey?: string
  /** OO 健康检查端点，默认 /api/workpapers/onlyoffice/health */
  healthEndpoint?: string
  /** 切回 HTML 后的回调（如重新加载数据） */
  onSwitchToHtml?: () => void | Promise<void>
}

export interface DualModeReturn {
  /** 当前模式 */
  currentMode: Ref<DualModeType>
  /** 是否 HTML 模式 */
  isHtmlMode: ComputedRef<boolean>
  /** 是否 OnlyOffice 模式 */
  isOoMode: ComputedRef<boolean>
  /** OO 是否可用 */
  isOoAvailable: Ref<boolean>
  /** 正在检查 OO 健康状态 */
  checking: Ref<boolean>
  /** 切换模式 */
  toggleMode: () => Promise<void>
  /** 切换到指定模式 */
  switchMode: (target: DualModeType) => Promise<void>
  /** el-segmented onChange 适配器 */
  onModeChange: (val: string | number | boolean) => void
  /** 手动检查 OO 健康 */
  checkOOHealth: () => Promise<boolean>
}

// ─── Factory ─────────────────────────────────────────────────────────────────

export function createDualMode(config: DualModeConfig = {}): DualModeReturn {
  const {
    defaultMode = 'html',
    persistKey,
    healthEndpoint = '/api/workpapers/onlyoffice/health',
    onSwitchToHtml,
  } = config

  const currentMode = ref<DualModeType>(defaultMode)
  const isOoAvailable = ref(false)
  const checking = ref(false)

  const isHtmlMode = computed(() => currentMode.value === 'html')
  const isOoMode = computed(() => currentMode.value === 'onlyoffice')

  function loadPersistedMode(): void {
    if (!persistKey) return
    try {
      const saved = localStorage.getItem(persistKey)
      if (saved === 'html' || saved === 'onlyoffice') {
        currentMode.value = saved
      }
    } catch { /* ignore storage access errors */ }
  }

  function persistMode(mode: DualModeType): void {
    if (!persistKey) return
    try {
      localStorage.setItem(persistKey, mode)
    } catch { /* ignore */ }
  }

  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch(healthEndpoint)
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

  async function switchMode(target: DualModeType): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    currentMode.value = target
    persistMode(target)

    if (target === 'html' && onSwitchToHtml) {
      await onSwitchToHtml()
    }
  }

  async function toggleMode(): Promise<void> {
    const next: DualModeType = currentMode.value === 'html' ? 'onlyoffice' : 'html'
    await switchMode(next)
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as DualModeType)
  }

  onMounted(async () => {
    await checkOOHealth()
    loadPersistedMode()
    // 如果持久化为 OO 但 OO 不可用，回退 HTML
    if (currentMode.value === 'onlyoffice' && !isOoAvailable.value) {
      currentMode.value = 'html'
    }
  })

  return {
    currentMode,
    isHtmlMode,
    isOoMode,
    isOoAvailable,
    checking,
    toggleMode,
    switchMode,
    onModeChange,
    checkOOHealth,
  }
}
