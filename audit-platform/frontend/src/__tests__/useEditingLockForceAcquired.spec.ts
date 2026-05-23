/**
 * useEditingLock — force_acquired SSE 事件处理测试
 * Validates: workpaper-collaboration-presence F3 Task 3.4
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick, defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { eventBus } from '@/utils/eventBus'

// Mock apiProxy
const mockPost = vi.fn().mockResolvedValue({ acquired: true, locked_by_name: 'admin' })
const mockPatch = vi.fn().mockResolvedValue({})
const mockDelete = vi.fn().mockResolvedValue({})

vi.mock('@/services/apiProxy', () => ({
  api: {
    post: (...args: any[]) => mockPost(...args),
    patch: (...args: any[]) => mockPatch(...args),
    delete: (...args: any[]) => mockDelete(...args),
  },
}))

import { useEditingLock } from '@/composables/useEditingLock'

/** Helper: mount composable inside a real component to trigger lifecycle hooks */
function mountComposable(fn: () => any) {
  let result: any
  const Comp = defineComponent({
    setup() {
      result = fn()
      return () => h('div')
    },
  })
  const wrapper = mount(Comp)
  return { result, wrapper }
}

describe('useEditingLock — force_acquired SSE handling', () => {
  beforeEach(() => {
    mockPost.mockResolvedValue({ acquired: true, locked_by_name: 'admin' })
    mockPatch.mockResolvedValue({})
    mockDelete.mockResolvedValue({})
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    eventBus.all.clear()
  })

  it('sets isMine to false when receiving force_acquired event for our wp', async () => {
    const resourceId = ref('wp-100')
    const { result } = mountComposable(() =>
      useEditingLock({ resourceId, resourceType: 'workpaper' })
    )

    await nextTick()
    await nextTick()
    expect(result.isMine.value).toBe(true)

    // Simulate SSE event: someone else force-acquired our lock
    eventBus.emit('sse:sync-event', {
      event_type: 'editing_lock.force_acquired',
      wp_id: 'wp-100',
      new_holder_id: 'user-other',
      new_holder_name: '李四',
      previous_holder_id: 'some-id',
    })

    await nextTick()
    expect(result.isMine.value).toBe(false)
  })

  it('emits editing-lock:taken-over event on force_acquired', async () => {
    const resourceId = ref('wp-200')
    mountComposable(() =>
      useEditingLock({ resourceId, resourceType: 'workpaper' })
    )

    await nextTick()
    await nextTick()

    const takenOverHandler = vi.fn()
    eventBus.on('editing-lock:taken-over', takenOverHandler)

    eventBus.emit('sse:sync-event', {
      event_type: 'editing_lock.force_acquired',
      wp_id: 'wp-200',
      new_holder_id: 'user-other',
      new_holder_name: '王五',
      previous_holder_id: 'me',
    })

    await nextTick()
    expect(takenOverHandler).toHaveBeenCalledWith(
      expect.objectContaining({
        wp_id: 'wp-200',
        new_holder_name: '王五',
      })
    )
  })

  it('ignores force_acquired event for different wp_id', async () => {
    const resourceId = ref('wp-300')
    const { result } = mountComposable(() =>
      useEditingLock({ resourceId, resourceType: 'workpaper' })
    )

    await nextTick()
    await nextTick()
    expect(result.isMine.value).toBe(true)

    // Event for a different workpaper
    eventBus.emit('sse:sync-event', {
      event_type: 'editing_lock.force_acquired',
      wp_id: 'wp-999',
      new_holder_id: 'user-other',
      new_holder_name: '赵六',
      previous_holder_id: 'someone',
    })

    await nextTick()
    expect(result.isMine.value).toBe(true) // unchanged
  })

  it('does not react to force_acquired when not holding lock', async () => {
    // Simulate 409 conflict on acquire
    mockPost.mockRejectedValueOnce({
      response: { status: 409, data: { detail: { locked_by: 'u1', locked_by_name: '张三', acquired_at: '2026-01-01' } } },
    })

    const resourceId = ref('wp-400')
    const { result } = mountComposable(() =>
      useEditingLock({ resourceId, resourceType: 'workpaper' })
    )

    await nextTick()
    await nextTick()
    expect(result.isMine.value).toBe(false)

    const takenOverHandler = vi.fn()
    eventBus.on('editing-lock:taken-over', takenOverHandler)

    eventBus.emit('sse:sync-event', {
      event_type: 'editing_lock.force_acquired',
      wp_id: 'wp-400',
      new_holder_id: 'user-other',
      new_holder_name: '新人',
      previous_holder_id: 'u1',
    })

    await nextTick()
    expect(takenOverHandler).not.toHaveBeenCalled()
  })
})
