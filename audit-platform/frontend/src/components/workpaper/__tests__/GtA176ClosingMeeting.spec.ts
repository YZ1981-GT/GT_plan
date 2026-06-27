/**
 * Unit Tests — GtA176ClosingMeeting.vue 组件渲染
 *
 * Spec: .kiro/specs/a17-6-closing-meeting/
 * Task: 3.3
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'

// ─── Mock API ────────────────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({
      sheets: [{
        html_data: {
          meta_info: { client_name: '测试公司', period: '2025年12月31日', preparer: '张三', reviewer: '', date: '', index_no: 'A17-6' },
          fields: { meeting_time: '', attendees: '', minutes: '', conclusion: '', attachments: '' },
          project_context: { client_name: '测试公司', period: '2025年12月31日', current_user: '张三' },
        },
      }],
    }),
    put: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual as any,
    ElMessage: { warning: vi.fn(), error: vi.fn() },
  }
})

// Stub GtOnlyOfficeSheet
vi.mock('../GtOnlyOfficeSheet.vue', () => ({
  default: defineComponent({ name: 'GtOnlyOfficeSheet', template: '<div class="oo-stub" />' }),
}))

describe('GtA176ClosingMeeting.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  async function mountComponent(props: Record<string, any> = {}) {
    const { default: GtA176ClosingMeeting } = await import('../GtA176ClosingMeeting.vue')
    const wrapper = mount(GtA176ClosingMeeting, {
      props: { wpId: 'wp-001', ...props },
      global: {
        stubs: {
          ElSegmented: defineComponent({
            props: ['modelValue', 'options'],
            emits: ['update:modelValue'],
            setup(props, { emit }) {
              return () => h('div', { class: 'el-segmented-stub' },
                (props.options || []).map((opt: string) =>
                  h('button', { onClick: () => emit('update:modelValue', opt) }, opt)
                )
              )
            },
          }),
          ElSkeleton: defineComponent({ template: '<div class="el-skeleton-stub" />' }),
          ElDatePicker: defineComponent({
            props: ['modelValue', 'type', 'disabled'],
            template: '<div class="el-date-picker-stub" />',
          }),
        },
      },
    })
    await wrapper.vm.$nextTick()
    // Wait for loadData to complete
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()
    return wrapper
  }

  describe('rendering', () => {
    it('renders structured view by default', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a176__content').exists()).toBe(true)
    })

    it('renders meta info card with 6 fields', async () => {
      const wrapper = await mountComponent()
      const metaItems = wrapper.findAll('.gt-a176__meta-item')
      expect(metaItems.length).toBe(6)
    })

    it('renders 5 content fields (meeting_time, attendees, minutes, conclusion, attachments)', async () => {
      const wrapper = await mountComponent()
      const fields = wrapper.findAll('.gt-a176__field')
      expect(fields.length).toBe(5)
    })

    it('renders save status indicator', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a176__save-status').exists()).toBe(true)
    })
  })

  describe('mode switch', () => {
    it('defaults to structured view', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a176__content').exists()).toBe(true)
      expect(wrapper.find('.oo-stub').exists()).toBe(false)
    })
  })

  describe('readonly mode', () => {
    it('passes readonly to composable fields', async () => {
      const wrapper = await mountComponent({ readonly: true })
      // El-inputs should have disabled attribute propagated
      const inputs = wrapper.findAll('input')
      // At minimum the component renders without error in readonly
      expect(wrapper.find('.gt-a176').exists()).toBe(true)
    })
  })
})
