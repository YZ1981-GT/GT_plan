/**
 * useEditingLock composable 单测
 * 验证锁获取/释放/心跳/降级逻辑
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

// Mock lifecycle hooks (not in component context)
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual as any,
    onMounted: (fn: Function) => fn(),
    onUnmounted: vi.fn(),
  }
})

const mockPost = vi.fn()
const mockDelete = vi.fn()
const mockPatch = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    post: (...args: any[]) => mockPost(...args),
    delete: (...args: any[]) => mockDelete(...args),
    patch: (...args: any[]) => mockPatch(...args),
  },
}))

import { useEditingLock } from '@/composables/useEditingLock'

describe('useEditingLock', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPost.mockReset()
    mockDelete.mockReset()
    mockPatch.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('acquires lock on mount for workpaper type', async () => {
    mockPost.mockResolvedValue({ acquired: true, locked_by_name: 'admin' })
    const resourceId = ref('wp-001')
    const { locked, isMine } = useEditingLock({ resourceId, resourceType: 'workpaper' })

    await nextTick()
    expect(mockPost).toHaveBeenCalledWith('/api/workpapers/wp-001/editing-lock')
    expect(locked.value).toBe(true)
    expect(isMine.value).toBe(true)
  })

  it('handles 409 conflict when another user holds lock', async () => {
    mockPost.mockRejectedValue({
      response: { status: 409, data: { detail: { locked_by_name: '张三' } } },
    })
    const resourceId = ref('wp-002')
    const { locked, isMine, lockedBy } = useEditingLock({ resourceId, resourceType: 'workpaper' })

    await nextTick()
    expect(locked.value).toBe(true)
    expect(isMine.value).toBe(false)
    expect(lockedBy.value).toBe('张三')
  })

  it('releases lock on explicit release call', async () => {
    mockPost.mockResolvedValue({ acquired: true })
    mockDelete.mockResolvedValue({})
    const resourceId = ref('wp-003')
    const { isMine, release } = useEditingLock({ resourceId, resourceType: 'workpaper' })

    await nextTick()
    expect(isMine.value).toBe(true)

    await release()
    expect(mockDelete).toHaveBeenCalledWith('/api/workpapers/wp-003/editing-lock')
  })

  it('sends heartbeat at configured interval', async () => {
    mockPost.mockResolvedValue({ acquired: true })
    mockPatch.mockResolvedValue({})
    const resourceId = ref('wp-004')
    useEditingLock({ resourceId, resourceType: 'workpaper', heartbeatMs: 1000 })

    // Flush microtasks so acquire() resolves and startHeartbeat() is called
    await vi.advanceTimersByTimeAsync(0)
    mockPatch.mockClear()
    // Advance past one heartbeat interval
    await vi.advanceTimersByTimeAsync(1000)
    expect(mockPatch).toHaveBeenCalledWith('/api/workpapers/wp-004/editing-lock/heartbeat')
  })

  it('degrades to local-only for non-workpaper resources', async () => {
    const resourceId = ref('report-001')
    const { locked, isMine } = useEditingLock({ resourceId, resourceType: 'other' })

    await nextTick()
    expect(mockPost).not.toHaveBeenCalled()
    expect(locked.value).toBe(true)
    expect(isMine.value).toBe(true)
  })

  it('does not auto-acquire when autoAcquire is false', async () => {
    const resourceId = ref('wp-005')
    const { locked } = useEditingLock({ resourceId, resourceType: 'workpaper', autoAcquire: false })

    await nextTick()
    expect(mockPost).not.toHaveBeenCalled()
    expect(locked.value).toBe(false)
  })
})
