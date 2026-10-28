/**
 * 账表穿透页的年度（spec post-push-residual-defect-closure 6.5.3）：
 * 路由没带年度时取项目 store 的年度（原先只认路由 ⇒ 有年度的项目也提示「未设置」）；
 * 都没有 ⇒ 提示、清掉穿透 store 里上次的年度（免得翻页 / 筛选按旧年度取数）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const { get, warning, route } = vi.hoisted(() => ({
  get: vi.fn(),
  warning: vi.fn(),
  route: { params: { projectId: 'p1' } as Record<string, string>, query: {} as Record<string, string> },
}))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/utils/http', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))
vi.mock('@/services/auditPlatformApi', () => ({ getProject: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({}) } }))
vi.mock('element-plus', async (orig) => {
  const mod = await orig<typeof import('element-plus')>()
  return { ...mod, ElMessage: Object.assign(vi.fn(), { warning, success: vi.fn(), info: vi.fn(), error: vi.fn() }) }
})

import Drilldown from '../Drilldown.vue'
import { useDrilldownStore } from '@/stores/drilldown'
import { useProjectStore } from '@/stores/project'

function mountPage() {
  return mount(Drilldown, { global: { plugins: [ElementPlus], mocks: { $router: { push: vi.fn() } } } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  route.query = {}
  get.mockReset().mockResolvedValue({ data: { items: [], total: 0 } })
  warning.mockReset()
})

describe('Drilldown 年度', () => {
  it('路由没带年度：用项目 store 的年度取余额', async () => {
    useProjectStore().year = 2025
    mountPage()
    await flushPromises()
    expect(useDrilldownStore().year).toBe(2025)
    expect(get).toHaveBeenCalledWith('/api/projects/p1/drilldown/balance', { params: expect.objectContaining({ year: 2025 }) })
  })

  it('路由与 store 都没有：提示，清掉上次的年度，不取数', async () => {
    useDrilldownStore().setProject('p1', 2024) // 上次访问留下的
    mountPage()
    await flushPromises()
    expect(warning).toHaveBeenCalledWith(expect.stringContaining('未设置审计年度'))
    expect(useDrilldownStore().year).toBeNull()
    expect(get).not.toHaveBeenCalled()
  })
})
