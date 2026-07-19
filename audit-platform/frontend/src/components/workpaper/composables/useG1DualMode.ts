/**
 * useG1DualMode — G1 HTML ↔ OnlyOffice 双模式（对齐 D4 useD4EntryDualMode / useWorkpaperEntryDualMode）
 *
 * - 健康检查后才允许切在线编辑；不可用时强制回结构化视图
 * - resolveOoSheetName：编码 → 真实 sheet_name（供 GtOnlyOfficeSheet）
 * - fallback：OO 初始化失败时由入口切回 html
 */
import { ref, computed, onMounted, type Ref } from 'vue'
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
  reloadAll?: () => Promise<void>
}

export function useG1DualMode(options: UseG1DualModeOptions) {
  const { wpId, currentSheet, availableSheets, sheetName, reloadAll } = options

  const currentMode = ref<G1RenderMode>('html')
  const isOoAvailable = ref(false)
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
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) {
        isOoAvailable.value = false
        return false
      }
      const result = await response.json()
      // 兼容多层信封（与 GtOnlyOfficeSheet / D4 一致）
      const healthy =
        result.data?.data?.healthy ?? result.data?.healthy ?? result.healthy ?? false
      isOoAvailable.value = !!healthy
      return isOoAvailable.value
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: G1RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice') {
      currentMode.value = 'onlyoffice'
      persistMode('onlyoffice')
    } else {
      currentMode.value = 'html'
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
        currentMode.value = 'onlyoffice'
      } else if (!healthy) {
        persistMode('html')
      }
    })
  })

  return {
    currentMode,
    isOoAvailable,
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
