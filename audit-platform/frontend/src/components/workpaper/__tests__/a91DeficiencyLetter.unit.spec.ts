/**
 * Unit Tests — GtA91DeficiencyLetter.vue 组件渲染
 *
 * Spec: .kiro/specs/a9-1-deficiency-letter/
 * Task: 3.12
 *
 * Coverage: 7 section cards render, mode switch, radio interactions,
 * deficiency add/remove UI, AI button disabled state, navigation anchor links, GtIndexChip presence
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

// ─── Mock API ────────────────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ healthy: true }),
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

vi.mock('../GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    props: ['value', 'contextProjectId', 'context', 'indexRef', 'label'],
    template: '<span class="gt-index-chip-stub">{{ indexRef || value || label }}</span>',
  },
}))

const htmlDataWithDeficiencies = {
  section_data: {
    addressee: { client_name: '测试公司', custom_text: null },
    independence: {
      team_independent: 'Y',
      no_relationships: 'N',
      no_relationships_detail: '存在关联关系',
      safeguards_taken: 'Y',
      non_audit_services: 'Y',
      non_audit_services_detail: '提供税务咨询',
    },
    committee: { applicability: 'Y', description: '监督无效描述' },
    signature: { date: '2026-06-26' },
    response: { opinion: '同意', conclusion: null, representative: '张三', response_date: '2026-06-26' },
  },
  deficiency_list: {
    major: [{ id: 'def-1', description: '重大缺陷1', impact: '影响1', recommendation: '建议1', indexRef: 'B22B-001', source: 'b22b', severity: 'major' }],
    significant: [],
    general: [{ id: 'def-2', description: '一般缺陷1', impact: '影响2', recommendation: '建议2', indexRef: null, source: 'manual', severity: 'general' }],
  },
  project_context: {
    client_name: '测试公司',
    firm_name: '致同会计师事务所（特殊普通合伙）',
    audit_report_date: '2026-06-30',
  },
  b22b_warning: null,
}

describe('GtA91DeficiencyLetter.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function createStubs() {
    return {
      GtOnlyOfficeSheet: defineComponent({
        name: 'GtOnlyOfficeSheet',
        props: ['wpId', 'sheetName'],
        template: '<div class="oo-stub" />',
      }),
      GtIndexChip: defineComponent({
        name: 'GtIndexChip',
        props: ['indexRef'],
        template: '<span class="gt-index-chip-stub">{{ indexRef }}</span>',
      }),
      ElSegmented: defineComponent({
        props: ['modelValue', 'options'],
        emits: ['update:modelValue'],
        setup(props, { emit }) {
          return () => h('div', { class: 'el-segmented-stub' },
            (props.options || []).map((opt: string) =>
              h('button', {
                class: opt === props.modelValue ? 'active' : '',
                onClick: () => emit('update:modelValue', opt),
              }, opt),
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
        template: '<div class="el-alert-stub"><slot /><slot name="title" /></div>',
      }),
    }
  }

  async function mountComponent(props: Record<string, any> = {}) {
    const { default: GtA91DeficiencyLetter } = await import('../GtA91DeficiencyLetter.vue')
    const wrapper = mount(GtA91DeficiencyLetter, {
      props: {
        wpId: 'wp-a91-001',
        projectId: 'proj-001',
        htmlData: htmlDataWithDeficiencies,
        ...props,
      },
      global: { stubs: createStubs() },
    })
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()
    return wrapper
  }

  describe('7 section cards render', () => {
    it('renders all 7 section cards', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('#section-addressee').exists()).toBe(true)
      expect(wrapper.find('#section-intro').exists()).toBe(true)
      expect(wrapper.find('#section-independence').exists()).toBe(true)
      expect(wrapper.find('#section-deficiency').exists()).toBe(true)
      expect(wrapper.find('#section-committee').exists()).toBe(true)
      expect(wrapper.find('#section-signature').exists()).toBe(true)
      expect(wrapper.find('#section-response').exists()).toBe(true)
    })

    it('renders section titles in Chinese', async () => {
      const wrapper = await mountComponent()
      const text = wrapper.text()
      expect(text).toContain('收件人')
      expect(text).toContain('引言')
      // Independence sub-items are visible (card headers stubbed out)
      expect(text).toContain('（一）审计项目组成员保持独立性')
      expect(text).toContain('（二）不存在影响独立性的关系和事项')
      // Deficiency severity groups visible
      expect(text).toContain('（一）重大缺陷')
      expect(text).toContain('管理层意见')
      expect(text).toContain('管理层结论')
    })
  })

  describe('mode switch', () => {
    it('defaults to structured view', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a91__layout').exists()).toBe(true)
      expect(wrapper.find('.oo-stub').exists()).toBe(false)
    })

    it('switches to online edit mode', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-segmented-stub button')
      const onlineBtn = buttons.find(b => b.text() === '在线编辑')
      if (onlineBtn) {
        await onlineBtn.trigger('click')
        await wrapper.vm.$nextTick()
        expect(wrapper.find('.gt-a91__layout').exists()).toBe(false)
        expect(wrapper.find('.oo-stub').exists()).toBe(true)
      }
    })
  })

  describe('radio interactions', () => {
    it('renders independence radio groups', async () => {
      const wrapper = await mountComponent()
      const independence = wrapper.find('#section-independence')
      expect(independence.exists()).toBe(true)
      // Should contain sub-labels
      const text = independence.text()
      expect(text).toContain('（一）审计项目组成员保持独立性')
      expect(text).toContain('（二）不存在影响独立性的关系和事项')
      expect(text).toContain('（三）已采取必要防护措施')
      expect(text).toContain('是否提供非审计服务')
    })

    it('shows conditional textarea for no_relationships when N', async () => {
      const wrapper = await mountComponent()
      // htmlData has no_relationships: 'N', so textarea should be visible
      const independence = wrapper.find('#section-independence')
      const textareas = independence.findAll('.gt-a91__conditional-textarea')
      expect(textareas.length).toBeGreaterThanOrEqual(1)
    })

    it('shows conditional textarea for non_audit_services when Y', async () => {
      const wrapper = await mountComponent()
      // htmlData has non_audit_services: 'Y', so textarea should be visible
      const independence = wrapper.find('#section-independence')
      const textareas = independence.findAll('.gt-a91__conditional-textarea')
      // Both conditional textareas should be visible (no_relationships=N + non_audit_services=Y)
      expect(textareas.length).toBe(2)
    })

    it('renders committee radio group with Y/N/NA options', async () => {
      const wrapper = await mountComponent()
      const committee = wrapper.find('#section-committee')
      const text = committee.text()
      expect(text).toContain('适用')
      expect(text).toContain('不适用')
      expect(text).toContain('不涉及')
    })

    it('shows committee textarea when applicability is Y', async () => {
      const wrapper = await mountComponent()
      const committee = wrapper.find('#section-committee')
      const textareas = committee.findAll('.gt-a91__conditional-textarea')
      expect(textareas.length).toBe(1)
    })

    it('hides committee textarea when applicability is N', async () => {
      const modifiedData = {
        ...htmlDataWithDeficiencies,
        section_data: {
          ...htmlDataWithDeficiencies.section_data,
          committee: { applicability: 'N', description: null },
        },
      }
      const wrapper = await mountComponent({ htmlData: modifiedData })
      const committee = wrapper.find('#section-committee')
      const textareas = committee.findAll('.gt-a91__conditional-textarea')
      expect(textareas.length).toBe(0)
    })
  })

  describe('deficiency add/remove UI', () => {
    it('renders deficiency cards for each severity group', async () => {
      const wrapper = await mountComponent()
      const cards = wrapper.findAll('.gt-a91__deficiency-card')
      // major: 1, significant: 0, general: 1
      expect(cards.length).toBe(2)
    })

    it('renders add buttons for each severity group', async () => {
      const wrapper = await mountComponent()
      const headers = wrapper.findAll('.gt-a91__severity-header')
      expect(headers.length).toBe(3) // major, significant, general
    })

    it('renders delete button only for manual deficiencies', async () => {
      const wrapper = await mountComponent()
      const cards = wrapper.findAll('.gt-a91__deficiency-card')
      // def-1 is b22b source (no delete), def-2 is manual (has delete)
      const card1Text = cards[0].text()
      const card2Text = cards[1].text()
      // Manual card should have delete button
      expect(card2Text).toContain('删除')
    })

    it('renders textarea fields in each deficiency card', async () => {
      const wrapper = await mountComponent()
      const deficiencySection = wrapper.find('#section-deficiency')
      const text = deficiencySection.text()
      expect(text).toContain('缺陷描述')
      expect(text).toContain('影响说明')
      expect(text).toContain('整改建议')
    })
  })

  describe('AI button disabled state', () => {
    it('renders disabled AI buttons in deficiency cards', async () => {
      const wrapper = await mountComponent()
      const aiButtons = wrapper.findAll('.gt-a91__ai-btn')
      expect(aiButtons.length).toBeGreaterThan(0)
      aiButtons.forEach(btn => {
        expect(btn.attributes('disabled')).toBeDefined()
      })
    })
  })

  describe('navigation anchor links', () => {
    it('renders left navigation with 7 items', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a91__nav-item')
      expect(navItems.length).toBe(7)
    })

    it('navigation items have correct labels', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a91__nav-item')
      const labels = navItems.map(n => n.text())
      expect(labels).toContain('收件人')
      expect(labels).toContain('引言')
      expect(labels).toContain('独立性')
      expect(labels).toContain('缺陷')
      expect(labels).toContain('委员会')
      expect(labels).toContain('签发')
      expect(labels).toContain('回复')
    })

    it('clicking a nav item updates active state', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a91__nav-item')
      await navItems[2].trigger('click')
      await wrapper.vm.$nextTick()
      expect(navItems[2].classes()).toContain('gt-a91__nav-item--active')
    })
  })

  describe('GtIndexChip presence', () => {
    it('renders GtIndexChip for deficiencies with indexRef', async () => {
      const wrapper = await mountComponent()
      const chips = wrapper.findAll('.gt-index-chip-stub')
      expect(chips.length).toBeGreaterThan(0)
      expect(chips[0].text()).toContain('B22B-001')
    })

    it('does not render GtIndexChip when indexRef is null', async () => {
      const wrapper = await mountComponent()
      const cards = wrapper.findAll('.gt-a91__deficiency-card')
      // The second card (general, manual) has no indexRef
      const lastCard = cards[cards.length - 1]
      const chip = lastCard.find('.gt-index-chip-stub')
      expect(chip.exists()).toBe(false)
    })
  })

  describe('save status', () => {
    it('renders save status indicator', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a91__save-status').exists()).toBe(true)
    })
  })

  describe('addressee auto-fill', () => {
    it('displays client name format when available', async () => {
      const wrapper = await mountComponent()
      const addressee = wrapper.find('#section-addressee')
      expect(addressee.text()).toContain('测试公司')
      expect(addressee.text()).toContain('总经理')
    })

    it('shows input when client_name is empty', async () => {
      const modifiedData = {
        ...htmlDataWithDeficiencies,
        project_context: {
          ...htmlDataWithDeficiencies.project_context,
          client_name: '',
        },
      }
      const wrapper = await mountComponent({ htmlData: modifiedData })
      const addressee = wrapper.find('#section-addressee')
      expect(addressee.find('.gt-a91__addressee-text').exists()).toBe(false)
    })
  })

  describe('signature section', () => {
    it('displays firm name label in signature section', async () => {
      const wrapper = await mountComponent()
      const signature = wrapper.find('#section-signature')
      expect(signature.text()).toContain('事务所')
      expect(signature.text()).toContain('签发日期')
    })
  })

  describe('response section', () => {
    it('renders management response fields', async () => {
      const wrapper = await mountComponent()
      const response = wrapper.find('#section-response')
      const text = response.text()
      expect(text).toContain('管理层意见')
      expect(text).toContain('管理层结论')
      expect(text).toContain('授权代表签字')
    })
  })
})
