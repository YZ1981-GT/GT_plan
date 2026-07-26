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
  /**
   * 当前 sheet 是否支持「矩阵视图」（默认 false）。
   *
   * 平台矩阵视图语义（J1-8 / D2-7 已 proven）= 行 × 判断项的核对矩阵。
   * N1 中只有 N1-5 亏损检查表属该语义（届满 / 所得额是否充足 / 依据是否已填），
   * 其余 sheet 是纯数值表，呈现矩阵选项会变成"点了没反应"的死选项。
   */
  supportsMatrix?: Ref<boolean> | boolean
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
  const { wpId, defaultMode = 'structured', supportsMatrix = false } = options

  /** 当前 sheet 是否支持矩阵视图（reactive 或常量） */
  const matrixSupported = computed<boolean>(() =>
    typeof supportsMatrix === 'boolean' ? supportsMatrix : !!supportsMatrix.value,
  )

  // ─── State ─────────────────────────────────────────────────────────────

  const mode = ref<N1RenderMode>(defaultMode)
  const isOOHealthy = ref<boolean>(false)
  const ooChecking = ref(false)
  /** 切 OO 前预拉 onlyoffice-config 是否成功（"拉取成功才可切"的正向状态） */
  const ooConfigReady = ref(false)
  const fetchingConfig = ref(false)

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
   * 切换渲染模式（平台"拉取成功才可切"标准）。
   *
   * 🔴 铁律：调用方 el-segmented 必须用 `:model-value` + `@change`，**禁用 v-model**。
   * v-model 会先把 mode 改掉，使本函数首行 `newMode === mode.value` 短路 →
   * 健康门控/config 预拉/localStorage 持久化全部失效。
   *
   * @param sheetName 目标 OnlyOffice sheet 名（传入则切 OO 前先预拉 config，拉取成功才切）
   */
  async function switchMode(newMode: N1RenderMode, sheetName?: string): Promise<void> {
    if (newMode === mode.value) return

    // 当前 sheet 不支持矩阵视图时不允许切到 matrix（防历史持久化值/误传）
    if (newMode === 'matrix' && !matrixSupported.value) return

    if (newMode === 'onlyoffice') {
      // OO 不可用时不允许切换到 onlyoffice
      if (!isOOHealthy.value) return
      if (sheetName) {
        fetchingConfig.value = true
        try {
          const res: any = await http.get(
            `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sheetName)}/onlyoffice-config`,
            { _silent: true } as any,
          )
          const cfg = res?.data?.data ?? res?.data
          if (!cfg) {
            ooConfigReady.value = false
            return // 拉取失败 → 保持结构化视图
          }
          ooConfigReady.value = true
        } catch {
          ooConfigReady.value = false
          return
        } finally {
          fetchingConfig.value = false
        }
      }
    }

    mode.value = newMode
    _persistMode(newMode)
  }

  /** GtOnlyOfficeSheet @fallback：文档渲染/超时失败 → 回退结构化并标记不可用 */
  function onOoLoadFailed(): void {
    ooConfigReady.value = false
    isOOHealthy.value = false
    mode.value = 'structured'
    _persistMode('structured')
  }

  // ─── Computed ──────────────────────────────────────────────────────────

  /** 当前是否结构化模式 */
  const isStructured = computed(() => mode.value === 'structured')

  /** 当前是否矩阵视图模式 */
  const isMatrix = computed(() => mode.value === 'matrix')

  /** 当前是否 OnlyOffice 模式 */
  const isOnlyOffice = computed(() => mode.value === 'onlyoffice')

  /**
   * el-segmented 模式选项列表。
   *
   * 🔴「矩阵视图」只在支持该语义的 sheet 呈现（N1 目前仅 N1-5 亏损检查表：行 × 判断项核对矩阵）。
   * 纯数值 sheet 不呈现该项，否则选了等于结构化视图 = 点了没反应的死选项。
   */
  const modeOptions = computed<N1ModeOption[]>(() => {
    const opts: N1ModeOption[] = [{ label: '结构化视图', value: 'structured' }]
    if (matrixSupported.value) opts.push({ label: '矩阵视图', value: 'matrix' })
    opts.push({ label: '在线编辑', value: 'onlyoffice', disabled: !isOOHealthy.value })
    return opts
  })

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

    // 恢复用户偏好（按 wpId 持久化）；matrix 仅在当前 sheet 支持时恢复，否则降级结构化
    const persisted = _loadPersistedMode()
    if (persisted === 'matrix') {
      mode.value = matrixSupported.value ? 'matrix' : 'structured'
    } else if (persisted === 'structured') {
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
    ooConfigReady,
    fetchingConfig,

    // 计算属性
    isStructured,
    isMatrix,
    isOnlyOffice,
    matrixSupported,
    modeOptions,
    ooDisabledTooltip,

    // 操作
    switchMode,
    checkOOHealth,
    onOoLoadFailed,
  }
}

export default useN1DualMode
