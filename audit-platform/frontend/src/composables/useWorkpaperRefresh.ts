/**
 * useWorkpaperRefresh — 6 种数据刷新事件订阅（Sprint 2 Task 2.33）
 *
 * 锚定 requirements F4.3 + design D19
 *
 * 6 种触发场景：
 * - trial-balance:updated → prefill 重取
 * - adjustment:saved → AJE/RJE 重取
 * - project:updated → 表头重填
 * - confirmation:received → E1-3 标记已函证
 * - prior-year:imported → PREV 公式重取
 * - manual-refresh → 工具栏手动按钮
 */
import { onMounted, onUnmounted } from 'vue'
import { eventBus } from '@/utils/eventBus'

interface UseWorkpaperRefreshOptions {
  projectId: () => string
  wpId: () => string
  onRefresh: () => Promise<void> | void
  /** 防抖间隔（毫秒），默认 500 */
  debounceMs?: number
}

export function useWorkpaperRefresh(opts: UseWorkpaperRefreshOptions) {
  const debounceMs = opts.debounceMs ?? 500
  let timer: ReturnType<typeof setTimeout> | null = null
  const lastEventName = { value: '' as string }

  function triggerRefresh(eventName: string) {
    lastEventName.value = eventName
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      void opts.onRefresh()
    }, debounceMs)
  }

  function tbUpdated(payload: any) {
    const pid = opts.projectId()
    if (payload?.projectId && payload.projectId !== pid) return
    triggerRefresh('trial-balance:updated')
  }
  function adjustmentSaved(payload: any) {
    const pid = opts.projectId()
    if (payload?.projectId && payload.projectId !== pid) return
    triggerRefresh('adjustment:saved')
  }
  function projectUpdated(payload: any) {
    const pid = opts.projectId()
    if (payload?.projectId && payload.projectId !== pid) return
    triggerRefresh('project:updated')
  }
  function confirmationReceived(payload: any) {
    const pid = opts.projectId()
    if (payload?.projectId && payload.projectId !== pid) return
    triggerRefresh('confirmation:received')
  }
  function priorYearImported(payload: any) {
    const pid = opts.projectId()
    if (payload?.projectId && payload.projectId !== pid) return
    triggerRefresh('prior-year:imported')
  }
  function manualRefresh(payload: any) {
    const pid = opts.projectId()
    const wid = opts.wpId()
    if (payload?.projectId && payload.projectId !== pid) return
    if (payload?.wpId && payload.wpId !== wid) return
    triggerRefresh('manual-refresh')
  }

  onMounted(() => {
    eventBus.on('trial-balance:updated', tbUpdated)
    eventBus.on('adjustment:saved', adjustmentSaved)
    eventBus.on('project:updated', projectUpdated)
    eventBus.on('confirmation:received', confirmationReceived)
    eventBus.on('prior-year:imported', priorYearImported)
    eventBus.on('manual-refresh', manualRefresh)
  })

  onUnmounted(() => {
    eventBus.off('trial-balance:updated', tbUpdated)
    eventBus.off('adjustment:saved', adjustmentSaved)
    eventBus.off('project:updated', projectUpdated)
    eventBus.off('confirmation:received', confirmationReceived)
    eventBus.off('prior-year:imported', priorYearImported)
    eventBus.off('manual-refresh', manualRefresh)
    if (timer) clearTimeout(timer)
  })

  return {
    lastEventName,
    triggerRefresh,
  }
}
