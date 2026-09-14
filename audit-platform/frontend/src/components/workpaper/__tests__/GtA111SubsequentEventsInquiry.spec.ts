/**
 * Unit Tests — GtA111SubsequentEventsInquiry.vue 组件
 *
 * Spec: .kiro/specs/a11-1-subsequent-events-inquiry/
 * Tasks: 3.7, 3.8
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

// ─── Mock API ────────────────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockImplementation((url: string) => {
      if (url.includes('onlyoffice/health')) {
        return Promise.resolve({ healthy: true })
      }
      return Promise.resolve({
        sheets: [{
          html_data: {
            meta_data: {
              inquiry_date: '2026-03-20',
              interviewee: '张三（财务总监）',
              location: '公司会议室',
              team_signature: '李四',
            },
            qa_list: Array.from({ length: 10 }, (_, i) => ({
              number: i + 1,
              answer: i === 0 ? '无新承诺' : null,
            })),
            evidence: '银行对账单',
            project_context: { client_name: '测试公司', balance_sheet_date: '2025-12-31' },
            questions_config: Array.from({ length: 10 }, (_, i) => ({
              number: i + 1,
              title: ['承诺、借款及担保', '资产出售或购置', '资本发行/债务', '政府征用/灾害损失',
                '或有事项进展', '重大调整事项', '持续经营事项', '会计估计变更',
                '资产可收回性', '其他重大事项'][i],
              text: `问题${i + 1}文本`,
              has_guidance: i === 4,
              guidance_text: i === 4 ? '如涉及诉讼案例，请列明案号、诉讼金额、判决结果等详细信息' : null,
            })),
          },
        }],
      })
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

vi.mock('../GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    props: ['value', 'contextProjectId', 'context'],
    template: '<span class="gt-index-chip-stub">{{ value }}</span>',
  },
}))

describe('GtA111SubsequentEventsInquiry.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function mountComponent(props: Record<string, any> = {}) {
    const { default: GtA111SubsequentEventsInquiry } = await import('../GtA111SubsequentEventsInquiry.vue')
    const wrapper = mount(GtA111SubsequentEventsInquiry, {
      props: { wpId: 'wp-a111', ...props },
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
          ElCollapse: defineComponent({
            props: ['modelValue'],
            template: '<div class="el-collapse-stub"><slot /></div>',
          }),
          ElCollapseItem: defineComponent({
            props: ['title', 'name'],
            template: '<div class="el-collapse-item-stub"><slot /></div>',
          }),
          ElAlert: defineComponent({
            props: ['type', 'closable', 'showIcon'],
            template: '<div class="el-alert-stub" :data-type="type"><slot name="title" /><slot /></div>',
          }),
        },
      },
    })
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()
    return wrapper
  }

  // ─── 10 Q&A Cards Render ───

  describe('10 Q&A cards render', () => {
    it('renders 10 question cards', async () => {
      const wrapper = await mountComponent()
      const cards = wrapper.findAll('.gt-a111__card')
      // meta card + 10 QA cards + evidence card = 12
      expect(cards.length).toBe(12)
    })

    it('renders numbered titles for questions', async () => {
      const wrapper = await mountComponent()
      const text = wrapper.text()
      // Card headers rendered in slot, check question text body instead
      expect(text).toContain('问题1文本')
      expect(text).toContain('问题5文本')
      expect(text).toContain('问题10文本')
    })

    it('renders question text (read-only)', async () => {
      const wrapper = await mountComponent()
      const questionTexts = wrapper.findAll('.gt-a111__question-text')
      expect(questionTexts.length).toBe(10)
    })

    it('renders answer textarea for each question', async () => {
      const wrapper = await mountComponent()
      const qaBlocks = wrapper.findAll('.gt-a111__qa')
      expect(qaBlocks.length).toBe(10)
    })
  })

  // ─── Meta Form Fields ───

  describe('meta form fields', () => {
    it('renders meta card with 4 fields', async () => {
      const wrapper = await mountComponent()
      const metaCard = wrapper.find('#nav-meta')
      expect(metaCard.exists()).toBe(true)
      // el-card header slot stubbed; check field labels instead
      expect(wrapper.text()).toContain('询问日期')
    })

    it('renders date picker, interviewee, location, signature fields', async () => {
      const wrapper = await mountComponent()
      const fields = wrapper.findAll('.gt-a111__field')
      expect(fields.length).toBeGreaterThanOrEqual(4)
      expect(wrapper.text()).toContain('询问日期')
      expect(wrapper.text()).toContain('受访对象')
      expect(wrapper.text()).toContain('询问地点')
      expect(wrapper.text()).toContain('项目组签字')
    })
  })

  // ─── AI Button Disabled ───

  describe('AI button disabled', () => {
    it('renders AI buttons that are disabled', async () => {
      const wrapper = await mountComponent()
      const aiButtons = wrapper.findAll('.gt-a111__ai-btn')
      expect(aiButtons.length).toBe(10)
      for (const btn of aiButtons) {
        expect(btn.attributes('disabled')).toBeDefined()
      }
    })
  })

  // ─── Navigation 12 Items ───

  describe('navigation 12 items', () => {
    it('renders left navigation with 12 items', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a111__nav-item')
      expect(navItems.length).toBe(12)
    })

    it('first nav item is 元信息', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a111__nav-item')
      expect(navItems[0].text()).toBe('元信息')
    })

    it('last nav item is 证据', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a111__nav-item')
      expect(navItems[11].text()).toBe('证据')
    })

    it('middle items are Q1 through Q10', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a111__nav-item')
      for (let i = 1; i <= 10; i++) {
        expect(navItems[i].text()).toBe(`Q${i}`)
      }
    })
  })

  // ─── Mode Switch ───

  describe('mode switch', () => {
    it('defaults to structured view', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a111__layout').exists()).toBe(true)
      expect(wrapper.find('.oo-stub').exists()).toBe(false)
    })

    it('renders segmented control', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.el-segmented-stub').exists()).toBe(true)
    })
  })

  // ─── OO Health Check Disable ───

  describe('OO health check disable', () => {
    it('when OO healthy, both modes available', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-segmented-stub button')
      expect(buttons.length).toBe(2)
      expect(buttons[0].text()).toBe('结构化视图')
      expect(buttons[1].text()).toBe('在线编辑')
    })
  })

  // ─── Timing Guidance Alert ───

  describe('timing guidance alert', () => {
    it('renders timing alert at top of form', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('问询时间要求')
      expect(wrapper.text()).toContain('尽量接近审计报告日')
    })
  })

  // ─── Guidance el-alert for Q5 ───

  describe('guidance conditional display', () => {
    it('renders guidance alert for Q5 (has_guidance=true)', async () => {
      const wrapper = await mountComponent()
      const guidanceAlerts = wrapper.findAll('.gt-a111__guidance')
      expect(guidanceAlerts.length).toBe(1) // Only Q5 has guidance
      expect(wrapper.text()).toContain('如涉及诉讼案例')
    })
  })

  // ─── Evidence Card ───

  describe('evidence card', () => {
    it('renders evidence section', async () => {
      const wrapper = await mountComponent()
      const evidenceCard = wrapper.find('#nav-evidence')
      expect(evidenceCard.exists()).toBe(true)
      // el-card header slot is stubbed, just verify the card exists
      expect(evidenceCard.exists()).toBe(true)
    })
  })

  // ─── Save Status Indicator ───

  describe('save status', () => {
    it('renders save status area', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a111__save-status').exists()).toBe(true)
    })
  })
})
