/**
 * GtF2InventorySpecial — 订阅外部 substantive:adjudicated（1405 科目）
 */
import { ref, onBeforeUnmount } from 'vue'
import { is1405SubstantiveEvent } from './useF2SpeEventBus'

export function useF2SpeExternalAdjudicated(opts: {
  onRefresh: () => void | Promise<void>
}) {
  const dataUpdatedVisible = ref(false)
  let hideTimer: ReturnType<typeof setTimeout> | null = null

  function handler(e: Event): void {
    const d = (e as CustomEvent).detail as Record<string, unknown> | undefined
    if (!d || d.wpCode === 'F2-special') return
    if (!is1405SubstantiveEvent(d)) return
    void opts.onRefresh()
    dataUpdatedVisible.value = true
    if (hideTimer) clearTimeout(hideTimer)
    hideTimer = setTimeout(() => { dataUpdatedVisible.value = false }, 3000)
  }

  window.addEventListener('substantive:adjudicated', handler)
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', handler)
    if (hideTimer) clearTimeout(hideTimer)
  })

  return { dataUpdatedVisible }
}

export default useF2SpeExternalAdjudicated
