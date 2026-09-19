/**
 * Unit Tests — GtA91DeficiencyLetter.vue variant='governance' (A9-2)
 *
 * Spec: .kiro/specs/a9-2-deficiency-letter-governance/
 * Task: 2.8
 *
 * Coverage:
 * - variant governance hides Section 7
 * - variant governance hides general deficiency group
 * - addressee text shows 董事会 for governance
 * - itemIdPrefix generates a92-* item_ids
 * - navigation has 6 items for governance
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

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

const governanceHtmlData = {
  variant: 'governance',
  section_data: {
    addressee: { client_name: '治理层测试公司', custom_text: null },
    independence: {
      team_independent: 'Y',
      no_relationships: 'Y',
      no_relationships_detail: null,
      safeguards_taken: 'Y',
      non_audit_services: 'N',
      non_audit_services_detail: null,
    },
    committee: { applicability: 'N', description: null },
    signature: { date: '2026-07-01' },
    // No response key in governance mode
  },
  deficiency_list: {
    major: [{ id: 'def-m1', description: '重大缺陷', impact: '重大', recommendation: '整改', indexRef: 'B22B-001', source: 'b22b', severity: 'major' }],
    significant: [{ id: 'def-s1', description: '重要缺陷', impact: '较大', recommendation: '改进', indexRef: null, source: 'manual', severity: 'significant' }],
    // No general key
  },
  project_context: {
    client_name: '治理层测试公司',
    firm_name: '致同会计师事务所（特殊普通合伙）',
    audit_report_date: '2025年12月31日',
  },
  b22b_warning: null,
}

describe('GtA91DeficiencyLetter.vue — variant=governance (A9-2)', () => {
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

  async function mountGovernance(extraProps: Record<string, any> = {}) {
    const { default: GtA91DeficiencyLetter } = await import('../GtA91DeficiencyLetter.vue')
    const wrapper = mount(GtA91DeficiencyLetter, {
      props: {
        wpId: 'wp-a92-001',
        projectId: 'proj-001',
        htmlData: governanceHtmlData as any,
        variant: 'governance',
        ...extraProps,
      },
      global: { stubs: createStubs() },
    })
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()
    return wrapper
  }

  describe('Section 7 hidden in governance mode', () => {
    it('does not render section-response', async () => {
      const wrapper = await mountGovernance()
      expect(wrapper.find('#section-response').exists()).toBe(false)
    })

    it('still renders other 6 sections', async () => {
      const wrapper = await mountGovernance()
      expect(wrapper.find('#section-addressee').exists()).toBe(true)
      expect(wrapper.find('#section-intro').exists()).toBe(true)
      expect(wrapper.find('#section-independence').exists()).toBe(true)
      expect(wrapper.find('#section-deficiency').exists()).toBe(true)
      expect(wrapper.find('#section-committee').exists()).toBe(true)
      expect(wrapper.find('#section-signature').exists()).toBe(true)
    })

    it('does not show management response fields', async () => {
      const wrapper = await mountGovernance()
      const text = wrapper.text()
      expect(text).not.toContain('管理层意见')
      expect(text).not.toContain('管理层结论')
      expect(text).not.toContain('授权代表签字')
    })
  })

  describe('一般缺陷 hidden in governance mode', () => {
    it('does not show 一般缺陷 severity group header', async () => {
      const wrapper = await mountGovernance()
      const headers = wrapper.findAll('.gt-a91__severity-header')
      const labels = headers.map(h => h.text())
      expect(labels.some(l => l.includes('一般缺陷'))).toBe(false)
    })

    it('shows only 2 severity groups (major + significant)', async () => {
      const wrapper = await mountGovernance()
      const headers = wrapper.findAll('.gt-a91__severity-header')
      expect(headers).toHaveLength(2)
      const allText = headers.map(h => h.text()).join(' ')
      expect(allText).toContain('重大缺陷')
      expect(allText).toContain('重要缺陷')
    })
  })

  describe('addressee text for governance', () => {
    it('displays 董事会\\监事会\\审计委员会 for governance variant', async () => {
      const wrapper = await mountGovernance()
      const addressee = wrapper.find('#section-addressee')
      const text = addressee.text()
      expect(text).toContain('董事会')
      expect(text).toContain('监事会')
      expect(text).toContain('审计委员会')
      expect(text).not.toContain('总经理')
    })

    it('displays 总经理 for management variant (default)', async () => {
      const { default: GtA91DeficiencyLetter } = await import('../GtA91DeficiencyLetter.vue')
      const managementData = {
        ...governanceHtmlData,
        section_data: {
          ...governanceHtmlData.section_data,
          response: { opinion: null, conclusion: null, representative: null, response_date: null },
        },
        deficiency_list: {
          ...governanceHtmlData.deficiency_list,
          general: [],
        },
      }
      const wrapper = mount(GtA91DeficiencyLetter, {
        props: {
          wpId: 'wp-a91-001',
          projectId: 'proj-001',
          htmlData: managementData as any,
          variant: 'management',
        },
        global: { stubs: createStubs() },
      })
      await wrapper.vm.$nextTick()
      await new Promise(r => setTimeout(r, 10))
      await wrapper.vm.$nextTick()
      const addressee = wrapper.find('#section-addressee')
      const text = addressee.text()
      expect(text).toContain('总经理')
      expect(text).not.toContain('董事会')
    })
  })

  describe('navigation for governance', () => {
    it('shows 6 nav items (no 回复)', async () => {
      const wrapper = await mountGovernance()
      const navItems = wrapper.findAll('.gt-a91__nav-item')
      expect(navItems).toHaveLength(6)
    })

    it('nav items do not include 回复', async () => {
      const wrapper = await mountGovernance()
      const navItems = wrapper.findAll('.gt-a91__nav-item')
      const labels = navItems.map(n => n.text())
      expect(labels).not.toContain('回复')
      expect(labels).toContain('收件人')
      expect(labels).toContain('签发')
    })
  })

  describe('itemIdPrefix generates a92-* item_ids', () => {
    it('buildItemId with a92 prefix produces correct format', async () => {
      const { buildItemId } = await import('../composables/useA91DeficiencyLetter')
      expect(buildItemId('addressee', 'client_name', 'a92')).toBe('a92-addressee-client_name')
      expect(buildItemId('independence', 'team_independent', 'a92')).toBe('a92-independence-team_independent')
      expect(buildItemId('deficiency', 'major', 'a92')).toBe('a92-deficiency-major')
      expect(buildItemId('committee', 'applicability', 'a92')).toBe('a92-committee-applicability')
      expect(buildItemId('signature', 'date', 'a92')).toBe('a92-signature-date')
    })

    it('buildItemId default prefix remains a91', async () => {
      const { buildItemId } = await import('../composables/useA91DeficiencyLetter')
      expect(buildItemId('addressee', 'client_name')).toBe('a91-addressee-client_name')
    })
  })
})
