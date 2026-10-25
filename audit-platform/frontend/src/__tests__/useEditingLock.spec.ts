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

  // ── 切换资源时必须释放**旧** id（2026-09-28 Playwright 实测缺陷）──────────
  //
  // 原实现 watch 里写 `await release()`，而 release() 读 options.resourceId.value
  // —— watcher 执行时该值已是 newId ⇒ DELETE 打在**新**资源上：
  //   · 旧底稿的锁从不释放，要等心跳超时，期间他人看到「正在被 admin 编辑」
  //   · 新资源上多一次无意义 DELETE（真机实测返回 404）
  // 实测证据：从 K8 跳 L4 时网络日志为
  //   DELETE /api/editing-locks/workpaper/{L4} => 404   ← 本该是 {K8}
  //   POST   /api/editing-locks/workpaper/{L4} => 200
  it('releases the OLD resource id when resourceId changes (not the new one)', async () => {
    mockPost.mockResolvedValue({ acquired: true, locked_by_name: 'admin' })
    mockDelete.mockResolvedValue({})
    const resourceId = ref('wp-old')
    useEditingLock({ resourceId, resourceType: 'workpaper' })

    await vi.advanceTimersByTimeAsync(0)
    expect(mockPost).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-old')
    mockDelete.mockClear()
    mockPost.mockClear()

    resourceId.value = 'wp-new'
    await vi.advanceTimersByTimeAsync(0)

    // 释放的必须是旧 id
    expect(mockDelete).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-old')
    // 且绝不能把 DELETE 发到新 id 上（原缺陷形态）
    expect(mockDelete).not.toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-new')
    // 新 id 只应被 acquire
    expect(mockPost).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-new')
  })

  it('release() 释放的是持有的那把锁（卸载/关页路径）', async () => {
    mockPost.mockResolvedValue({ acquired: true, locked_by_name: 'admin' })
    mockDelete.mockResolvedValue({})
    const resourceId = ref('wp-cur')
    const { release } = useEditingLock({ resourceId, resourceType: 'workpaper' })

    await vi.advanceTimersByTimeAsync(0)
    mockDelete.mockClear()
    await release()
    expect(mockDelete).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-cur')
  })

  // 🔴 真实缺陷路径：resourceId 先变、release 后调（= 组件卸载路径）
  //
  // 首版修复只给 watch 传了 oldId，真机仍复现 —— 因为 WorkpaperEditor 在切底稿时是
  // **卸载重建**，watch 根本不触发，走的是 onUnmounted 里的无参 release()。
  // 而 resourceId 通常是 computed(() => route.params.wpId)，Vue Router 先更新参数、
  // 后卸载组件 ⇒ 无参 release 读到的已是新 id。
  // 正解 = 按「实际持有的 id」释放。本条模拟该时序：先改 resourceId，再 release。
  it('resourceId 已变但尚未重新获取时，release 仍释放原持有的 id（卸载时序）', async () => {
    mockPost.mockResolvedValue({ acquired: true, locked_by_name: 'admin' })
    mockDelete.mockResolvedValue({})
    const resourceId = ref('wp-held')
    const { release } = useEditingLock({ resourceId, resourceType: 'workpaper', autoAcquire: true })

    await vi.advanceTimersByTimeAsync(0)
    expect(mockPost).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-held')
    mockDelete.mockClear()

    // 模拟路由参数已切到新底稿（组件还没重新 acquire）
    // 注：此处**不**等待 watch 的异步链跑完，正是要复现「先变值、后 release」
    resourceId.value = 'wp-routed-away'
    await release()

    expect(mockDelete).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-held')
    expect(mockDelete).not.toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-routed-away')
  })

  // 心跳/释放都以 heldId 为准 ⇒ acquire 没成功（锁在别人手里）时不得有任何后续请求。
  // 原实现读 options.resourceId.value，只靠 isMine 兜；heldId 让「没持有就没得放」
  // 成为结构性保证而非条件判断。
  it('acquire 冲突（409）时不发 release / heartbeat（从未持有 ⇒ heldId 为空）', async () => {
    mockPost.mockRejectedValue({
      response: { status: 409, data: { detail: { locked_by_name: '张三' } } },
    })
    mockDelete.mockResolvedValue({})
    mockPatch.mockResolvedValue({})
    const resourceId = ref('wp-conflict')
    const { isMine, release } = useEditingLock({
      resourceId, resourceType: 'workpaper', heartbeatMs: 1000,
    })

    await vi.advanceTimersByTimeAsync(0)
    expect(isMine.value).toBe(false)

    await release()
    await vi.advanceTimersByTimeAsync(3000)

    expect(mockDelete).not.toHaveBeenCalled()
    expect(mockPatch).not.toHaveBeenCalled()
  })

  it('未持有锁时 release 不发请求（isMine=false / 从未 acquire）', async () => {
    const resourceId = ref('wp-none')
    const { release } = useEditingLock({ resourceId, resourceType: 'workpaper', autoAcquire: false })

    await vi.advanceTimersByTimeAsync(0)
    await release()
    expect(mockDelete).not.toHaveBeenCalled()
  })
})
