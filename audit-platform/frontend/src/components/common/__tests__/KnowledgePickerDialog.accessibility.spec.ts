import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const state = vi.hoisted(() => ({
  search: vi.fn(),
  searchStatus: { value: 'idle' as string },
  searchError: { value: '' },
  options: { value: { title: '选择知识库文档', maxSelect: 5 } },
  resolve: vi.fn(),
  reject: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('@/composables/useKnowledge', () => ({
  useKnowledge: () => ({
    search: state.search,
    searchStatus: state.searchStatus,
    searchError: state.searchError,
  }),
  knowledgePickerOptions: state.options,
  _resolvePickerSelection: state.resolve,
  _rejectPickerSelection: state.reject,
}))
vi.mock('@element-plus/icons-vue', () => ({ Loading: { render: () => null } }))

import KnowledgePickerDialog from '../KnowledgePickerDialog.vue'

const InputStub = defineComponent({
  props: { modelValue: { type: String, default: '' }, size: String },
  emits: ['update:modelValue'],
  setup(props, { emit, expose, attrs }) {
    const input = ref<HTMLInputElement | null>(null)
    expose({ focus: () => input.value?.focus() })
    return () => h('input', {
      ref: input,
      value: props.modelValue,
      'aria-label': attrs['aria-label'],
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
    })
  },
})

const DialogStub = defineComponent({
  props: { modelValue: Boolean, title: String },
  setup(props, { slots }) {
    return () => props.modelValue ? h('div', { class: 'el-dialog' }, [slots.default?.(), slots.footer?.()]) : null
  },
})

const ButtonStub = defineComponent({
  inheritAttrs: false,
  props: { disabled: Boolean, loading: Boolean },
  emits: ['click'],
  setup(props, { attrs, emit, slots }) {
    return () => h('button', {
      type: 'button',
      disabled: props.disabled,
      'aria-label': attrs['aria-label'],
      title: attrs.title,
      onClick: (event: MouseEvent) => emit('click', event),
    }, slots.default?.())
  },
})

const stubs = {
  'el-dialog': DialogStub,
  'el-input': InputStub,
  'el-button': ButtonStub,
  'el-table': true,
  'el-table-column': true,
  'el-empty': true,
  'el-icon': true,
}

beforeEach(() => {
  vi.clearAllMocks()
  state.searchStatus.value = 'idle'
  state.searchError.value = ''
  state.options.value = { title: '选择知识库文档', maxSelect: 5 }
  state.search.mockResolvedValue([])
})

describe('KnowledgePickerDialog 键盘与焦点', () => {
  it('打开后聚焦搜索框，Enter 发起搜索，按钮保留中文可读名', async () => {
    const wrapper = mount(KnowledgePickerDialog, {
      attachTo: document.body,
      props: { visible: true },
      global: { stubs },
    })
    await nextTick()

    const input = wrapper.find('input[aria-label="搜索知识库文档"]')
    expect(document.activeElement).toBe(input.element)
    const searchButton = wrapper.find('button[aria-label="搜索知识库文档"]')
    expect(searchButton.attributes('type')).toBe('button')
    expect(searchButton.attributes('title')).toBe('搜索知识库文档')

    await input.setValue('合同')
    await input.trigger('keyup', { key: 'Enter' })
    await flushPromises()
    expect(state.search).toHaveBeenCalledWith('合同', '')
    wrapper.unmount()
  })
})
