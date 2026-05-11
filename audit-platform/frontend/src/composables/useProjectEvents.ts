/**
 * useProjectEvents — 订阅项目级 SSE 事件（云协同）
 *
 * 基于 eventBus 的 'sse:sync-event' 事件，过滤当前 projectId 的事件，
 * 暴露 typed handler 供视图自动刷新。
 *
 * @example
 * ```ts
 * const { lastEvent, onDatasetActivated, onDatasetRolledBack } = useProjectEvents(projectId)
 * onDatasetActivated(() => { fetchData() })
 * ```
 */
import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'

export interface ProjectEvent {
  event_type: string
  project_id: string
  year?: number
  extra?: Record<string, any>
}

export function useProjectEvents(projectId: Ref<string>) {
  const lastEvent = ref<ProjectEvent | null>(null)

  // ─── Internal handler registry ──────────────────────────────────────────────

  type EventHandler = (payload: ProjectEvent) => void

  const activatedHandlers: EventHandler[] = []
  const rolledBackHandlers: EventHandler[] = []
  const genericHandlers: EventHandler[] = []

  function handler(payload: SyncEventPayload) {
    // Only process events for our project
    if (payload.project_id !== projectId.value) return

    const evt: ProjectEvent = {
      event_type: payload.event_type,
      project_id: payload.project_id,
      year: payload.year,
      extra: payload.extra,
    }
    lastEvent.value = evt

    // Dispatch to typed handlers
    if (payload.event_type === 'DATASET_ACTIVATED' || payload.event_type === 'LEDGER_DATASET_ACTIVATED') {
      activatedHandlers.forEach(h => h(evt))
    } else if (payload.event_type === 'DATASET_ROLLED_BACK' || payload.event_type === 'LEDGER_DATASET_ROLLED_BACK') {
      rolledBackHandlers.forEach(h => h(evt))
    }

    // Always call generic handlers
    genericHandlers.forEach(h => h(evt))
  }

  // ─── Public API ─────────────────────────────────────────────────────────────

  function onDatasetActivated(cb: EventHandler) {
    activatedHandlers.push(cb)
  }

  function onDatasetRolledBack(cb: EventHandler) {
    rolledBackHandlers.push(cb)
  }

  function onAnyEvent(cb: EventHandler) {
    genericHandlers.push(cb)
  }

  // ─── Lifecycle ──────────────────────────────────────────────────────────────

  onMounted(() => {
    eventBus.on('sse:sync-event', handler)
  })

  onUnmounted(() => {
    eventBus.off('sse:sync-event', handler)
    activatedHandlers.length = 0
    rolledBackHandlers.length = 0
    genericHandlers.length = 0
  })

  return {
    lastEvent,
    onDatasetActivated,
    onDatasetRolledBack,
    onAnyEvent,
  }
}
