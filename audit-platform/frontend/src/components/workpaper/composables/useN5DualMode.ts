/**
 * useN5DualMode — N5 所得税费用双模式切换 composable
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Task: 3.3
 * Requirements: 4.6
 *
 * 职责：
 * - 双模式切换（HTML精美模式 / OnlyOffice模式）
 * - el-segmented 控制（"HTML精美模式" / "OnlyOffice模式"）
 * - OnlyOffice 健康检查: GET /api/workpapers/onlyoffice/health
 *   双层.data兼容: response.data?.data?.healthy ?? response.data?.healthy
 * - Auto-degrade: OO健康→默认HTML可切OO；OO不可用→仅HTML
 * - 状态持久化（localStorage 记忆用户偏好）
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** N5 渲染模式 */
export type N5RenderMode = 'html' | 'onlyoffice'

/** el-segmented 选项 */
export interface N5ModeOption {
  label: string
  value: N5RenderMode
  disabled?: boolean
}

export interface UseN5DualModeOptions {
  wpId: Ref<string>
  defaultMode?: N5RenderMode
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** localStorage key */
const STORAGE_KEY = 'n5-dual-mode'

/** OO 健康检查端点 */
const OO_HEALTH_ENDPOINT = '/api/workpapers/onlyoffice/health'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * N5 双模式切换
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.defaultMode 默认模式（默认 html）
 */
export function useN5DualMode(options: UseN5DualModeOptions) {
  const { wpId, defaultMode = 'html' } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const currentMode = ref<N5RenderMode>(defaultMode)
  const isOOHealthy = ref<boolean>(false)
  const ooChecking = ref(false)

  // ─── localStorage 持久化 ───────────────────────────────────────────────

  function _loadPersistedMode(): N5RenderMode {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored === 'html' || stored === 'onlyoffice') {
        return stored
      }
    } catch {
      // localStorage 不可用时静默回退
    }
    return 'html'
  }

  function _persistMode(m: N5RenderMode): void {
    try {
      localStorage.setItem(STORAGE_KEY, m)
    } catch {
      // 静默忽略
    }
  }

  // ─── OnlyOffice Health Check ───────────────────────────────────────────

  /**
   * 检查 OnlyOffice 服务是否可用
   * 双层.data兼容: ResponseWrapperMiddleware 信封 {code,message,data:{healthy:true}}
   */
  async function checkOOHealth(): Promise<boolean> {
    ooChecking.value = true
    try {
      const response = await http.get(OO_HEALTH_ENDPOINT)
      // 双层.data兼容
      const healthy = (response as any).data?.data?.healthy
        ?? (response as any).data?.healthy
        ?? false
      isOOHealthy.value = Boolean(healthy)
      return isOOHealthy.value
    } catch {
      isOOHealthy.value = false
      return false
    } finally {
      ooChecking.value = false
    }
  }

  // ─── Mode Switch ───────────────────────────────────────────────────────

  /**
   * 切换渲染模式
   * - OO 不可用时不允许切换到 onlyoffice
   */
  function switchMode(newMode: N5RenderMode): void {
    if (newMode === currentMode.value) return

    // OO 不可用时不允许切换到 onlyoffice
    if (newMode === 'onlyoffice' && !isOOHealthy.value) {
      return
    }

    currentMode.value = newMode
    _persistMode(newMode)
  }

  // ─── Computed ──────────────────────────────────────────────────────────

  /** 当前是否HTML精美模式 */
  const isHtmlMode = computed(() => currentMode.value === 'html')

  /** 当前是否 OnlyOffice 模式 */
  const isOoMode = computed(() => currentMode.value === 'onlyoffice')

  /** el-segmented 模式选项列表 */
  const modes = computed<N5ModeOption[]>(() => [
    { label: 'HTML精美模式', value: 'html' },
    { label: 'OnlyOffice模式', value: 'onlyoffice', disabled: !isOOHealthy.value },
  ])

  /** OO 不可用时的禁用 tooltip */
  const ooDisabledTooltip = computed(() => {
    if (ooChecking.value) return '正在检查在线编辑服务...'
    if (!isOOHealthy.value) return 'OnlyOffice 服务不可用，仅支持HTML精美模式'
    return ''
  })

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onMounted(async () => {
    // 健康检查
    await checkOOHealth()

    // 恢复用户偏好
    const persisted = _loadPersistedMode()
    if (persisted === 'html') {
      currentMode.value = 'html'
    } else if (persisted === 'onlyoffice' && isOOHealthy.value) {
      currentMode.value = 'onlyoffice'
    } else {
      // OO 不可用时降级到HTML
      currentMode.value = 'html'
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    currentMode,
    isOOHealthy,
    ooChecking,

    // 计算属性
    isHtmlMode,
    isOoMode,
    modes,
    ooDisabledTooltip,

    // 操作
    switchMode,
    checkOOHealth,
  }
}

export default useN5DualMode
