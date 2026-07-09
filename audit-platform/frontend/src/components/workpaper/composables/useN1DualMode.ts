/**
 * useN1DualMode — N1 递延所得税资产双模式切换 composable
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 3.3
 * Requirements: 3.4
 *
 * 职责：
 * - 三模式切换（结构化视图 / 矩阵视图 / 在线编辑OnlyOffice）
 * - el-segmented 控制
 * - OnlyOffice 健康检查: GET /api/workpapers/onlyoffice/health
 *   双层.data兼容: response.data?.data?.healthy ?? response.data?.healthy
 * - Auto-degrade: OO健康→可切在线编辑；OO不可用→仅结构化/矩阵视图
 * - 状态持久化（localStorage 按 wpId 记忆用户偏好）
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** N1 渲染模式 */
export type N1RenderMode = 'structured' | 'matrix' | 'onlyoffice'

/** el-segmented 选项 */
export interface N1ModeOption {
  label: string
  value: N1RenderMode
  disabled?: boolean
}

export interface UseN1DualModeOptions {
  wpId: Ref<string>
  defaultMode?: N1RenderMode
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** localStorage key prefix（按 wpId 存储） */
const STORAGE_KEY_PREFIX = 'n1-dual-mode'

/** OO 健康检查端点 */
const OO_HEALTH_ENDPOINT = '/api/workpapers/onlyoffice/health'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * N1 双模式切换（含矩阵视图）
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.defaultMode 默认模式（默认 structured）
 */
export function useN1DualMode(options: UseN1DualModeOptions) {
  const { wpId, defaultMode = 'structured' } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const mode = ref<N1RenderMode>(defaultMode)
  const isOOHealthy = ref<boolean>(false)
  const ooChecking = ref(false)

  // ─── localStorage 持久化（按 wpId） ────────────────────────────────────

  function _storageKey(): string {
    return `${STORAGE_KEY_PREFIX}:${wpId.value}`
  }

  function _loadPersistedMode(): N1RenderMode {
    try {
      const stored = localStorage.getItem(_storageKey())
      if (stored === 'structured' || stored === 'matrix' || stored === 'onlyoffice') {
        return stored
      }
    } catch {
      // localStorage 不可用时静默回退
    }
    return 'structured'
  }

  function _persistMode(m: N1RenderMode): void {
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
   * - structured 和 matrix 始终可切换
   */
  function switchMode(newMode: N1RenderMode): void {
    if (newMode === mode.value) return

    // OO 不可用时不允许切换到 onlyoffice
    if (newMode === 'onlyoffice' && !isOOHealthy.value) {
      return
    }

    mode.value = newMode
    _persistMode(newMode)
  }

  // ─── Computed ──────────────────────────────────────────────────────────

  /** 当前是否结构化模式 */
  const isStructured = computed(() => mode.value === 'structured')

  /** 当前是否矩阵视图模式 */
  const isMatrix = computed(() => mode.value === 'matrix')

  /** 当前是否 OnlyOffice 模式 */
  const isOnlyOffice = computed(() => mode.value === 'onlyoffice')

  /** el-segmented 模式选项列表 */
  const modeOptions = computed<N1ModeOption[]>(() => [
    { label: '结构化视图', value: 'structured' },
    { label: '矩阵视图', value: 'matrix' },
    { label: '在线编辑', value: 'onlyoffice', disabled: !isOOHealthy.value },
  ])

  /** OO 不可用时的禁用 tooltip */
  const ooDisabledTooltip = computed(() => {
    if (ooChecking.value) return '正在检查在线编辑服务...'
    if (!isOOHealthy.value) return 'OnlyOffice 服务不可用，仅支持结构化/矩阵视图'
    return ''
  })

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onMounted(async () => {
    // 健康检查
    await checkOOHealth()

    // 恢复用户偏好（按 wpId 持久化）
    const persisted = _loadPersistedMode()
    if (persisted === 'structured' || persisted === 'matrix') {
      mode.value = persisted
    } else if (persisted === 'onlyoffice' && isOOHealthy.value) {
      mode.value = 'onlyoffice'
    } else {
      // OO 不可用时降级到结构化
      mode.value = 'structured'
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    mode,
    isOOHealthy,
    ooChecking,

    // 计算属性
    isStructured,
    isMatrix,
    isOnlyOffice,
    modeOptions,
    ooDisabledTooltip,

    // 操作
    switchMode,
    checkOOHealth,
  }
}

export default useN1DualMode
