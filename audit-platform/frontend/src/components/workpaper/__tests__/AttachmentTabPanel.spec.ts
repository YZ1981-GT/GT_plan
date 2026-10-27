/**
 * AttachmentTabPanel — 侧栏附件页签读统一视图（spec attachment-evidence-intake 需求 4.3）
 *
 * 回归背景：原先读 process-record 的底稿附件（只认 reference_type='working_paper'），行级证据与函证挂载都看不到；
 * 每个附件加载时再发一次「关联底稿」请求（N+1）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

// vi.mock 工厂会被提升到文件顶部：桩组件的构造放进 vi.hoisted
const { passthrough } = vi.hoisted(() => ({
  passthrough: async (name: string) => {
    const vue = await import('vue')
    return {
      default: vue.defineComponent({
        name,
        setup(_props, { slots }) {
          return () => vue.h('div', { class: `${name}-stub` }, slots.default?.())
        },
      }),
    }
  },
}))
vi.mock('@/components/workpaper/AttachmentDropZone.vue', () => passthrough('AttachmentDropZone'))
vi.mock('@/components/common/AttachmentPreviewDrawer.vue', () => passthrough('AttachmentPreviewDrawer'))
vi.mock('@/components/attachment/OcrConfirmDialog.vue', () => passthrough('OcrConfirmDialog'))

import AttachmentTabPanel from '../AttachmentTabPanel.vue'

const PopoverStub = defineComponent({
  name: 'ElPopoverStub',
  emits: ['show'],
  setup(_props, { slots, emit }) {
    return () => h('div', { class: 'popover-stub', onMouseenter: () => emit('show') }, [
      slots.reference?.(),
      slots.default?.(),
    ])
  },
})

const stubs = {
  'el-popover': PopoverStub,
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-icon': { template: '<i><slot /></i>' },
}

const VIEW = {
  items: [
    { id: 'a1', file_name: '合同.pdf', file_type: 'pdf', file_size: 2048, created_at: '2026-10-27T08:00:00',
      sources: ['associated'], linked_wp_count: 2 },
    { id: 'a2', file_name: '行证据.pdf', file_type: 'pdf', file_size: 1024, created_at: '2026-10-27T09:00:00',
      sources: ['evidence_link'], linked_wp_count: 1 },
  ],
}

describe('AttachmentTabPanel', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('只读一次统一视图，不再逐个附件请求关联底稿', async () => {
    mockGet.mockResolvedValueOnce(VIEW)
    const wrapper = mount(AttachmentTabPanel, { props: { projectId: 'p1', wpId: 'w1' }, global: { stubs } })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet.mock.calls[0][0]).toBe('/api/working-papers/w1/attachments')
    expect(wrapper.text()).toContain('合同.pdf')
    expect(wrapper.text()).toContain('行证据.pdf')
    const rowTags = wrapper.findAll('[data-testid="row-evidence-tag"]')
    expect(rowTags).toHaveLength(1)
    expect(wrapper.find('[data-attachment="a1"]').text()).toContain('×2')
    expect(wrapper.find('[data-attachment="a2"]').exists()).toBe(false)
  })

  it('悬停关联底稿数时才取清单，取过一次后复用', async () => {
    mockGet
      .mockResolvedValueOnce(VIEW)
      .mockResolvedValueOnce([
        { wp_id: 'w1', wp_code: 'D4-2', wp_name: '合同检查' },
        { wp_id: 'w9', wp_code: 'F2-30', wp_name: '存货采购合同' },
      ])
    const wrapper = mount(AttachmentTabPanel, { props: { projectId: 'p1', wpId: 'w1' }, global: { stubs } })
    await flushPromises()
    const popover = wrapper.find('.popover-stub')
    expect(popover.text()).toContain('加载中')
    await popover.trigger('mouseenter')
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(mockGet.mock.calls[1][0]).toBe('/api/process-record/attachments/a1/workpapers')
    expect(popover.text()).toContain('F2-30')
    await popover.trigger('mouseenter')
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('关联底稿清单取失败时提示，下次悬停重试', async () => {
    mockGet
      .mockResolvedValueOnce(VIEW)
      .mockRejectedValueOnce(new Error('500'))
      .mockResolvedValueOnce([{ wp_id: 'w1', wp_code: 'D4-2', wp_name: '合同检查' }])
    const wrapper = mount(AttachmentTabPanel, { props: { projectId: 'p1', wpId: 'w1' }, global: { stubs } })
    await flushPromises()
    const popover = wrapper.find('.popover-stub')
    await popover.trigger('mouseenter')
    await flushPromises()
    expect(popover.text()).toContain('关联底稿加载失败')
    await popover.trigger('mouseenter')
    await flushPromises()
    expect(popover.text()).toContain('D4-2')
  })
})
