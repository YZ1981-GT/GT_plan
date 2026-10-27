/**
 * WorkflowProgress 的年度口径（spec post-push-residual-defect-closure R2.3）：
 * - 不传 year ⇒ 不带 year 请求，后端按项目审计年度取；
 * - year 为 null（宿主已知项目没填审计年度 / 还在解析）⇒ 不请求、不显示进度条（原先缺年度 422 后显示一条假进度）；
 * - 年度到达后（null → 数字）按新年度取。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import WorkflowProgress from '../WorkflowProgress.vue'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/projects/p1/trial-balance' }),
}))

const STATUS = { steps: {}, current_step: 3, next_action: null }

describe('WorkflowProgress 年度口径', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue(STATUS)
    localStorage.clear()
  })

  it('year 为 null：不请求、不显示进度条', async () => {
    const w = mount(WorkflowProgress, { props: { projectId: 'p1', year: null } })
    await flushPromises()
    expect(get).not.toHaveBeenCalled()
    expect(w.find('.workflow-progress').exists()).toBe(false)
  })

  it('不传 year：不带 year 请求（后端按项目审计年度取）', async () => {
    mount(WorkflowProgress, { props: { projectId: 'p1' } })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(1)
    expect(get.mock.calls[0][0]).toBe('/api/projects/p1/workflow-status')
    expect(get.mock.calls[0][1].params).toEqual({})
  })

  it('年度后到：null → 2025 时按 2025 取并显示', async () => {
    const w = mount(WorkflowProgress, { props: { projectId: 'p1', year: null } })
    await flushPromises()
    expect(get).not.toHaveBeenCalled()
    await w.setProps({ year: 2025 })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(1)
    expect(get.mock.calls[0][1].params).toEqual({ year: 2025 })
    expect(w.find('.workflow-progress').exists()).toBe(true)
  })
})
