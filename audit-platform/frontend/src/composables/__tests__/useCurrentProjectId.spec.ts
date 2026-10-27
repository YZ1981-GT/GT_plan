/**
 * useCurrentProjectId — 取值上下文的显式条件（acnr-foundation-defect-closure 段四审计 F4-03 / F4-16）
 *
 * - 无注入上下文、无活动 Pinia（普通函数 / 纯函数单测）：返回空串，且不触碰 useRoute / useProjectStore；
 * - 有注入上下文：路由 projectId 优先，其次项目 store；
 * - 上下文存在时 useRoute 抛出的错误照常抛出（不吞异常）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createApp } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

const h = vi.hoisted(() => ({
  useRoute: vi.fn(),
  useProjectStore: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: h.useRoute }))
vi.mock('@/stores/project', () => ({ useProjectStore: h.useProjectStore }))

import { useCurrentProjectId } from '@/composables/useCurrentProjectId'

beforeEach(() => {
  h.useRoute.mockReset()
  h.useProjectStore.mockReset()
  // 每例从「无活动 Pinia」开始
  setActivePinia(undefined as any)
})

describe('useCurrentProjectId 取值上下文', () => {
  it('无注入上下文且无活动 Pinia：返回空串，不调用 useRoute / useProjectStore', () => {
    const pid = useCurrentProjectId()
    expect(pid.value).toBe('')
    expect(h.useRoute).not.toHaveBeenCalled()
    expect(h.useProjectStore).not.toHaveBeenCalled()
  })

  it('有注入上下文：路由 projectId 优先于项目 store', () => {
    setActivePinia(createPinia())
    h.useRoute.mockReturnValue({ params: { projectId: 'p-route' } })
    h.useProjectStore.mockReturnValue({ projectId: 'p-store' })
    const app = createApp({})
    const pid = app.runWithContext(() => useCurrentProjectId())
    expect(pid.value).toBe('p-route')
    expect(h.useRoute).toHaveBeenCalledTimes(1)
  })

  it('路由没有 projectId 时回退项目 store', () => {
    setActivePinia(createPinia())
    h.useRoute.mockReturnValue({ params: {} })
    h.useProjectStore.mockReturnValue({ projectId: 'p-store' })
    const app = createApp({})
    const pid = app.runWithContext(() => useCurrentProjectId())
    expect(pid.value).toBe('p-store')
  })

  it('无活动 Pinia 但有注入上下文：只读路由，不调用 useProjectStore', () => {
    h.useRoute.mockReturnValue({ params: { projectId: 'p-route' } })
    const app = createApp({})
    const pid = app.runWithContext(() => useCurrentProjectId())
    expect(pid.value).toBe('p-route')
    expect(h.useProjectStore).not.toHaveBeenCalled()
  })

  it('上下文存在时 useRoute 的异常照常抛出（不吞异常）', () => {
    h.useRoute.mockImplementation(() => {
      throw new Error('route-boom')
    })
    const app = createApp({})
    expect(() => app.runWithContext(() => useCurrentProjectId())).toThrow('route-boom')
  })
})
