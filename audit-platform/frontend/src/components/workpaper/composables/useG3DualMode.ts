/**
 * useG3DualMode — G3 应收股利 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 8.2 / Req 14.1~14.4
 * 模式状态(html/onlyoffice) + 健康检查 + 切换 + localStorage 持久化(per wpId)
 */
import { ref, computed, onMounted, type Ref } from 'vue'

export type G3RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g3-dual-mode:'

export interface UseG3DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}

export function useG3DualMode(options: UseG3DualModeOptions) {
  const { wpId, reloadAll } = options

  const currentMode = ref<G3RenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

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

  function persistMode(mode: G3RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
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
      const healthy = result.data?.healthy ?? result.healthy ?? false
      isOoAvailable.value = healthy
      return healthy
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: G3RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) {
      // 强制回退到 html（防止 segmented 视觉状态不同步）
      currentMode.value = 'html'
      return
    }

    if (target === 'onlyoffice') {
      currentMode.value = 'onlyoffice'
      persistMode('onlyoffice')
    } else {
      currentMode.value = 'html'
      ooConfig.value = null
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as G3RenderMode)
  }

  function onOoFallback(): void {
    currentMode.value = 'html'
    isOoAvailable.value = false
    persistMode('html')
  }

  onMounted(() => {
    // 先检查 OO 健康状态，再恢复持久化模式（避免 race condition：恢复 OO→渲染→才发现不可用）
    void checkOOHealth().then((healthy) => {
      if (healthy) {
        loadPersistedMode()
      } else {
        // OO 不可用，强制 html 不管 localStorage 存什么
        currentMode.value = 'html'
        persistMode('html')
      }
    })
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    onOoFallback,
    checkOOHealth,
  }
}
