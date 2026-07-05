/**
 * useD3EventBus — B50 风险联动（D3A 程序表提示）
 */
import { onBeforeUnmount, type Ref } from 'vue'
import type { ChecklistResponse } from './useD3FormData'

export function useD3EventBus(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
) {
  const listeners: Array<{ event: string; handler: (e: Event) => void }> = []

  function onRiskUpdated(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail?.level) return
    const hint = `[B50] 风险等级 ${detail.level}${detail.description ? '：' + detail.description : ''}`
    allResponses.value.set('D3-proc-risk-hint', { item_id: 'D3-proc-risk-hint', conclusion: null, remark: hint })
    debouncedSave('D3-proc-risk-hint', { remark: hint })
  }

  function register(): void {
    const handler = (e: Event) => onRiskUpdated(e)
    window.addEventListener('risk:updated', handler)
    window.addEventListener('risk:assessed', handler)
    listeners.push(
      { event: 'risk:updated', handler },
      { event: 'risk:assessed', handler },
    )
  }

  function unregister(): void {
    for (const { event, handler } of listeners) {
      window.removeEventListener(event, handler)
    }
    listeners.length = 0
  }

  register()
  onBeforeUnmount(unregister)

  return { unregister }
}

export default useD3EventBus
