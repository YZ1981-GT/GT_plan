/**
 * useH2DualMode — H2 在建工程 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/h2-construction-in-progress/ Task 6.2
 * Requirements: 14.1-14.2
 *
 * - el-segmented 切换 HTML / OnlyOffice
 * - OO 健康检查（http.get 带鉴权，双层兼容）
 * - 切 OO 前预拉 onlyoffice-config（拉取成功才切，对齐 useF2DualMode 范式）
 * - 切换前 autoSave
 * - localStorage 持久化 (per wpId)
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

export type H2RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'h2-dual-mode:'

export interface UseH2DualModeOptions {
  wpId: Ref<string>
  projectId?: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useH2DualMode(options: UseH2DualModeOptions) {
  const { wpId, projectId, autoSave, reloadAll } = options

  const currentMode = ref<H2RenderMode>('html')
  const isOoAvailable = ref(false)
  const checking = ref(false)
  const fetchingConfig = ref(false)
  /** 配置预拉成功后为 true（真·「拉取成功」） */
  const ooConfigReady = ref(false)

  const modeOptions = computed(() => [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice', disabled: !isOoAvailable.value },
  ])

  /** 健康状态标签 */
  const healthTag = computed(() => {
    if (checking.value) return { text: '检测中…', type: 'info' as const }
    if (fetchingConfig.value) return { text: '拉取配置中…', type: 'info' as const }
    if (ooConfigReady.value) return { text: 'OnlyOffice 拉取成功', type: 'success' as const }
    if (isOoAvailable.value) return { text: 'OnlyOffice 就绪', type: 'success' as const }
    return { text: '仅结构化视图', type: 'warning' as const }
  })

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: H2RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  /** OO 健康检查 — 使用 http.get 带鉴权（修复裸 fetch 无 Authorization 被 gate 拦截 401 的 bug） */
  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      // http 拦截器已解包信封：res.data 直接是 {healthy,...}
      const result = res?.data ?? res
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

  async function switchMode(target: H2RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    // autoSave before switching
    if (autoSave) {
      try { await autoSave() } catch { /* best effort */ }
    }

    if (target === 'onlyoffice') {
      // 预拉 onlyoffice-config：拉取成功才切换（对齐 useF2DualMode/useK10DualMode 范式）
      fetchingConfig.value = true
      try {
        const configRes = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(options.sheetName?.value || 'H2-1')}/onlyoffice-config`,
          { params: { project_id: projectId?.value }, _silent: true } as any,
        )
        const cfg = configRes?.data ?? configRes
        if (!cfg || (typeof cfg === 'object' && Object.keys(cfg).length === 0)) {
          // config 为空 → 不切换
          isOoAvailable.value = false
          ooConfigReady.value = false
          return
        }
        ooConfigReady.value = true
      } catch {
        // config 拉取失败 → 回退 html
        ooConfigReady.value = false
        return
      } finally {
        fetchingConfig.value = false
      }
      currentMode.value = 'onlyoffice'
      persistMode('onlyoffice')
    } else {
      currentMode.value = 'html'
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  /** @fallback handler：GtOnlyOfficeSheet 渲染/超时失败后回退 html */
  function onOoLoadFailed(): void {
    currentMode.value = 'html'
    persistMode('html')
    ooConfigReady.value = false
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as H2RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void checkOOHealth()
  })

  return {
    currentMode,
    isOoAvailable,
    checking,
    fetchingConfig,
    ooConfigReady,
    healthTag,
    modeOptions,
    switchMode,
    onModeChange,
    onOoLoadFailed,
    checkOOHealth,
  }
}

export default useH2DualMode
