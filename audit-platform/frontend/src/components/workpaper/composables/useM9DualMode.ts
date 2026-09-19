/**
 * useM9DualMode — M9 其他综合收益双模式切换 composable
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 3.3
 * Requirements: 6.5
 *
 * 职责：
 * - 双模式切换（结构化视图 / OnlyOffice降级）
 * - el-segmented 控制（结构化 / OnlyOffice）
 * - OnlyOffice 健康检查: GET /api/workpapers/onlyoffice/health
 *   双层.data兼容: response.data?.data?.healthy ?? response.data?.healthy
 * - Auto-degrade: OO健康→默认结构化可切OO；OO不可用→仅结构化
 * - 状态持久化（localStorage 按 wpId 记忆用户偏好）
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** M9 渲染模式 */
export type M9RenderMode = 'html' | 'onlyoffice'

/** el-segmented 选项 */
export interface M9ModeOption {
  label: string
  value: M9RenderMode
  disabled?: boolean
}

export interface UseM9DualModeOptions {
  wpId: Ref<string>
  defaultMode?: M9RenderMode
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** localStorage key prefix（按 wpId 存储） */
const STORAGE_KEY_PREFIX = 'm9-dual-mode'

/** OO 健康检查端点 */
const OO_HEALTH_ENDPOINT = '/api/workpapers/onlyoffice/health'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M9 双模式切换
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.defaultMode 默认模式（默认 html）
 */
export function useM9DualMode(options: UseM9DualModeOptions) {
  const { wpId, defaultMode = 'html' } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const mode = ref<M9RenderMode>(defaultMode)
  const isOoHealthy = ref<boolean>(false)
  const ooChecking = ref(false)

  // ─── localStorage 持久化（按 wpId） ────────────────────────────────────

  function _storageKey(): string {
    return `${STORAGE_KEY_PREFIX}:${wpId.value}`
  }

  function _loadPersistedMode(): M9RenderMode {
    try {
      const stored = localStorage.getItem(_storageKey())
      if (stored === 'html' || stored === 'onlyoffice') {
        return stored
      }
    } catch {
      // localStorage 不可用时静默回退
    }
    return 'html'
  }

  function _persistMode(m: M9RenderMode): void {
    try {
      localStorage.setItem(_storageKey(), m)
    } catch {
      // 静默忽略
    }
  }

  // ─── OnlyOffice Health Check ───────────────────────────────────────────

  /**
   * 检查 OnlyOffice 服务是否可用
   * 双层.data兼容: ResponseWrapperMiddleware 信封 {code,message,data:{healthy:true}}
   */
  async function checkOoHealth(): Promise<void> {
    ooChecking.value = true
    try {
      const response = await http.get(OO_HEALTH_ENDPOINT)
      // 双层.data兼容
      const healthy = (response as any).data?.data?.healthy
        ?? (response as any).data?.healthy
        ?? false
      isOoHealthy.value = Boolean(healthy)
    } catch {
      isOoHealthy.value = false
    } finally {
      ooChecking.value = false
    }
  }

  // ─── Mode Switch ───────────────────────────────────────────────────────

  /**
   * 切换渲染模式
   * - OO 不可用时不允许切换到 onlyoffice
   */
  function switchMode(newMode: M9RenderMode): void {
    if (newMode === mode.value) return

    // OO 不可用时不允许切换到 onlyoffice
    if (newMode === 'onlyoffice' && !isOoHealthy.value) {
      return
    }

    mode.value = newMode
    _persistMode(newMode)
  }

  // ─── Computed ──────────────────────────────────────────────────────────

  /** 当前是否HTML结构化模式 */
  const isHtml = computed(() => mode.value === 'html')

  /** 当前是否 OnlyOffice 模式 */
  const isOnlyOffice = computed(() => mode.value === 'onlyoffice')

  /** el-segmented 模式选项列表 */
  const modeOptions = computed<M9ModeOption[]>(() => [
    { label: '结构化', value: 'html' },
    { label: 'OnlyOffice', value: 'onlyoffice', disabled: !isOoHealthy.value },
  ])

  /** OO 不可用时的禁用 tooltip */
  const ooDisabledTooltip = computed(() => {
    if (ooChecking.value) return '正在检查在线编辑服务...'
    if (!isOoHealthy.value) return 'OnlyOffice 服务不可用，仅支持结构化视图'
    return ''
  })

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onMounted(async () => {
    // 健康检查
    await checkOoHealth()

    // 恢复用户偏好（按 wpId 持久化）
    const persisted = _loadPersistedMode()
    if (persisted === 'html') {
      mode.value = 'html'
    } else if (persisted === 'onlyoffice' && isOoHealthy.value) {
      mode.value = 'onlyoffice'
    } else {
      // OO 不可用时降级到结构化
      mode.value = 'html'
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    mode,
    isOoHealthy,
    ooChecking,

    // 计算属性
    isHtml,
    isOnlyOffice,
    modeOptions,
    ooDisabledTooltip,

    // 操作
    switchMode,
    checkOoHealth,
  }
}

export default useM9DualMode
