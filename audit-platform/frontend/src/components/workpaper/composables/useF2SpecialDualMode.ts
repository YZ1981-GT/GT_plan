/** 比照 useF2ValuationDualMode */
import { ref, onMounted, type Ref } from 'vue'
import { runLegacyOnlyOfficeTransition } from '../sync/legacyPendingWriteBarrier'

export type F2SpeRenderMode = 'html' | 'onlyoffice'
const STORAGE_PREFIX = 'f2-spe-dual-mode:'

export function useF2SpecialDualMode(options: {
  wpId: Ref<string>
  reloadAll?: () => Promise<void>
}) {
  const { wpId, reloadAll } = options
  const currentMode = ref<F2SpeRenderMode>('html')
  const isOoAvailable = ref(false)
  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  async function checkOOHealth(): Promise<boolean> {
    try {
      const res = await fetch('/api/workpapers/onlyoffice/health')
      if (!res.ok) { isOoAvailable.value = false; return false }
      const j = await res.json()
      isOoAvailable.value = j.data?.healthy ?? j.healthy ?? false
      return isOoAvailable.value
    } catch {
      isOoAvailable.value = false
      return false
    }
  }

  async function switchMode(target: F2SpeRenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return
    if (target === 'onlyoffice') {
      await runLegacyOnlyOfficeTransition(async () => {
        currentMode.value = 'onlyoffice'
        try { localStorage.setItem(STORAGE_PREFIX + wpId.value, 'onlyoffice') } catch { /* ignore */ }
      })
      return
    }
    currentMode.value = 'html'
    try { localStorage.setItem(STORAGE_PREFIX + wpId.value, 'html') } catch { /* ignore */ }
    if (reloadAll) await reloadAll()
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as F2SpeRenderMode)
  }

  onMounted(() => {
    let saved: string | null = null
    try { saved = localStorage.getItem(STORAGE_PREFIX + wpId.value) } catch { /* ignore */ }
    // 保持 HTML，健康检查成功后经同一完整屏障恢复在线编辑。
    void checkOOHealth().then(async (healthy) => {
      if (healthy && saved === 'onlyoffice') await switchMode('onlyoffice')
      else if (!healthy) {
        currentMode.value = 'html'
        try { localStorage.setItem(STORAGE_PREFIX + wpId.value, 'html') } catch { /* ignore */ }
      }
    })
  })

  return { currentMode, isOoAvailable, modeOptions, switchMode, onModeChange, checkOOHealth }
}

export default useF2SpecialDualMode
