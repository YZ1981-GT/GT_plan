import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, type PropType } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api }))

import ChatProjectAttachmentPicker from '../ChatProjectAttachmentPicker.vue'

const Button = defineComponent({
  props: { disabled: Boolean }, emits: ['click'],
  setup: (p, { emit, slots }) => () => h('button', { disabled: p.disabled, onClick: () => emit('click') }, slots.default?.()),
})
const Dialog = defineComponent({
  props: { modelValue: Boolean },
  setup: (p, { slots }) => () => p.modelValue ? h('div', { class: 'dialog' }, [slots.default?.(), slots.footer?.()]) : null,
})
const Select = defineComponent({
  props: { modelValue: { type: Array as PropType<string[]>, default: () => [] } },
  emits: ['update:modelValue'],
  setup: (p, { emit, slots }) => () => h('div', { class: 'select' }, [
    slots.default?.(),
    h('button', { class: 'choose', onClick: () => emit('update:modelValue', ['att-1']) }, '选择'),
  ]),
})
const Option = defineComponent({
  props: { label: String, value: String, disabled: Boolean },
  setup: (p) => () => h('span', { class: 'option', 'data-disabled': p.disabled }, p.label),
})
const stubs = {
  'el-button': Button, 'el-dialog': Dialog, 'el-select': Select, 'el-option': Option,
  'el-alert': defineComponent({ props: { title: String }, setup: (p) => () => h('div', { class: 'alert' }, p.title) }),
  'el-empty': defineComponent({ props: { description: String }, setup: (p) => () => h('div', { class: 'empty' }, p.description) }),
}

beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockResolvedValue({ items: [
    { id: 'att-1', file_name: '回函.pdf', attachment_type: 'confirmation', state: 'available' },
    { id: 'att-2', file_name: '处理中.pdf', state: 'pending' },
  ], total: 2 })
})

describe('ChatProjectAttachmentPicker', () => {
  it('按项目只加载一次、禁用不可用行并提交稳定附件 ID', async () => {
    const wrapper = mount(ChatProjectAttachmentPicker, {
      props: { projectId: 'project-1' }, global: { stubs },
    })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith('/api/projects/project-1/attachments', {
      params: { page: 1, page_size: 200 }, _silent: true,
    })
    expect(wrapper.text()).toContain('回函.pdf · confirmation')
    expect(wrapper.findAll('.option')[1].attributes('data-disabled')).toBe('true')
    await wrapper.find('button.choose').trigger('click')
    const confirm = wrapper.findAll('button').find((button) => button.text() === '确定')!
    await confirm.trigger('click')
    expect(wrapper.emitted('change')?.at(-1)).toEqual([['att-1']])

    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(1)
  })

  it('加载失败显示错误而非伪装空列表，并允许重试', async () => {
    api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ items: [], total: 0 })
    const wrapper = mount(ChatProjectAttachmentPicker, {
      props: { projectId: 'project-1' }, global: { stubs },
    })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.alert').some((node) => node.text().includes('附件列表加载失败'))).toBe(true)
    expect(wrapper.find('.empty').exists()).toBe(false)
    const retry = wrapper.findAll('button').find((button) => button.text() === '重试')!
    await retry.trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.empty').text()).toContain('暂无可用项目附件')
  })
})
