/**
 * useWorkpaperEntryDualMode — 循环底稿入口 HTML ↔ OnlyOffice 双模式（D4/D5/D6/D7 共用）
 *
 * 各 cycle 通过 resolveOoSheetName 注入 sheet 名解析逻辑。
 */
import { ref, onMounted, type Ref } from 'vue'

export type WorkpaperRenderMode = 'html' | 'onlyoffice'

export function useWorkpaperEntryDualMode(options: {
  reloadAllResponses: () => Promise<void>
  resolveOoSheetName: () => string
}) {
  const { reloadAllResponses, resolveOoSheetName } = options

  const mode = ref<WorkpaperRenderMode>('html')
  const ooAvailable = ref(false)
  const checking = ref(false)

  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) {
        ooAvailable.value = false
        return false
      }
      const result = await response.json()
      const healthy = result.data?.healthy ?? result.healthy ?? false
      ooAvailable.value = !!healthy
      return ooAvailable.value
    } catch {
      ooAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: WorkpaperRenderMode): Promise<void> {
    if (target === mode.value) return
    if (target === 'onlyoffice' && !ooAvailable.value) return
    if (target === 'onlyoffice') {
      mode.value = 'onlyoffice'
    } else {
      mode.value = 'html'
      await reloadAllResponses()
    }
  }

  onMounted(() => { void checkOOHealth() })

  return {
    mode,
    ooAvailable,
    checking,
    switchMode,
    checkOOHealth,
    resolveOoSheetName,
  }
}

export default useWorkpaperEntryDualMode
