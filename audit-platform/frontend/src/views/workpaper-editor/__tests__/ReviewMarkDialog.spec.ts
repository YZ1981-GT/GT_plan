import { describe, test, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'
import { EDITOR_CONTEXT_KEY, createMockEditorContext } from '@/composables/useEditorContext'

// ─── Mock composables ────────────────────────────────────────────────────────
const mockCreateReviewMark = vi.fn().mockResolvedValue({ id: 'mark-1' })

vi.mock('@/composables/useReviewMarks', () => ({
  useReviewMarks: () => ({
    createReviewMark: mockCreateReviewMark,
    marks: ref([]),
    loading: ref(false),
  }),
}))

vi.mock('@/composables/useFormSubmit', () => ({
  useFormSubmit: () => ({
    submit: async (action: () => Promise<void>) => { await action() },
    submitting: ref(false),
  }),
}))

// ─── Mock utils ──────────────────────────────────────────────────────────────
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

// ─── Import component ────────────────────────────────────────────────────────
import ReviewMarkDialog from '@/views/workpaper-editor/ReviewMarkDialog.vue'

describe('ReviewMarkDialog', () => {
  function mountComponent(props: Partial<InstanceType<typeof ReviewMarkDialog>['$props']> = {}) {
    const ctx = createMockEditorContext()
    return shallowMount(ReviewMarkDialog, {
      props: {
        projectId: 'proj-1',
        wpId: 'wp-1',
        visible: true,
        cell: { sheet: 'Sheet1', cellRef: 'A1' },
        ...props,
      },
      global: {
        provide: { [EDITOR_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          ElDialog: {
            template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>',
            props: ['modelValue', 'title', 'width'],
            emits: ['update:modelValue'],
          },
          ElForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
          ElFormItem: { template: '<div class="form-item"><slot /></div>', props: ['label', 'prop'] },
          ElRadioGroup: { template: '<div><slot /></div>' },
          ElRadio: { template: '<label><slot /></label>', props: ['value'] },
          ElInput: { template: '<input />', props: ['modelValue', 'type', 'rows', 'placeholder'] },
          ElButton: {
            template: '<button @click="$emit(\'click\')" :disabled="loading"><slot /></button>',
            props: ['type', 'loading'],
          },
        },
      },
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('默认渲染：显示表单和单元格信息', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    // dialog 应渲染
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(true)
    // 应显示单元格位置
    expect(wrapper.text()).toContain('Sheet1')
    expect(wrapper.text()).toContain('A1')
  })

  test('onMarkReview 提交后 emit marked 事件', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    // 找到确认按钮并点击
    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认标记'))
    expect(confirmBtn).toBeDefined()

    await confirmBtn!.trigger('click')
    await flushPromises()

    // 应调用 createReviewMark
    expect(mockCreateReviewMark).toHaveBeenCalledWith(
      'wp-1',
      'Sheet1',
      'A1',
      'reviewed', // 默认状态
      '',         // 默认空备注
    )

    // 应 emit 'marked' 事件
    const emitted = wrapper.emitted('marked')
    expect(emitted).toBeTruthy()
  })
})
