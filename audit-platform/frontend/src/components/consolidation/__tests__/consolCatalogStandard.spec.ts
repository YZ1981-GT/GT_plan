/**
 * 合并四栏目录按项目口径取附注章节（spec note-pull-header-formula-closure，浏览器实测发现）：
 * 原先恒从国企版起、只听顶部栏切换事件；它挂载晚于合并页读项目信息 ⇒ 上市集团四栏目录是国企版章节。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.get } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'p-1' } }) }))
vi.mock('element-plus', () => ({ ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() } }))

import ConsolCatalog from '../ConsolCatalog.vue'
import { eventBus } from '@/utils/eventBus'

const STUBS = Object.fromEntries(
  ['el-tree', 'el-tabs', 'el-tab-pane', 'el-input', 'el-tag', 'el-button', 'el-tooltip', 'el-empty', 'el-icon']
    .map(name => [name, true]),
)
const mountCatalog = () => shallowMount(ConsolCatalog, { global: { stubs: STUBS } })

function sectionRequests(): string[] {
  return h.get.mock.calls.map(c => String(c[0])).filter(u => u.includes('/consol-note-sections/'))
}

beforeEach(() => {
  h.get.mockReset()
})

describe('ConsolCatalog 准则', () => {
  it('上市项目：挂载即按上市版取附注章节', async () => {
    h.get.mockImplementation(async (url: string) => (String(url).includes('/consol-note-sections/') ? [] : { template_type: 'listed' }))
    const wrapper = mountCatalog()
    await flushPromises()
    expect(sectionRequests()).toEqual(['/api/consol-note-sections/listed'])
    wrapper.unmount()
  })

  it('取不到项目口径按国企版；顶部栏切换照旧生效', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (String(url).includes('/consol-note-sections/')) return []
      throw new Error('offline')
    })
    const wrapper = mountCatalog()
    await flushPromises()
    expect(sectionRequests()).toEqual(['/api/consol-note-sections/soe'])
    eventBus.emit('standard-change', { standard: 'listed' })
    await flushPromises()
    expect(sectionRequests()).toEqual(['/api/consol-note-sections/soe', '/api/consol-note-sections/listed'])
    wrapper.unmount()
  })
})
