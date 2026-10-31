/**
 * 取锁 / 强制接管先等窗口编号认领（spec workpaper-multi-window-lock-gaps R1.3）。
 *
 * 「复制标签页」的编号认领完才换成本页自己的；认领前就取锁，会用原标签页的编号把锁续成自己的，
 * 两个窗口又成了一个。认领期间切了底稿：不再按旧底稿取锁。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return { ...actual, onMounted: (fn: () => unknown) => fn(), onUnmounted: vi.fn() }
})

const { post, claim } = vi.hoisted(() => ({ post: vi.fn(), claim: { release: () => {}, promise: Promise.resolve('w') } }))
vi.mock('@/services/apiProxy', () => ({ api: { post: (...a: unknown[]) => post(...a), delete: vi.fn(), patch: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn() } }))
vi.mock('@/utils/clientInstance', () => ({ claimClientInstanceId: () => claim.promise }))

import { useEditingLock } from '@/composables/useEditingLock'

function pendingClaim() {
  claim.promise = new Promise<string>((resolve) => { claim.release = () => resolve('claimed') })
}

const flush = async () => { for (let i = 0; i < 5; i++) await Promise.resolve() }

beforeEach(() => {
  post.mockReset().mockResolvedValue({ acquired: true })
  pendingClaim()
})

describe('useEditingLock：先认领窗口编号', () => {
  it('认领完成前不发取锁请求，完成后才发', async () => {
    useEditingLock({ resourceId: ref('wp-1'), resourceType: 'workpaper' })
    await flush()
    expect(post).not.toHaveBeenCalled()

    claim.release()
    await flush()
    expect(post).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-1', undefined, { _silent: true })
  })

  it('强制接管同样先等认领', async () => {
    const lock = useEditingLock({ resourceId: ref('wp-2'), resourceType: 'workpaper', autoAcquire: false })
    const forcing = lock.forceAcquire()
    await flush()
    expect(post).not.toHaveBeenCalled()
    claim.release()
    await forcing
    expect(post).toHaveBeenCalledWith('/api/editing-locks/workpaper/wp-2/force', undefined, { _silent: true })
  })

  it('认领期间切了底稿：不按旧底稿取锁', async () => {
    const id = ref('wp-old')
    const lock = useEditingLock({ resourceId: id, resourceType: 'workpaper', autoAcquire: false })
    const acquiring = lock.acquire()
    id.value = 'wp-new'
    await nextTick()
    claim.release()
    await acquiring
    await flush()
    expect(post.mock.calls.map((c) => c[0])).not.toContain('/api/editing-locks/workpaper/wp-old')
  })
})
