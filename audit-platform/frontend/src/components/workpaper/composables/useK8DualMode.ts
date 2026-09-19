/**
 * useK8DualMode — K8 销售费用 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Task: 3.3
 *
 * 对齐 D4 七月十日 + K9 孪生模块「拉取成功才可以」范式：
 * - 健康检查用 `http.get`（带鉴权头 + _silent），不用裸 fetch（修 401→OO 永不可用）。
 * - 🔴 切到 OnlyOffice 前**预拉该 sheet 的 onlyoffice-config**，config 非空（拉取成功）
 *   才真正进入 OO 模式；失败回退结构化视图（对齐 useK9DualMode/useF2DualMode）。
 * - 🔴 `onOoLoadFailed`：GtOnlyOfficeSheet 文档渲染/45s 就绪失败 @fallback 时回退 HTML+
 *   标记不可用，避免「拉取成功」标签与实际错误页不一致。
 * - 「在线编辑」选项常显但 `disabled:!isOoAvailable`；切换前 autoSave；切回 reloadAll。
 * - localStorage 持久化 (per wpId)。
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

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
  const { wpId, sheetName, autoSave, reloadAll } = options

  const currentMode = ref<K8RenderMode>('html')
  const isOoAvailable = ref(false)
  /** 预拉成功的 OO 配置（拉取成功的标志） */
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)
  /** 正在预拉 config */
  const fetchingConfig = ref(false)

  /** 「在线编辑」未拉取成功前置灰（D4 always-visible + disabled 范式） */
  const modeOptions = computed(() => [
    { label: '结构化视图', value: 'html' },
    {
      label: isOoAvailable.value ? '在线编辑（就绪）' : '在线编辑',
      value: 'onlyoffice',
      disabled: !isOoAvailable.value,
    },
  ])

  /** 顶部状态标签：就绪(拉取成功)/拉取中/检测中/不可用 */
  const healthStatus = computed<'ready' | 'fetching' | 'checking' | 'unavailable'>(() => {
    if (fetchingConfig.value) return 'fetching'
    if (checking.value) return 'checking'
    return isOoAvailable.value ? 'ready' : 'unavailable'
  })

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
   * OO 健康检查 — GET /api/workpapers/onlyoffice/health（http.get 带 auth）
   * 信封双层兼容: res.data?.data?.healthy 或 res.data?.healthy 或 res.healthy
   */
  async function checkOoHealth(): Promise<boolean> {
    checking.value = true
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      const healthy = res.data?.data?.healthy ?? res.data?.healthy ?? (res as any)?.healthy ?? false
      isOoAvailable.value = !!healthy
      return isOoAvailable.value
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
   * - 🔴 切到 OO：先预拉 onlyoffice-config，config 非空才进入 OO；失败回退 HTML
   * - 切回 HTML 时调 reloadAll 刷新数据
   */
  async function switchMode(target: K8RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (autoSave) {
      try { await autoSave() } catch { /* best effort */ }
    }

    if (target === 'onlyoffice') {
      const sn = sheetName?.value || 'K8'
      fetchingConfig.value = true
      try {
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { _silent: true } as any,
        )
        const result = res.data?.data ?? res.data ?? {}
        const cfg = result.data ?? result
        if (!cfg || (!cfg.config && !cfg.token && !cfg.onlyoffice_url)) {
          throw new Error('empty onlyoffice-config')
        }
        ooConfig.value = cfg
        currentMode.value = 'onlyoffice'
        persistMode('onlyoffice')
      } catch {
        // 拉取失败 → 不进入 OO，回退结构化视图
        isOoAvailable.value = false
        ooConfig.value = null
        currentMode.value = 'html'
        persistMode('html')
      } finally {
        fetchingConfig.value = false
      }
    } else {
      currentMode.value = 'html'
      ooConfig.value = null
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  /** el-segmented @change 回调 */
  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as K8RenderMode)
  }

  /**
   * GtOnlyOfficeSheet 加载失败（@fallback）回调：
   * config 已拉取但文档渲染/就绪超时失败 → 回退结构化视图并标记不可用，
   * 避免「拉取成功」标签与实际错误页不一致（P0-B）。
   */
  function onOoLoadFailed(): void {
    isOoAvailable.value = false
    ooConfig.value = null
    currentMode.value = 'html'
    persistMode('html')
    if (reloadAll) void reloadAll()
  }

  onMounted(() => {
    loadPersistedMode()
    void (async () => {
      const healthy = await checkOoHealth()
      // 持久化偏好为 OO 且健康：走 switchMode 的「拉取成功」门控恢复；否则留结构化
      if (currentMode.value === 'onlyoffice') {
        if (healthy) {
          currentMode.value = 'html'
          await switchMode('onlyoffice')
        } else {
          currentMode.value = 'html'
          persistMode('html')
        }
      }
    })()
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,
    fetchingConfig,
    healthStatus,
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
    onOoLoadFailed,
  }
}

export default useK8DualMode
