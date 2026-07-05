/** 监盘 bundle 双模式 — localStorage 前缀独立于 spe/val */
import { ref, onMounted, type Ref } from 'vue'

export type F2StRenderMode = 'html' | 'onlyoffice'
const STORAGE_PREFIX = 'f2-st-dual-mode:'

export function useF2StocktakeDualMode(options: {
  wpId: Ref<string>
  reloadAll?: () => Promise<void>
}) {
  const { wpId, reloadAll } = options
  const currentMode = ref<F2StRenderMode>('html')
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

  async function switchMode(target: F2StRenderMode): Promise<void> {
    if (target === 'onlyoffice' && !isOoAvailable.value) return
    currentMode.value = target
    try { localStorage.setItem(STORAGE_PREFIX + wpId.value, target) } catch { /* ignore */ }
    if (target === 'html' && reloadAll) await reloadAll()
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as F2StRenderMode)
  }

  onMounted(() => {
    try {
      const s = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (s === 'html' || s === 'onlyoffice') currentMode.value = s
    } catch { /* ignore */ }
    void checkOOHealth()
  })

  return { currentMode, isOoAvailable, modeOptions, onModeChange, switchMode }
}
