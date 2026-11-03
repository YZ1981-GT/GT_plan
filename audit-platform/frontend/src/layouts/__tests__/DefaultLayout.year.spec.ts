/**
 * DefaultLayout 的年度（spec post-push-residual-defect-closure 6.5.2）：
 * - 路由内容区套 ProjectContextGate：换项目后年度定下来之前不挂载页面；
 * - 待重算「查看详情」缺年度不带 year（原先兜底去年）、「重算」缺年度提示不发；
 * - 目录切项目不再把当前项目的年度带给目标项目。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const getProject = vi.fn()
const apiGet = vi.fn()
const apiPost = vi.fn()
const warning = vi.fn()
vi.mock('@/services/auditPlatformApi', () => ({ getProject: (...a: unknown[]) => getProject(...a) }))
vi.mock('@/services/apiProxy', () => ({ api: { get: (...a: unknown[]) => apiGet(...a), post: (...a: unknown[]) => apiPost(...a) } }))
vi.mock('@/services/pmApi', () => ({ getGlobalReviewInbox: vi.fn().mockResolvedValue({ total: 0 }) }))
vi.mock('@/composables/useNavigationStack', () => ({ initGlobalBackspace: vi.fn() }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/stores/roleContext', () => ({
  useRoleContextStore: () => ({
    loaded: true, initialize: vi.fn(), loadProjectRole: vi.fn().mockResolvedValue(undefined),
    effectiveRole: 'auditor', isPartner: false, isManager: false, currentProjectRole: null,
  }),
}))
vi.mock('element-plus', async (orig) => {
  const mod = await orig<typeof import('element-plus')>()
  return { ...mod, ElMessage: Object.assign(vi.fn(), { warning: (...a: unknown[]) => warning(...a), success: vi.fn(), error: vi.fn(), info: vi.fn() }) }
})

vi.mock('@/layouts/ThreeColumnLayout.vue', async () => ({ default: (await import('./defaultLayoutStubs')).slotStub('ThreeColumnLayout', ['middle', 'catalog', 'detail']) }))
vi.mock('@/components/layout/MiddleProjectList.vue', async () => ({ default: (await import('./defaultLayoutStubs')).emitterStub('MiddleProjectList') }))
vi.mock('@/components/layout/FourColumnCatalog.vue', async () => ({ default: (await import('./defaultLayoutStubs')).emitterStub('FourColumnCatalog') }))
vi.mock('@/components/common/LinkageStatusBar.vue', async () => ({ default: (await import('./defaultLayoutStubs')).emitterStub('LinkageStatusBar') }))
vi.mock('@/components/layout/MiddlePlaceholder.vue', async () => ({ default: (await import('./defaultLayoutStubs')).blankStub('MiddlePlaceholder') }))
vi.mock('@/components/layout/DetailProjectPanel.vue', async () => ({ default: (await import('./defaultLayoutStubs')).blankStub('DetailProjectPanel') }))
vi.mock('@/components/layout/FourColumnContent.vue', async () => ({ default: (await import('./defaultLayoutStubs')).blankStub('FourColumnContent') }))
vi.mock('@/components/consolidation/ConsolMiddleNav.vue', async () => ({ default: (await import('./defaultLayoutStubs')).blankStub('ConsolMiddleNav') }))
vi.mock('@/components/consolidation/ConsolCatalog.vue', async () => ({ default: (await import('./defaultLayoutStubs')).blankStub('ConsolCatalog') }))
vi.mock('@/components/collaboration/NotificationCenter.vue', async () => ({ default: (await import('./defaultLayoutStubs')).blankStub('NotificationCenter') }))
vi.mock('@/components/common/GlobalSearchDialog.vue', async () => ({ default: (await import('./defaultLayoutStubs')).blankStub('GlobalSearchDialog') }))

import DefaultLayout from '../DefaultLayout.vue'
import { useProjectStore } from '@/stores/project'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'

const Page = defineComponent({ setup: () => () => h('div', { class: 'route-page' }, '页面') })

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Page },
      { path: '/projects/:projectId/:sub?', component: Page },
    ],
  })
  // 与真实路由守卫同口径：导航前同步项目上下文（不等 API）
  router.beforeEach((to) => { if (to.params.projectId) void useProjectStore().syncFromRoute(to as any) })
  await router.push(path)
  await router.isReady()
  const w = mount(DefaultLayout, { global: { plugins: [router, ElementPlus] } })
  return { w, router }
}

beforeEach(() => {
  setActivePinia(createPinia())
  getProject.mockReset()
  apiGet.mockReset().mockImplementation((url: string) =>
    Promise.resolve(String(url).endsWith('/stale-summary') ? { stale_count: 3 } : { years: [] }))
  apiPost.mockReset().mockResolvedValue({ stale_resolution: { kept_stale: 0 } })
  warning.mockReset()
})

describe('ProjectContextGate 接在路由内容区', () => {
  it('换项目取项目信息期间不挂载页面，取到后才挂', async () => {
    const d = deferred<any>()
    getProject.mockReturnValue(d.promise)
    const { w } = await mountAt('/projects/p1/trial-balance')
    await flushPromises()
    expect(w.find('.route-page').exists()).toBe(false)
    expect(w.text()).toContain('正在读取项目信息')
    d.resolve({ audit_year: 2025 })
    await flushPromises()
    expect(w.find('.route-page').exists()).toBe(true)
    expect(useProjectStore().year).toBe(2025)
  })
})

describe('待重算横条', () => {
  it('项目没填年度：「查看详情」不带 year（不兜底去年）', async () => {
    getProject.mockResolvedValue({ client_name: '【测试】无年度' })
    const { w, router } = await mountAt('/projects/p0/trial-balance')
    await flushPromises()
    w.findComponent({ name: 'LinkageStatusBar' }).vm.$emit('detail')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/projects/p0/workpapers')
    expect(router.currentRoute.value.query).toEqual({ view: 'list', filter: 'stale' })
  })

  it('有年度：「查看详情」带本项目年度', async () => {
    getProject.mockResolvedValue({ audit_year: 2025 })
    const { w, router } = await mountAt('/projects/p1/trial-balance')
    await flushPromises()
    w.findComponent({ name: 'LinkageStatusBar' }).vm.$emit('detail')
    await flushPromises()
    expect(router.currentRoute.value.query.year).toBe('2025')
  })

  it('项目没填年度：「重算」提示后不发请求', async () => {
    getProject.mockResolvedValue({})
    const { w } = await mountAt('/projects/p0/trial-balance')
    await flushPromises()
    w.findComponent({ name: 'LinkageStatusBar' }).vm.$emit('recalc')
    await flushPromises()
    expect(apiPost).not.toHaveBeenCalled()
    expect(warning).toHaveBeenCalledWith(expect.stringContaining(MISSING_AUDIT_YEAR_MESSAGE))
  })

  it('有年度：「重算」按本项目年度发', async () => {
    getProject.mockResolvedValue({ audit_year: 2025 })
    const { w } = await mountAt('/projects/p1/trial-balance')
    await flushPromises()
    w.findComponent({ name: 'LinkageStatusBar' }).vm.$emit('recalc')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/api/projects/p1/trial-balance/recalc', undefined, { params: { year: 2025 } })
  })
})

describe('目录切项目', () => {
  async function switchTo(item: Record<string, unknown>) {
    getProject.mockResolvedValue({ audit_year: 2025 })
    const { w, router } = await mountAt('/projects/p1/trial-balance')
    await flushPromises()
    w.findComponent({ name: 'MiddleProjectList' }).vm.$emit('select', { id: 'p1', name: '当前项目' })
    await flushPromises()
    w.findComponent({ name: 'FourColumnCatalog' }).vm.$emit('select', { type: 'switch_project', ...item })
    await flushPromises()
    return router
  }

  it('目标项目没带年度：不把当前项目的 2025 带过去', async () => {
    const router = await switchTo({ project_id: 'p2' })
    expect(router.currentRoute.value.params.projectId).toBe('p2')
    expect(router.currentRoute.value.query.year).toBeUndefined()
  })

  it('目标项目带了自己的年度：用它', async () => {
    const router = await switchTo({ project_id: 'p2', year: 2024 })
    expect(router.currentRoute.value.query.year).toBe('2024')
  })
})
