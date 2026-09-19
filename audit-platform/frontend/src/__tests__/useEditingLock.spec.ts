/**
 * useEditingLock composable 单测
 * 验证锁获取/释放/心跳/降级逻辑
 *
 * Feature: editing-lock-v1-v2-consolidation, Property 11
 * 阶段 3 后 workpaper 统一走 v2 通用端点，无 v1 回退分支。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

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

  it('acquires lock on mount for workpaper type via v2 endpoint', async () => {
    mockPost.mockResolvedValue({ acquired: true, locked_by_name: 'admin' })
    const resourceId = ref('wp-001')
    const { locked, isMine } = useEditingLock({ resourceId, resourceType: 'workpaper' })

    await vi.advanceTimersByTimeAsync(0)
    expect(mockPost).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-001')
    expect(locked.value).toBe(true)
    expect(isMine.value).toBe(true)
  })

  it('handles 409 conflict when another user holds lock', async () => {
    mockPost.mockRejectedValue({
      response: { status: 409, data: { detail: { locked_by_name: '张三' } } },
    })
    const resourceId = ref('wp-002')
    const { locked, isMine, lockedBy } = useEditingLock({ resourceId, resourceType: 'workpaper' })

    await vi.advanceTimersByTimeAsync(0)
    expect(locked.value).toBe(true)
    expect(isMine.value).toBe(false)
    expect(lockedBy.value).toBe('张三')
  })

  it('releases lock via v2 endpoint on explicit release call', async () => {
    mockPost.mockResolvedValue({ acquired: true })
    mockDelete.mockResolvedValue({})
    const resourceId = ref('wp-003')
    const { isMine, release } = useEditingLock({ resourceId, resourceType: 'workpaper' })

    await vi.advanceTimersByTimeAsync(0)
    expect(isMine.value).toBe(true)

    await release()
    expect(mockDelete).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-003')
  })

  it('sends heartbeat via v2 endpoint at configured interval', async () => {
    mockPost.mockResolvedValue({ acquired: true })
    mockPatch.mockResolvedValue({})
    const resourceId = ref('wp-004')
    useEditingLock({ resourceId, resourceType: 'workpaper', heartbeatMs: 1000 })

    // Flush microtasks so acquire() resolves and startHeartbeat() is called
    await vi.advanceTimersByTimeAsync(0)
    mockPatch.mockClear()
    // Advance past one heartbeat interval
    await vi.advanceTimersByTimeAsync(1000)
    expect(mockPatch).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-004/heartbeat')
  })

  it('uses generic lock endpoint for non-workpaper resources', async () => {
    mockPost.mockResolvedValue({ acquired: true, locked_by_name: null })
    const resourceId = ref('report-001')
    const { locked, isMine } = useEditingLock({ resourceId, resourceType: 'other' })

    await vi.advanceTimersByTimeAsync(0)
    expect(mockPost).toHaveBeenCalledWith('/api/editing-locks/other/report-001')
    expect(locked.value).toBe(true)
    expect(isMine.value).toBe(true)
  })

  it('does not auto-acquire when autoAcquire is false', async () => {
    const resourceId = ref('wp-005')
    const { locked } = useEditingLock({ resourceId, resourceType: 'workpaper', autoAcquire: false })

    await vi.advanceTimersByTimeAsync(0)
    expect(mockPost).not.toHaveBeenCalled()
    expect(locked.value).toBe(false)
  })

  it('force acquires via v2 endpoint', async () => {
    mockPost.mockResolvedValue({ acquired: true, lock_id: 'lock-1' })
    const resourceId = ref('wp-006')
    const { forceAcquire } = useEditingLock({ resourceId, resourceType: 'workpaper', autoAcquire: false })

    await vi.advanceTimersByTimeAsync(0)
    await forceAcquire()
    expect(mockPost).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-006/force')
  })
})
