/**
 * useG1DualMode — G1 HTML ↔ OnlyOffice 双模式（对齐 D4/F2/K11「拉取成功才可以」范式）
 *
 * 2026-07 复盘修复：原实现只做 health 检查即允许切 OnlyOffice，未预拉该 sheet 的
 * onlyoffice-config —— 与 D4/F2/K9-K13 等 gold 范式不一致（health 通过 ≠ 该 sheet
 * 真能拉到文档）。本次改为：
 * - 健康检查后才允许切在线编辑（isOoAvailable）；
 * - 切到 onlyoffice 前先 GET onlyoffice-config（带 project_id），**拉取成功才真正切换**，
 *   失败则回退结构化视图（单 sheet 失败不全局禁用 OO）；
 * - 暴露 ooConfigReady / fetchingConfig 供上层展示"拉取成功"状态（对齐 K11）。
 * - resolveOoSheetName：编码 → 真实 sheet_name（供 GtOnlyOfficeSheet / config 预拉）
 * - fallback：OO 初始化失败时由入口切回 html
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'
import { dualModeHtmlOoOptions } from './dualModeLabels'
import { resolveG1SheetLabel } from './g1SheetLabels'

export type G1RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g1-dual-mode:'

export interface UseG1DualModeOptions {
  wpId: Ref<string>
  /** 当前分发编码，如 G1-9 */
  currentSheet: Ref<string>
  /** render-config / htmlData.sheets */
  availableSheets: Ref<Array<{ sheet_name?: string }>>
  /** 外层传入的完整 sheetName（优先用于匹配） */
  sheetName?: Ref<string>
  /** 项目 id（onlyoffice-config 端点 query 参，缺失多数项目仍可用，但传入更稳） */
  projectId?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useG1DualMode(options: UseG1DualModeOptions) {
  const { wpId, currentSheet, availableSheets, sheetName, projectId, reloadAll } = options

  const currentMode = ref<G1RenderMode>('html')
  const isOoAvailable = ref(false)
  /** 当前 sheet 的 onlyoffice-config 是否已拉取成功（"拉取成功"状态展示用） */
  const ooConfigReady = ref(false)
  /** config 拉取中 */
  const fetchingConfig = ref(false)
  const checking = ref(false)

  const modeOptions = computed(() =>
    dualModeHtmlOoOptions({ onlineDisabled: !isOoAvailable.value }),
  )

  function resolveOoSheetName(): string {
    const code = currentSheet.value
    if (!code || code === '底稿目录') return sheetName?.value || 'G1-1'
    return resolveG1SheetLabel(code, availableSheets.value, sheetName?.value)
  }

  function loadPersistedMode(): G1RenderMode | null {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') return saved
    } catch {
      /* ignore */
    }
    return null
  }

  function persistMode(mode: G1RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch {
      /* ignore */
    }
  }

  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      // 兼容多层信封（与 GtOnlyOfficeSheet / D4 / K11 一致）
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
   * 切换模式。
   * - 切到 onlyoffice：health 通过后，先 GET 该 sheet 的 onlyoffice-config，
   *   **拉取成功（config 非空）才真正切换**；失败则保持结构化视图（不全局禁用 OO 服务）。
   * - 切回 html：清 config + reloadAll 刷新数据。
   */
  async function switchMode(target: G1RenderMode): Promise<void> {
    if (target === currentMode.value) return

    if (target === 'onlyoffice') {
      if (!isOoAvailable.value) return
      const sn = resolveOoSheetName()
      if (!sn) return
      fetchingConfig.value = true
      ooConfigReady.value = false
      try {
        const params: Record<string, any> = {}
        if (projectId?.value) params.project_id = projectId.value
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { params, _silent: true } as any,
        )
        const payload = res.data?.data ?? res.data
        if (!payload) throw new Error('empty onlyoffice-config')
        // config 拉取成功 → 允许进入在线编辑
        ooConfigReady.value = true
        currentMode.value = 'onlyoffice'
        persistMode('onlyoffice')
      } catch {
        // 该 sheet 拉取失败：不切、保持结构化视图（不全局禁用 isOoAvailable）
        ooConfigReady.value = false
        currentMode.value = 'html'
        persistMode('html')
      } finally {
        fetchingConfig.value = false
      }
    } else {
      currentMode.value = 'html'
      ooConfigReady.value = false
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as G1RenderMode)
  }

  /** OO 组件 fallback：强制回结构化视图 */
  function onOoFallback(): void {
    void switchMode('html')
  }

  onMounted(() => {
    const saved = loadPersistedMode()
    // 先以结构化视图起页，待健康检查后再决定是否恢复在线编辑（避免 OO 死页）
    currentMode.value = 'html'
    void checkOOHealth().then((healthy) => {
      if (healthy && saved === 'onlyoffice') {
        // 恢复偏好前须重新预拉 config（拉取成功才切，见 switchMode）
        void switchMode('onlyoffice')
      } else if (!healthy) {
        persistMode('html')
      }
    })
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfigReady,
    fetchingConfig,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOOHealth,
    resolveOoSheetName,
    onOoFallback,
  }
}

export default useG1DualMode
