/**
 * useL6DualMode — L6 专项应付款双模式切换 composable
 *
 * Spec: .kiro/specs/l6-special-payables/
 * Task: 3.3
 * Requirements: 6.4
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
import { useOnlyOfficeHealthProbe } from './useOnlyOfficeHealthProbe'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L6 渲染模式 */
export type L6RenderMode = 'structured' | 'onlyoffice'

/** el-segmented 选项 */
export interface L6ModeOption {
  label: string
  value: L6RenderMode
  disabled?: boolean
}

export interface UseL6DualModeOptions {
  wpId: Ref<string>
  defaultMode?: L6RenderMode
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** localStorage key prefix（按 wpId 存储） */
const STORAGE_KEY_PREFIX = 'l6-dual-mode'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L6 双模式切换
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.defaultMode 默认模式（默认 structured）
 */
export function useL6DualMode(options: UseL6DualModeOptions) {
  const { wpId, defaultMode = 'structured' } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const mode = ref<L6RenderMode>(defaultMode)
  // BP-6 收敛：OO 健康检查从共享 composable 获取
  const { isOOHealthy, ooChecking, checkOOHealth } = useOnlyOfficeHealthProbe()

  // ─── localStorage 持久化（按 wpId） ────────────────────────────────────

  function _storageKey(): string {
    return `${STORAGE_KEY_PREFIX}:${wpId.value}`
  }

  function _loadPersistedMode(): L6RenderMode {
    try {
      const stored = localStorage.getItem(_storageKey())
      if (stored === 'structured' || stored === 'onlyoffice') {
        return stored
      }
    } catch {
      // localStorage 不可用时静默回退
    }
    return 'structured'
  }

  function _persistMode(m: L6RenderMode): void {
    try {
      localStorage.setItem(_storageKey(), m)
    } catch {
      // 静默忽略
    }
  }

  // ─── Mode Switch ───────────────────────────────────────────────────────

  /**
   * 切换渲染模式
   * - OO 不可用时不允许切换到 onlyoffice
   */
  function switchMode(newMode: L6RenderMode): void {
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

  /** 当前是否 OnlyOffice 模式 */
  const isOnlyOffice = computed(() => mode.value === 'onlyoffice')

  /** el-segmented 模式选项列表 */
  const modeOptions = computed<L6ModeOption[]>(() => [
    { label: '结构化', value: 'structured' },
    { label: 'OnlyOffice', value: 'onlyoffice', disabled: !isOOHealthy.value },
  ])

  /** OO 不可用时的禁用 tooltip */
  const ooDisabledTooltip = computed(() => {
    if (ooChecking.value) return '正在检查在线编辑服务...'
    if (!isOOHealthy.value) return 'OnlyOffice 服务不可用，仅支持结构化视图'
    return ''
  })

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onMounted(async () => {
    // 健康检查
    await checkOOHealth()

    // 恢复用户偏好（按 wpId 持久化）
    const persisted = _loadPersistedMode()
    if (persisted === 'structured') {
      mode.value = 'structured'
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
    isOnlyOffice,
    modeOptions,
    ooDisabledTooltip,

    // 操作
    switchMode,
    checkOOHealth,
  }
}

export default useL6DualMode
