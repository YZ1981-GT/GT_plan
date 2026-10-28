/**
 * 底稿短链页 `/workpapers/:wpId`（spec acnr-foundation-defect-closure T16 / RV7.5-01）。
 *
 * 成功：按 locate 返回的项目 `router.replace` 到底稿编辑器（命名路由 WorkpaperEditor），sheet / cell 原样保留；
 * 失败（403 / 404 / 410 回收站 / 网络错误 / 编号无效）：显示中文原因与下一步，不跳转。
 * 用真实路由表（memory history）挂载，`api.get` 按生产错误形状返回。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { defineComponent, h } from 'vue'

vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), configure: vi.fn() } }))
const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))
vi.mock('@/composables/useWorkpaperNavigation', async (importOriginal) => {
  // 只用纯函数 workpaperEditorRoute（真实实现），不加载 composable 依赖的 store / ACNR
  const actual = await importOriginal<typeof import('@/composables/useWorkpaperNavigation')>()
  return { workpaperEditorRoute: actual.workpaperEditorRoute }
})

import WorkpaperShortLink from '@/views/WorkpaperShortLink.vue'
import { SHORT_LINK_TEXT } from '@/views/composables/workpaperShortLink'

const WP = '8c8cd491-2d21-48ce-9622-e2d9bca0d499'
const PID = '03fab093-bccb-4443-a6cc-3771b5934905'
const Stub = defineComponent({ render: () => h('div', { class: 'editor-stub' }) })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workpapers/:wpId', name: 'WorkpaperShortLink', component: WorkpaperShortLink },
      { path: '/projects/:projectId/workpapers/:wpId/edit', name: 'WorkpaperEditor', component: Stub },
      { path: '/projects', name: 'Projects', component: Stub },
    ],
  })
}

async function open(path: string) {
  const router = makeRouter()
  const replace = vi.spyOn(router, 'replace')
  await router.push(path)
  await router.isReady()
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    global: { plugins: [router], stubs: { 'el-result': { props: ['title', 'subTitle'],
      template: '<div class="res">{{ title }}|{{ subTitle }}<slot name="extra" /></div>' },
    'el-button': { template: '<button><slot /></button>' } } },
  })
  await flushPromises()
  await flushPromises()
  return { router, replace, wrapper }
}

function httpError(status: number, detail: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), { response: { status, data: { detail } } })
}

beforeEach(() => { apiMocks.get.mockReset() })

describe('底稿短链：成功 → replace 到编辑器', () => {
  it('replace 目标是 WorkpaperEditor + locate 的项目，sheet / cell 原样保留', async () => {
    apiMocks.get.mockResolvedValue({ wp_id: WP, project_id: PID, wp_code: 'E1' })
    const { router, replace } = await open(`/workpapers/${WP}?sheet=E1-14&cell=C10`)
    expect(apiMocks.get).toHaveBeenCalledWith(`/api/acnr/workpapers/${WP}/locate`, expect.objectContaining({ _silent: true }))
    expect(replace).toHaveBeenCalledTimes(1)
    expect(replace.mock.calls[0][0]).toEqual({
      name: 'WorkpaperEditor', params: { projectId: PID, wpId: WP }, query: { sheet: 'E1-14', cell: 'C10' } })
    expect(router.currentRoute.value.fullPath).toBe(`/projects/${PID}/workpapers/${WP}/edit?sheet=E1-14&cell=C10`)
  })

  it('没有查询串时不带空 query', async () => {
    apiMocks.get.mockResolvedValue({ wp_id: WP, project_id: PID, wp_code: 'E1' })
    const { replace } = await open(`/workpapers/${WP}`)
    expect(replace.mock.calls[0][0]).toEqual({ name: 'WorkpaperEditor', params: { projectId: PID, wpId: WP } })
  })
})

describe('底稿短链：失败 → 中文原因，不跳转', () => {
  it.each([
    [403, SHORT_LINK_TEXT.forbidden],
    [404, SHORT_LINK_TEXT.notFound],
    [410, SHORT_LINK_TEXT.recycled],
    [500, SHORT_LINK_TEXT.failed],
  ])('HTTP %s', async (status, text) => {
    apiMocks.get.mockRejectedValue(httpError(status as number, { message: 'x' }))
    const { router, replace, wrapper } = await open(`/workpapers/${WP}?sheet=E1-14`)
    expect(replace).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('WorkpaperShortLink')
    expect(wrapper.text()).toContain(text.reason)
    expect(wrapper.text()).toContain(text.hint)
    expect(wrapper.text()).toContain('返回上一页')
    expect(wrapper.text()).toContain('进入项目列表')
    expect(wrapper.text()).not.toMatch(/Request failed|status code/)
  })

  it('网络错误（无 response）', async () => {
    apiMocks.get.mockRejectedValue(new Error('Network Error'))
    const { replace, wrapper } = await open(`/workpapers/${WP}`)
    expect(replace).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(SHORT_LINK_TEXT.failed.reason)
    expect(wrapper.text()).not.toContain('Network Error')
  })

  it('编号不是 UUID：不发请求、提示编号无效', async () => {
    const { replace, wrapper } = await open('/workpapers/E1-14')
    expect(apiMocks.get).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(SHORT_LINK_TEXT.invalid.reason)
  })
})
