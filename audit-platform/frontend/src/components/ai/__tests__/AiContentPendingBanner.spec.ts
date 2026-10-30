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
const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

const msgSuccess = vi.fn()
const msgWarning = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...a: any[]) => msgSuccess(...a),
    warning: (...a: any[]) => msgWarning(...a),
    error: vi.fn(),
  },
}))

vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import { eventBus } from '@/utils/eventBus'
import AiContentPendingBanner from '../AiContentPendingBanner.vue'

describe('AiContentPendingBanner', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    msgSuccess.mockReset()
    msgWarning.mockReset()
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

  // ── 复盘 P0/P2 回补：确认结果分流 + eventBus 刷新 ──────────────────────────

  it('确认返回 skipped（锁定/无权）→ 警告原因、不移出、不发 resolved', async () => {
    mockGet.mockResolvedValue({ count: 1, items: [{ id: 'log-1', instance_type: 'note', content: 'x' }] })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'p1' } })
    await flushPromises()
    mockPost.mockResolvedValue({
      confirm_action: 'pending',
      writeback: { skipped: true, reason: '项目已被合并锁定，内容保持待确认' },
    })
    await (wrapper.vm as any).act({ id: 'log-1', instance_type: 'note', content: 'x' }, 'confirm')
    await flushPromises()
    expect(msgWarning).toHaveBeenCalledWith('项目已被合并锁定，内容保持待确认')
    expect(msgSuccess).not.toHaveBeenCalled()
    expect(wrapper.emitted('resolved')).toBeFalsy()
  })

  it('确认返回 written（附注已写）→ 成功提示含章节、发 resolved', async () => {
    mockGet.mockResolvedValue({ count: 1, items: [{ id: 'log-1', instance_type: 'note', content: 'x' }] })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'p1' } })
    await flushPromises()
    mockPost.mockResolvedValue({
      confirm_action: 'confirmed',
      writeback: { written: true, note_section: '八、1' },
    })
    await (wrapper.vm as any).act({ id: 'log-1', instance_type: 'note', content: 'x' }, 'confirm')
    await flushPromises()
    expect(msgSuccess).toHaveBeenCalledWith(expect.stringContaining('八、1'))
    expect(wrapper.emitted('resolved')).toBeTruthy()
  })

  it('底稿类确认 written=false → 提示复制、仍发 resolved', async () => {
    mockGet.mockResolvedValue({ count: 1, items: [{ id: 'log-1', instance_type: 'workpaper', content: 'x' }] })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'p1' } })
    await flushPromises()
    mockPost.mockResolvedValue({
      confirm_action: 'confirmed',
      writeback: { written: false, reason: '底稿内容不自动写入，请在底稿页面复制到目标位置' },
    })
    await (wrapper.vm as any).act({ id: 'log-1', instance_type: 'workpaper', content: 'x' }, 'confirm')
    await flushPromises()
    expect(msgSuccess).toHaveBeenCalledWith(expect.stringContaining('复制'))
    expect(wrapper.emitted('resolved')).toBeTruthy()
  })

  it('监听 ai-content:adopted 事件后重拉计数（同项目）', async () => {
    mockGet.mockResolvedValueOnce({ count: 0 })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'pX' } })
    await flushPromises()
    expect(wrapper.find('.gt-ai-pending-banner').exists()).toBe(false)
    mockGet.mockResolvedValueOnce({ count: 3 })
    eventBus.emit('ai-content:adopted', { projectId: 'pX' })
    await flushPromises()
    expect(wrapper.text()).toContain('3')
  })

  it('ai-content:adopted 事件项目不同则不重拉', async () => {
    mockGet.mockResolvedValueOnce({ count: 0 })
    mount(AiContentPendingBanner, { props: { projectId: 'pX' } })
    await flushPromises()
    mockGet.mockClear()
    eventBus.emit('ai-content:adopted', { projectId: 'pOther' })
    await flushPromises()
    expect(mockGet).not.toHaveBeenCalled()
  })

  // ── spec ai-content-pending-target-label：显示后端补的目标标签，不露出带 UUID 的原始 target_cell ──

  it('有目标标签：显示来源类型、标签与位置，不显示原始 target_cell', async () => {
    mockGet.mockResolvedValue({
      count: 1,
      items: [{
        id: 'log-1',
        instance_type: 'workpaper',
        target_cell: 'workpaper:3fa85f64-5717-4562-b3fc-2c963f66afa6:E5',
        target_label: 'D2 应收账款审定表',
        target_position: 'E5',
        content: 'x',
      }],
    })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'p1' } })
    await flushPromises()
    const meta = wrapper.find('.gt-aip-card__meta')
    expect(meta.exists()).toBe(true)
    expect(meta.find('.gt-aip-card__where').text()).toBe('底稿')
    expect(meta.find('.gt-aip-card__target').text()).toBe('D2 应收账款审定表')
    expect(meta.findAll('.gt-aip-card__cell').map((c) => c.text())).toEqual(['E5'])
    expect(meta.text()).not.toContain('3fa85f64')
  })

  it('有目标标签但没有位置：只显示标签', async () => {
    mockGet.mockResolvedValue({
      count: 1,
      items: [{
        id: 'log-2',
        instance_type: 'note',
        target_cell: 'note:9b2f0c1e-0000-4000-8000-000000000001',
        target_label: '八、1 货币资金',
        target_position: null,
        content: 'x',
      }],
    })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'p1' } })
    await flushPromises()
    const meta = wrapper.find('.gt-aip-card__meta')
    expect(meta.find('.gt-aip-card__where').text()).toBe('附注')
    expect(meta.find('.gt-aip-card__target').text()).toBe('八、1 货币资金')
    expect(meta.find('.gt-aip-card__cell').exists()).toBe(false)
  })

  it('没有目标标签（目标已找不到 / 旧后端）：照旧显示原始 target_cell', async () => {
    mockGet.mockResolvedValue({
      count: 1,
      items: [{ id: 'log-3', instance_type: 'note', target_cell: 'note:abc:正文', target_label: null, content: 'x' }],
    })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'p1' } })
    await flushPromises()
    const meta = wrapper.find('.gt-aip-card__meta')
    expect(meta.find('.gt-aip-card__target').exists()).toBe(false)
    expect(meta.find('.gt-aip-card__cell').text()).toBe('note:abc:正文')
  })

  it('卡片上有「复制」按钮：点了把该条 AI 原文写进剪贴板（底稿类确认后要到底稿页面粘贴）', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    mockGet.mockResolvedValue({
      count: 1,
      items: [{ id: 'log-9', instance_type: 'workpaper', target_cell: 'workpaper:x', content: '底稿结论草稿' }],
    })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'p1' } })
    await flushPromises()
    const btn = wrapper.find('.gt-aip-card__copy')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('底稿结论草稿')
  })

  it('卸载后不再响应 ai-content:adopted（取消订阅）', async () => {
    mockGet.mockResolvedValue({ count: 0 })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'pY' } })
    await flushPromises()
    wrapper.unmount()
    mockGet.mockClear()
    eventBus.emit('ai-content:adopted', { projectId: 'pY' })
    await flushPromises()
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('复制内容调用 clipboard 并提示', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    mockGet.mockResolvedValue({ count: 1, items: [{ id: 'log-1', instance_type: 'workpaper', content: '待复制' }] })
    const wrapper = mount(AiContentPendingBanner, { props: { projectId: 'p1' } })
    await flushPromises()
    await (wrapper.vm as any).copyContent({ content: '待复制的 AI 文本' })
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('待复制的 AI 文本')
    expect(msgSuccess).toHaveBeenCalledWith(expect.stringContaining('复制'))
  })
})
