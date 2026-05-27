/**
 * ConflictBanner — Task 7.5 vitest 单测
 *
 * 验证：
 * 1. projectId 为空时不调用 API 也不显示横幅
 * 2. 后端返回 count=0 时不显示
 * 3. 后端返回 count>0 时显示并展示数量
 * 4. 后端 404 时静默 fallback 到 0
 * 5. 点击查看详情按钮触发 view 事件
 * 6. expose refresh() 方法可调用
 */

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))

vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

import ConflictBanner from '../ConflictBanner.vue'

const stubAlert = {
  template: '<div class="gt-conflict-banner-stub"><slot name="title" /></div>',
  props: ['type', 'showIcon', 'closable'],
}

const stubButton = {
  template: '<button @click="$emit(\'click\', $event)"><slot /></button>',
  props: ['type', 'size', 'text'],
  emits: ['click'],
}

function makeBanner(props: Record<string, any> = {}) {
  return mount(ConflictBanner, {
    props: { projectId: 'p1', ...props },
    global: {
      stubs: {
        'el-alert': stubAlert,
        'el-button': stubButton,
      },
    },
  })
}

describe('ConflictBanner', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('projectId 为空时不调用 API 也不显示横幅', async () => {
    mockGet.mockResolvedValue({ count: 5 })
    const wrapper = makeBanner({ projectId: '' })
    await flushPromises()
    expect(mockGet).not.toHaveBeenCalled()
    expect(wrapper.find('.gt-conflict-banner-stub').exists()).toBe(false)
  })

  it('后端返回 count=0 时不显示', async () => {
    mockGet.mockResolvedValue({ count: 0, items: [] })
    const wrapper = makeBanner({ projectId: 'p1' })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledWith('/api/projects/p1/conflicts/pending')
    expect(wrapper.find('.gt-conflict-banner-stub').exists()).toBe(false)
  })

  it('后端返回 count>0 时显示数量', async () => {
    mockGet.mockResolvedValue({ count: 3, items: [{ id: 'a' }, { id: 'b' }, { id: 'c' }] })
    const wrapper = makeBanner({ projectId: 'p1' })
    await flushPromises()
    expect(wrapper.find('.gt-conflict-banner-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('未调解')
  })

  it('数组返回兼容', async () => {
    mockGet.mockResolvedValue([{ id: 'a' }, { id: 'b' }])
    const wrapper = makeBanner({ projectId: 'p2' })
    await flushPromises()
    expect(wrapper.find('.gt-conflict-banner-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('2')
  })

  it('后端 404 静默 fallback 到 0', async () => {
    mockGet.mockRejectedValue(new Error('404 Not Found'))
    const wrapper = makeBanner({ projectId: 'p3' })
    await flushPromises()
    expect(wrapper.find('.gt-conflict-banner-stub').exists()).toBe(false)
  })

  it('点击查看详情触发 view 事件', async () => {
    mockGet.mockResolvedValue({ count: 2 })
    const wrapper = makeBanner({ projectId: 'p4' })
    await flushPromises()

    const btn = wrapper.find('button')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    expect(wrapper.emitted('view')).toBeTruthy()
    expect(wrapper.emitted('view')!.length).toBe(1)
  })

  it('expose refresh() 主动刷新', async () => {
    mockGet.mockResolvedValueOnce({ count: 0 })
    const wrapper = makeBanner({ projectId: 'p5' })
    await flushPromises()
    expect(wrapper.find('.gt-conflict-banner-stub').exists()).toBe(false)

    mockGet.mockResolvedValueOnce({ count: 1 })
    await (wrapper.vm as any).refresh()
    await flushPromises()
    expect(wrapper.find('.gt-conflict-banner-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('1')
  })

  it('projectId 切换触发重新加载', async () => {
    mockGet.mockResolvedValueOnce({ count: 0 })
    const wrapper = makeBanner({ projectId: 'p1' })
    await flushPromises()
    expect(mockGet).toHaveBeenLastCalledWith('/api/projects/p1/conflicts/pending')

    mockGet.mockResolvedValueOnce({ count: 4 })
    await wrapper.setProps({ projectId: 'p2' })
    await flushPromises()
    expect(mockGet).toHaveBeenLastCalledWith('/api/projects/p2/conflicts/pending')
    expect(wrapper.text()).toContain('4')
  })
})
