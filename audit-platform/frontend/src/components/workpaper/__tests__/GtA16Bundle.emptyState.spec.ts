/**
 * GtA16Bundle：本项目没有 A16-1 ~ A16-7 子底稿时显示空态说明（spec api-prefix-fix-recovery R3）。
 * 原先只剩空白页签区、看不出原因（residual 任务 28 浏览器实测）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const getWpIndex = vi.fn()
vi.mock('@/services/workpaperApi', () => ({ getWpIndex: (...a: unknown[]) => getWpIndex(...a) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('../WorkpaperWordEditor.vue', () => ({ default: { name: 'WorkpaperWordEditor', template: '<div class="word-editor" />' } }))

import GtA16Bundle from '../GtA16Bundle.vue'

const stubs = {
  'el-empty': { props: ['description'], template: '<div class="el-empty-stub">{{ description }}</div>' },
  'el-tabs': { template: '<div class="el-tabs-stub"><slot /></div>' },
  'el-tab-pane': { props: ['label', 'name'], template: '<div class="el-tab-pane-stub" :data-name="name"><slot /></div>' },
}

function mountBundle() {
  return mount(GtA16Bundle, {
    props: { wpId: 'wp-a16', projectId: 'p1' },
    global: { stubs, directives: { loading: {} } },
  })
}

beforeEach(() => { getWpIndex.mockReset() })

describe('GtA16Bundle 空态', () => {
  it('wp_index 里没有任何 A16 子底稿：显示空态说明、不渲染页签区', async () => {
    getWpIndex.mockResolvedValue([{ id: 'x', wp_code: 'A16' }, { id: 'y', wp_code: 'A18-2' }])
    const w = mountBundle()
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(true)
    expect(w.find('.el-empty-stub').text()).toContain('A16-1 ~ A16-7')
    expect(w.find('.el-tabs-stub').exists()).toBe(false)
  })

  it('取 wp_index 失败：同样显示空态（不留空白）', async () => {
    getWpIndex.mockRejectedValue(new Error('boom'))
    const w = mountBundle()
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(true)
  })

  it('有子底稿：只渲染存在的页签，不显示空态', async () => {
    getWpIndex.mockResolvedValue([{ id: 'a1', wp_code: 'A16-1' }, { id: 'a3', wp_code: 'A16-3' }])
    const w = mountBundle()
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(false)
    const names = w.findAll('.el-tab-pane-stub').map(n => n.attributes('data-name'))
    expect(names).toEqual(['A16-1', 'A16-3'])
  })

  it('加载未结束前不闪空态', async () => {
    let resolve!: (v: unknown) => void
    getWpIndex.mockReturnValue(new Promise(r => { resolve = r }))
    const w = mountBundle()
    await Promise.resolve()
    expect(w.find('.el-empty-stub').exists()).toBe(false)
    resolve([])
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(true)
  })
})
