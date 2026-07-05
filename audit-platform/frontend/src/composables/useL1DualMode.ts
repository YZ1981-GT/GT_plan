/**
 * useL1DualMode — L1 短期借款双模式切换 composable
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.3
 * Requirements: 11.1
 *
 * 职责：
 * - 双模式切换（结构化视图 / OnlyOffice矩阵视图）
 * - el-segmented 控制当前模式
 * - OnlyOffice 健康检查（降级逻辑：OO 不可用时仅显示结构化）
 * - 状态持久化（localStorage 记忆用户偏好）
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L1 渲染模式 */
export type L1RenderMode = 'structured' | 'matrix' | 'onlyoffice'

/** el-segmented 选项 */
export interface L1ModeOption {
  label: string
  value: L1RenderMode
  disabled?: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** localStorage key 前缀 */
const STORAGE_KEY_PREFIX = 'l1-dual-mode-'

/** OO 健康检查端点 */
const OO_HEALTH_ENDPOINT = '/api/workpapers/onlyoffice/health'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1 双模式切换
 *
 * @param wpId 底稿ID（reactive）
 */
export function useL1DualMode(wpId: Ref<string>) {
  // ─── State ─────────────────────────────────────────────────────────────

  const currentMode = ref<L1RenderMode>('structured')
  const isOnlyOfficeHealthy = ref<boolean>(false)
  const ooChecking = ref(false)

  // ─── localStorage 持久化 ───────────────────────────────────────────────

  function _getStorageKey(): string {
    return `${STORAGE_KEY_PREFIX}${wpId.value}`
  }

  function _loadPersistedMode(): L1RenderMode {
    try {
      const stored = localStorage.getItem(_getStorageKey())
      if (stored === 'structured' || stored === 'matrix' || stored === 'onlyoffice') {
        return stored
      }
    } catch {
      // localStorage 不可用时静默回退
    }
    return 'structured'
  }

  function _persistMode(mode: L1RenderMode): void {
    try {
      localStorage.setItem(_getStorageKey(), mode)
    } catch {
      // 静默忽略
    }
  }

  // ─── OnlyOffice Health Check ───────────────────────────────────────────

  /**
   * 检查 OnlyOffice 服务是否可用
   * GET /api/workpapers/onlyoffice/health
   * 双层.data兼容: response.data?.data?.healthy ?? response.data?.healthy
   */
  async function checkOnlyOfficeHealth(): Promise<void> {
    ooChecking.value = true
    try {
      const response = await http.get(OO_HEALTH_ENDPOINT)
      // 兼容 ResponseWrapperMiddleware 信封
      const healthy = (response as any).data?.data?.healthy
        ?? (response as any).data?.healthy
        ?? false
      isOnlyOfficeHealthy.value = Boolean(healthy)
    } catch {
      isOnlyOfficeHealthy.value = false
    } finally {
      ooChecking.value = false
    }
  }

  // ─── Mode Switch ───────────────────────────────────────────────────────

  /**
   * 切换渲染模式
   * - 切 onlyoffice：需 OO 健康检查通过
   * - 降级逻辑：OO 不可用时切换请求静默忽略
   */
  function switchMode(mode: L1RenderMode): void {
    if (mode === currentMode.value) return

    // OO 不可用时不允许切换到 onlyoffice/matrix（matrix 也依赖 OO）
    if ((mode === 'onlyoffice' || mode === 'matrix') && !isOnlyOfficeHealthy.value) {
      return
    }

    currentMode.value = mode
    _persistMode(mode)
  }

  // ─── Computed ──────────────────────────────────────────────────────────

  /** 当前是否结构化模式 */
  const isStructured = computed(() => currentMode.value === 'structured')

  /** 当前是否矩阵视图模式 */
  const isMatrix = computed(() => currentMode.value === 'matrix')

  /** 当前是否在线编辑模式 */
  const isOnlyOffice = computed(() => currentMode.value === 'onlyoffice')

  /** el-segmented 模式选项列表 */
  const modeOptions = computed<L1ModeOption[]>(() => [
    { label: '结构化视图', value: 'structured' },
    { label: '矩阵视图', value: 'matrix', disabled: !isOnlyOfficeHealthy.value },
    { label: '在线编辑', value: 'onlyoffice', disabled: !isOnlyOfficeHealthy.value },
  ])

  /** OO 不可用时的禁用 tooltip */
  const ooDisabledTooltip = computed(() => {
    if (ooChecking.value) return '正在检查在线编辑服务...'
    if (!isOnlyOfficeHealthy.value) return 'OnlyOffice 服务不可用，仅支持结构化视图'
    return ''
  })

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onMounted(async () => {
    // 健康检查
    await checkOnlyOfficeHealth()

    // 恢复用户偏好
    const persisted = _loadPersistedMode()
    if (persisted === 'structured') {
      currentMode.value = 'structured'
    } else if ((persisted === 'matrix' || persisted === 'onlyoffice') && isOnlyOfficeHealthy.value) {
      currentMode.value = persisted
    } else {
      // OO 不可用时降级到结构化
      currentMode.value = 'structured'
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    currentMode,
    isOnlyOfficeHealthy,
    ooChecking,

    // 计算属性
    isStructured,
    isMatrix,
    isOnlyOffice,
    modeOptions,
    ooDisabledTooltip,

    // 操作
    switchMode,
    checkOnlyOfficeHealth,
  }
}

export default useL1DualMode
