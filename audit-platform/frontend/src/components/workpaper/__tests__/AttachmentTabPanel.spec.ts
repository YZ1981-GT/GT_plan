/**
 * AttachmentTabPanel — 侧栏附件页签读统一视图（spec attachment-evidence-intake 需求 4.3）
 *
 * 回归背景：原先读 process-record 的底稿附件（只认 reference_type='working_paper'），行级证据与函证挂载都看不到；
 * 每个附件加载时再发一次「关联底稿」请求（N+1）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

// vi.mock 工厂会被提升到文件顶部：桩组件的构造放进 vi.hoisted
const { passthrough, previewDrawer } = vi.hoisted(() => ({
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
  previewDrawer: async () => {
    const vue = await import('vue')
    return {
      default: vue.defineComponent({
        name: 'AttachmentPreviewDrawerStub',
        props: { modelValue: Boolean, attachment: Object },
        emits: ['update:modelValue'],
        setup(props, { emit }) {
          return () => props.modelValue
            ? vue.h('div', { class: 'AttachmentPreviewDrawer-stub', 'data-attachment': props.attachment?.name }, [
                vue.h('button', { type: 'button', 'data-testid': 'preview-close', onClick: () => emit('update:modelValue', false) }, '关闭预览'),
              ])
            : null
        },
      }),
    }
  },
}))
vi.mock('@/components/workpaper/AttachmentDropZone.vue', () => passthrough('AttachmentDropZone'))
vi.mock('@/components/common/AttachmentPreviewDrawer.vue', () => previewDrawer())
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

  it('主列表失败不伪装成空态，重试后可恢复并带取消边界', async () => {
    const pending = new Promise<never>(() => {})
    mockGet.mockImplementationOnce(() => pending)
    const wrapper = mount(AttachmentTabPanel, { props: { projectId: 'p1', wpId: 'w1' }, global: { stubs } })
    await flushPromises()
    const signal = mockGet.mock.calls[0][1].signal as AbortSignal
    expect(signal).toBeInstanceOf(AbortSignal)
    wrapper.unmount()
    expect(signal.aborted).toBe(true)

    mockGet.mockReset()
    mockGet.mockRejectedValueOnce(Object.assign(new Error('500'), { response: { status: 500 } }))
    const retryWrapper = mount(AttachmentTabPanel, { props: { projectId: 'p1', wpId: 'w1' }, global: { stubs } })
    await flushPromises()
    expect(retryWrapper.find('[data-testid="attachment-tab-load-error"]').exists()).toBe(true)
    expect(retryWrapper.text()).toContain('关联附件加载失败')
    expect(retryWrapper.text()).not.toContain('暂无关联附件')
    mockGet.mockResolvedValueOnce(VIEW)
    await retryWrapper.find('[data-testid="attachment-tab-retry"]').trigger('click')
    await flushPromises()
    expect(retryWrapper.text()).toContain('合同.pdf')
  })

  it('附件名称按钮支持 Enter/Space，关闭预览后焦点回到触发按钮', async () => {
    mockGet.mockResolvedValueOnce(VIEW)
    const wrapper = mount(AttachmentTabPanel, {
      props: { projectId: 'p1', wpId: 'w1' },
      global: { stubs },
      attachTo: document.body,
    })
    await flushPromises()
    const name = wrapper.find('button.gt-attach-tab__name')
    expect(name.attributes('type')).toBe('button')
    expect(name.attributes('aria-label')).toBe('预览附件 合同.pdf')
    expect(name.attributes('title')).toBe('预览 合同.pdf')
    expect(wrapper.find('.gt-attach-tab__item').attributes('role')).toBeUndefined()
    ;(name.element as HTMLElement).focus()

    await name.trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.find('[data-testid="preview-close"]').exists()).toBe(false)

    await name.trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('[data-attachment="a1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="preview-close"]').exists()).toBe(true)
    const close = wrapper.find('[data-testid="preview-close"]')
    ;(close.element as HTMLElement).focus()
    await close.trigger('click')
    await nextTick()
    expect(document.activeElement).toBe(name.element)

    await name.trigger('keydown', { key: ' ' })
    expect(wrapper.find('[data-testid="preview-close"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
