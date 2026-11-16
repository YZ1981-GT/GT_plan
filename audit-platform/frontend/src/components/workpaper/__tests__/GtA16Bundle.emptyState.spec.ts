/**
 * GtA16Bundle：本项目没有 A16-1 ~ A16-7 子底稿时显示空态说明（spec api-prefix-fix-recovery R3）。
 * 原先只剩空白页签区、看不出原因（residual 任务 28 浏览器实测）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const getWpIndex = vi.fn()
vi.mock('@/services/workpaperApi', () => ({
  __esModule: true,
  getWpIndex: (...a: unknown[]) => getWpIndex(...a),
}))

const push = vi.fn()
vi.mock('vue-router', () => ({
  __esModule: true,
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push }),
}))

// __esModule: true 让 defineAsyncComponent 正确解包 default（否则 test-utils 读取命名空间的
// __isTeleport 触发 vitest mock 未定义导出错误 —— 同 GtC1EntityControl.spec.ts 的写法）
vi.mock('../WorkpaperWordEditor.vue', () => ({
  __esModule: true,
  default: { name: 'WorkpaperWordEditor', template: '<div class="word-editor" />' },
}))

import GtA16Bundle from '../GtA16Bundle.vue'

const stubs = {
  'el-empty': {
    props: ['description'],
    template: '<div class="el-empty-stub"><span class="desc">{{ description }}</span><slot /></div>',
  },
  'el-button': { template: '<button class="el-button-stub" @click="$emit(\'click\')"><slot /></button>' },
  'el-tabs': { template: '<div class="el-tabs-stub"><slot /></div>' },
  'el-tab-pane': { props: ['label', 'name'], template: '<div class="el-tab-pane-stub" :data-name="name"><slot /></div>' },
}

function mountBundle() {
  return mount(GtA16Bundle, {
    props: { wpId: 'wp-a16', projectId: 'p1' },
    global: { stubs, directives: { loading: {} } },
  })
}

beforeEach(() => {
  getWpIndex.mockReset()
  push.mockReset()
})

describe('GtA16Bundle 空态', () => {
  it('wp_index 里没有任何 A16 子底稿：显示空态说明、不渲染页签区', async () => {
    getWpIndex.mockResolvedValue([{ id: 'x', wp_code: 'A16' }, { id: 'y', wp_code: 'A18-2' }])
    const w = mountBundle()
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(true)
    const desc = w.find('.el-empty-stub .desc').text()
    // 缺哪几张要具体列出，不能只说「一张都没有」
    for (const code of ['A16-1', 'A16-2', 'A16-3', 'A16-4', 'A16-5', 'A16-6', 'A16-7']) {
      expect(desc).toContain(code)
    }
    expect(w.find('.el-tabs-stub').exists()).toBe(false)
  })

  it('空态里的「去底稿列表生成」可点击，跳到本项目底稿列表并高亮 A16', async () => {
    getWpIndex.mockResolvedValue([{ id: 'x', wp_code: 'A16' }])
    const w = mountBundle()
    await flushPromises()
    const btn = w.findAll('.el-button-stub').find(b => b.text().includes('去底稿列表生成'))
    expect(btn, '空态里必须有去底稿列表的入口').toBeTruthy()
    await btn!.trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: 'p1' },
      query: { highlight: 'A16' },
    })
  })

  it('取 wp_index 失败：说明是加载失败（不是「未生成」），并给重试入口', async () => {
    let attempt = 0
    getWpIndex.mockImplementation(async () => {
      attempt += 1
      if (attempt === 1) throw new Error('网络异常')
      return [{ id: 'a1', wp_code: 'A16-1' }]
    })
    const w = mountBundle()
    await flushPromises()
    const desc = w.find('.el-empty-stub .desc').text()
    expect(desc).toContain('加载失败')
    expect(desc).toContain('网络异常')
    // 不能把加载失败说成「没有生成子底稿」
    expect(desc).not.toContain('还没有生成')

    // 重试：第二次成功则应正常渲染页签
    await w.findAll('.el-button-stub').find(b => b.text().includes('重试'))!.trigger('click')
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(false)
    expect(w.findAll('.el-tab-pane-stub').map(n => n.attributes('data-name'))).toEqual(['A16-1'])
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
    // 首帧 visibleTabs 同样是 0 —— 只按它判就会在这里误显空态
    expect(w.find('.el-empty-stub').exists()).toBe(false)
    resolve([])
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(true)
  })
})
