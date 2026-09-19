/**
 * useD1EventBus — B50/C2 联动监听（从 monolith 恢复）
 */
import { onBeforeUnmount, type Ref } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export function useD1EventBus(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  saveDebouncedText: (item: ChecklistItem) => void,
) {
  const listeners: Array<{ event: string; handler: (e: Event) => void }> = []

  function setLocal(itemId: string, conclusion: string | null, remark: string | null = null): void {
    allResponses.value.set(itemId, { item_id: itemId, conclusion, remark })
  }

  function onRiskAssessed(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail?.level) return
    const hint = `[B50] ${detail.description || detail.level}`
    setLocal('D1-proc-control-hint', null, hint)
    saveDebouncedText({ item_id: 'D1-proc-control-hint', conclusion: null, remark: hint })
  }

  function onControlTestConcluded(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || detail.wpCode !== 'C2') return
    const hint = detail.conclusion || '控制测试已完成'
    setLocal('D1-proc-control-hint', null, hint)
    saveDebouncedText({ item_id: 'D1-proc-control-hint', conclusion: null, remark: hint })
  }

  function register(): void {
    const riskHandler = (e: Event) => onRiskAssessed(e)
    const controlHandler = (e: Event) => onControlTestConcluded(e)
    window.addEventListener('risk:assessed', riskHandler)
    window.addEventListener('control:test-concluded', controlHandler)
    listeners.push(
      { event: 'risk:assessed', handler: riskHandler },
      { event: 'control:test-concluded', handler: controlHandler },
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

export default useD1EventBus
