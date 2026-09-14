/**
 * useK9DualMode — K9 管理费用 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/k9-admin-expenses/
 * Task: 3.3（2026-07-23 对齐 D4/F2「拉取成功」范式重写）
 *
 * - el-segmented 切换 结构化视图(html) / 在线编辑(onlyoffice)
 * - OO 健康检查（http.get 带 auth，双层兼容）
 * - 🔴 切到 OnlyOffice 前**预拉该 sheet 的 onlyoffice-config**，
 *   拉取成功(config 非空) 才真正进入 OO 模式；失败则回退结构化视图
 *   （对齐 7-10 D4 范式 useF2DualMode / useWorkpaperEntryDualMode）
 * - localStorage 持久化 (per wpId)
 *
 * K9 管理费用损益类底稿（实质性分析+截止双向），
 * 结构化视图为主要交互模式，OnlyOffice 作为降级/偏好切换备选。
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

export type K9RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'k9-dual-mode:'

export interface UseK9DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useK9DualMode(options: UseK9DualModeOptions) {
  const { wpId, sheetName, autoSave, reloadAll } = options

  const currentMode = ref<K9RenderMode>('html')
  const isOoAvailable = ref(false)
  /** 预拉成功的 OO 配置（拉取成功的标志） */
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)
  /** 正在预拉 config */
  const fetchingConfig = ref(false)

  /** 在线编辑项在 OO 不可用时禁用（el-segmented 单项 disabled） */
  const modeOptions = computed(() => [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice', disabled: !isOoAvailable.value },
  ])

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: K9RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  /**
   * OO 健康检查 — GET /workpapers/onlyoffice/health（http.get 带 auth）
   * 双层兼容: result.data?.healthy 或 result.healthy
   */
  async function checkOoHealth(): Promise<boolean> {
    checking.value = true
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      const result = res.data?.data ?? res.data ?? {}
      const healthy = result.data?.healthy ?? result.healthy ?? false
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
   * - 🔴 切到 OO：先预拉 onlyoffice-config，拉取成功才进入 OO；失败回退 HTML
   * - 切回 HTML 时调 reloadAll 刷新数据
   */
  async function switchMode(target: K9RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    // autoSave before switching
    if (autoSave) {
      try { await autoSave() } catch { /* best effort */ }
    }

    if (target === 'onlyoffice') {
      const sn = sheetName?.value || 'K9'
      fetchingConfig.value = true
      try {
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { _silent: true } as any,
        )
        const result = res.data?.data ?? res.data ?? {}
        const cfg = result.data ?? result
        if (!cfg || (!cfg.config && !cfg.token && !cfg.onlyoffice_url)) {
          // 拉取内容为空视为失败
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
    void switchMode(val as K9RenderMode)
  }

  /**
   * GtOnlyOfficeSheet 加载失败（@fallback）回调：
   * config 已拉取但文档渲染/就绪失败 → 回退结构化视图并标记不可用，
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
      // 若持久化偏好为 OO 且健康，尝试预拉 config 恢复 OO 模式；否则留结构化
      if (currentMode.value === 'onlyoffice') {
        if (healthy) {
          currentMode.value = 'html' // 先回退，交由 switchMode 走「拉取成功」门控
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
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
    onOoLoadFailed,
  }
}

export default useK9DualMode
