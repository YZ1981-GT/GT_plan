/**
 * AiContentPendingBanner — Task 6.4 vitest 单测
 *
 * 验证：
 * 1. projectId 为空时不显示横幅
 * 2. 后端返回 count=0 时不显示
 * 3. 后端返回 count>0 时显示并展示数量
 * 4. 后端返回 404 时静默 fallback 到 0
 * 5. 数组返回兼容
 * 6. expose refresh() 方法可调用
 */

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

import AiContentPendingBanner from '../AiContentPendingBanner.vue'

describe('AiContentPendingBanner', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('projectId 为空时不调用 API 也不显示横幅', async () => {
    mockGet.mockResolvedValue({ count: 5 })
    const wrapper = mount(AiContentPendingBanner, {
      props: { projectId: '' },
    })
    await flushPromises()
    expect(mockGet).not.toHaveBeenCalled()
    expect(wrapper.find('.gt-ai-pending-banner').exists()).toBe(false)
  })

  it('后端返回 count=0 时不显示', async () => {
    mockGet.mockResolvedValue({ count: 0 })
    const wrapper = mount(AiContentPendingBanner, {
      props: { projectId: 'p1' },
    })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledWith('/api/projects/p1/ai-content/pending', { _silent: true })
    expect(wrapper.find('.gt-ai-pending-banner').exists()).toBe(false)
  })

  it('后端返回 count>0 时显示数量', async () => {
    mockGet.mockResolvedValue({ count: 7 })
    const wrapper = mount(AiContentPendingBanner, {
      props: { projectId: 'p1' },
    })
    await flushPromises()
    expect(wrapper.find('.gt-ai-pending-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain('7')
    expect(wrapper.text()).toContain('待确认')
  })

  it('数组返回兼容（length=3）', async () => {
    mockGet.mockResolvedValue([{ id: 'a' }, { id: 'b' }, { id: 'c' }])
    const wrapper = mount(AiContentPendingBanner, {
      props: { projectId: 'p2' },
    })
    await flushPromises()
    expect(wrapper.find('.gt-ai-pending-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain('3')
  })

  it('items 字段返回兼容', async () => {
    mockGet.mockResolvedValue({ items: [{ id: 'a' }, { id: 'b' }] })
    const wrapper = mount(AiContentPendingBanner, {
      props: { projectId: 'p3' },
    })
    await flushPromises()
    expect(wrapper.find('.gt-ai-pending-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain('2')
  })

  it('后端 404 静默 fallback 到 0', async () => {
    mockGet.mockRejectedValue(new Error('404 Not Found'))
    const wrapper = mount(AiContentPendingBanner, {
      props: { projectId: 'p4' },
    })
    await flushPromises()
    expect(wrapper.find('.gt-ai-pending-banner').exists()).toBe(false)
  })

  it('expose refresh() 方法供父组件调用', async () => {
    mockGet.mockResolvedValueOnce({ count: 0 })
    const wrapper = mount(AiContentPendingBanner, {
      props: { projectId: 'p5' },
    })
    await flushPromises()
    expect(wrapper.find('.gt-ai-pending-banner').exists()).toBe(false)

    // 模拟新增 AI 内容后父组件主动 refresh
    mockGet.mockResolvedValueOnce({ count: 2 })
    await (wrapper.vm as any).refresh()
    await flushPromises()
    expect(wrapper.find('.gt-ai-pending-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain('2')
  })

  it('点击查看明细按钮触发 view 事件', async () => {
    mockGet.mockResolvedValue({ count: 1 })
    const wrapper = mount(AiContentPendingBanner, {
      props: { projectId: 'p6' },
    })
    await flushPromises()
    const btn = wrapper.find('.gt-ai-pending-banner__btn')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    expect(wrapper.emitted('view')).toBeTruthy()
    expect(wrapper.emitted('view')!.length).toBe(1)
  })
})
