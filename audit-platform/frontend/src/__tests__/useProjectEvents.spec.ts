/**
 * useProjectEvents composable 单测
 * 验证事件订阅/过滤/分发逻辑
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

// Mock lifecycle hooks
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  let mountedCb: Function | null = null
  let unmountedCb: Function | null = null
  return {
    ...actual as any,
    onMounted: (fn: Function) => { mountedCb = fn; fn() },
    onUnmounted: (fn: Function) => { unmountedCb = fn },
  }
})

// Mock eventBus
const listeners: Record<string, Function[]> = {}
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on(event: string, handler: Function) {
      if (!listeners[event]) listeners[event] = []
      listeners[event].push(handler)
    },
    off(event: string, handler: Function) {
      if (listeners[event]) {
        listeners[event] = listeners[event].filter(h => h !== handler)
      }
    },
    emit(event: string, payload: any) {
      (listeners[event] || []).forEach(h => h(payload))
    },
  },
}))

import { useProjectEvents } from '@/composables/useProjectEvents'
import { eventBus } from '@/utils/eventBus'

describe('useProjectEvents', () => {
  beforeEach(() => {
    // Clear all listeners
    Object.keys(listeners).forEach(k => { listeners[k] = [] })
  })

  it('subscribes to sse:sync-event on mount', () => {
    const projectId = ref('proj-001')
    useProjectEvents(projectId)
    expect(listeners['sse:sync-event']?.length).toBeGreaterThan(0)
  })

  it('filters events by projectId', () => {
    const projectId = ref('proj-001')
    const { lastEvent } = useProjectEvents(projectId)

    // Emit event for different project
    eventBus.emit('sse:sync-event', {
      event_type: 'DATASET_ACTIVATED',
      project_id: 'proj-999',
    })
    expect(lastEvent.value).toBeNull()

    // Emit event for our project
    eventBus.emit('sse:sync-event', {
      event_type: 'DATASET_ACTIVATED',
      project_id: 'proj-001',
      year: 2024,
    })
    expect(lastEvent.value).not.toBeNull()
    expect(lastEvent.value?.event_type).toBe('DATASET_ACTIVATED')
  })

  it('dispatches DATASET_ACTIVATED to typed handler', () => {
    const projectId = ref('proj-001')
    const handler = vi.fn()
    const { onDatasetActivated } = useProjectEvents(projectId)
    onDatasetActivated(handler)

    eventBus.emit('sse:sync-event', {
      event_type: 'DATASET_ACTIVATED',
      project_id: 'proj-001',
      year: 2024,
    })
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      event_type: 'DATASET_ACTIVATED',
      project_id: 'proj-001',
      year: 2024,
    }))
  })

  it('dispatches DATASET_ROLLED_BACK to typed handler', () => {
    const projectId = ref('proj-001')
    const handler = vi.fn()
    const { onDatasetRolledBack } = useProjectEvents(projectId)
    onDatasetRolledBack(handler)

    eventBus.emit('sse:sync-event', {
      event_type: 'DATASET_ROLLED_BACK',
      project_id: 'proj-001',
    })
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('onAnyEvent receives all project events', () => {
    const projectId = ref('proj-001')
    const handler = vi.fn()
    const { onAnyEvent } = useProjectEvents(projectId)
    onAnyEvent(handler)

    eventBus.emit('sse:sync-event', {
      event_type: 'SOME_CUSTOM_EVENT',
      project_id: 'proj-001',
    })
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('updates lastEvent ref on each matching event', () => {
    const projectId = ref('proj-001')
    const { lastEvent } = useProjectEvents(projectId)

    eventBus.emit('sse:sync-event', {
      event_type: 'EVENT_A',
      project_id: 'proj-001',
    })
    expect(lastEvent.value?.event_type).toBe('EVENT_A')

    eventBus.emit('sse:sync-event', {
      event_type: 'EVENT_B',
      project_id: 'proj-001',
    })
    expect(lastEvent.value?.event_type).toBe('EVENT_B')
  })
})
