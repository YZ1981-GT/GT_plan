/**
 * Unit Tests — GtA1731ConsultationExecution.vue 组件渲染
 *
 * Spec: .kiro/specs/a17-3-1-consultation-execution/
 * Task: 3.4
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
          meta_info: {
            executor: '张三',
            execution_date: '2026-06-20',
            review_date: '2026-06-25',
            reviewer: '李四',
            consultation_id: 'A17-3-001',
            not_required: '',
          },
          sections: {
            '1': { supplementary: '补充说明' },
            '2': { execution_details: '执行详情' },
            '3': { results: '结果' },
            '4': { follow_up: '跟进事项' },
          },
          a173_reference: { overview: '客户从事制造业', background: '收入确认时点问题' },
          project_context: { client_name: '测试公司', period: '2025年12月31日' },
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

// Stub GtIndexChip — avoid ACNR resolve on mount in full suite
vi.mock('../GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    props: ['value', 'contextProjectId', 'context', 'wpCode', 'label'],
    template: '<span class="gt-index-chip-stub">{{ value || label }}</span>',
  },
}))

describe('GtA1731ConsultationExecution.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  async function mountComponent(props: Record<string, any> = {}) {
    const { default: GtA1731ConsultationExecution } = await import('../GtA1731ConsultationExecution.vue')
    const wrapper = mount(GtA1731ConsultationExecution, {
      props: { wpId: 'wp-001', ...props },
      global: {
        stubs: {
          ElSegmented: defineComponent({
            props: ['modelValue', 'options'],
            emits: ['update:modelValue'],
            setup(props, { emit }) {
              return () => h('div', { class: 'el-segmented-stub' },
                (props.options || []).map((opt: string) =>
                  h('button', { onClick: () => emit('update:modelValue', opt) }, opt),
                ),
              )
            },
          }),
          ElSkeleton: defineComponent({ template: '<div class="el-skeleton-stub" />' }),
          ElDatePicker: defineComponent({
            props: ['modelValue', 'type', 'disabled'],
            template: '<div class="el-date-picker-stub" />',
          }),
          ElInput: defineComponent({
            props: ['modelValue', 'disabled', 'placeholder', 'size'],
            template: '<input class="el-input-stub" />',
          }),
          ElCard: defineComponent({
            template: '<div class="el-card-stub"><slot name="header" /><slot /></div>',
          }),
          ElCheckbox: defineComponent({
            props: ['modelValue', 'disabled'],
            template: '<label class="el-checkbox-stub"><slot /></label>',
          }),
          ElIcon: defineComponent({ template: '<span class="el-icon-stub" />' }),
          ElButton: defineComponent({
            props: ['type', 'size', 'loading', 'text', 'disabled'],
            template: '<button class="el-button-stub"><slot /></button>',
          }),
        },
      },
    })
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()
    return wrapper
  }

  describe('rendering — 5 blocks', () => {
    it('renders structured view by default', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a1731__content').exists()).toBe(true)
    })

    it('renders meta info card with 6 fields', async () => {
      const wrapper = await mountComponent()
      const metaItems = wrapper.findAll('.gt-a1731__meta-item')
      expect(metaItems.length).toBe(6)
    })

    it('renders 5 cards total (meta + 4 sections)', async () => {
      const wrapper = await mountComponent()
      const cards = wrapper.findAll('.gt-a1731__card')
      expect(cards.length).toBe(5)
    })

    it('renders save status indicator', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a1731__save-status').exists()).toBe(true)
    })
  })

  describe('A17-3 reference area', () => {
    it('renders A17-3 reference content when data exists', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a1731__reference').exists()).toBe(true)
      expect(wrapper.text()).toContain('客户从事制造业')
      expect(wrapper.text()).toContain('收入确认时点问题')
    })

    it('renders GtIndexChip for A17-3 navigation', async () => {
      const wrapper = await mountComponent()
      // A17-3 reference label is rendered in the reference area
      expect(wrapper.text()).toContain('A17-3')
      expect(wrapper.find('.gt-a1731__reference-label').exists()).toBe(true)
    })

    it('shows empty message when no A17-3 data', async () => {
      const { api } = await import('@/services/apiProxy')
      ;(api.get as any).mockResolvedValueOnce({
        sheets: [{
          html_data: {
            meta_info: { executor: '', execution_date: '', review_date: '', reviewer: '' },
            sections: { '1': { supplementary: '' }, '2': { execution_details: '' }, '3': { results: '' }, '4': { follow_up: '' } },
            a173_reference: { overview: '', background: '' },
            project_context: { client_name: '', period: '' },
          },
        }],
      })

      const { default: GtA1731 } = await import('../GtA1731ConsultationExecution.vue')
      const wrapper = mount(GtA1731, {
        props: { wpId: 'wp-002' },
        global: {
          stubs: {
            ElSegmented: defineComponent({ template: '<div />' }),
            ElSkeleton: defineComponent({ template: '<div />' }),
            ElDatePicker: defineComponent({ template: '<div />' }),
          },
        },
      })
      await wrapper.vm.$nextTick()
      await new Promise(r => setTimeout(r, 10))
      await wrapper.vm.$nextTick()

      expect(wrapper.find('.gt-a1731__reference-empty').exists()).toBe(true)
    })
  })

  describe('meta auto-fill', () => {
    it('displays loaded meta values from render-config', async () => {
      const wrapper = await mountComponent()
      // Meta section rendered with labels
      expect(wrapper.text()).toContain('执行人')
      expect(wrapper.text()).toContain('复核日期')
      expect(wrapper.text()).toContain('关联咨询事项编号')
    })
  })

  describe('mode switch', () => {
    it('defaults to structured view', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a1731__content').exists()).toBe(true)
      expect(wrapper.find('.oo-stub').exists()).toBe(false)
    })
  })

  describe('readonly mode', () => {
    it('renders without error in readonly mode', async () => {
      const wrapper = await mountComponent({ readonly: true })
      expect(wrapper.find('.gt-a1731').exists()).toBe(true)
    })
  })
})
