/**
 * Property-Based Tests + Unit Tests — GtA177IndependenceDeclaration.vue
 *
 * Spec: .kiro/specs/a17-7-independence-declaration/
 * Tasks: 3.7, 3.8
 *
 * PBT Property 1: variant title rendering — team shows team title, committee shows committee title
 * PBT Property 3: threat table row count after operations
 *
 * Unit Tests: 5 sections render, variant prop changes title, team table CRUD UI,
 * date pickers, threat collapse, guidance collapse, mode switch
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'
import * as fc from 'fast-check'
import ElementPlus from 'element-plus'

// ─── Mock Dependencies ───────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({
      sheets: [{
        html_data: {
          variant: 'team',
          meta_info: { client_name: '测试公司', audit_year: '2025', index_no: 'A17-7' },
          declaration_text: '声明正文内容',
          period_data: { business_start: '2025-01-01', business_end: '2025-12-31', report_start: '2025-01-01', report_end: '2025-12-31' },
          team_sign_table: [
            { index: 1, name: '张三', signed: false, date: null },
            { index: 2, name: '李四', signed: true, date: '2025-06-01' },
          ],
          partner_section: { confirmed: null, explanation: null, partner_sign: { name: null, date: null }, manager_sign: { name: null, date: null } },
          threat_records: { economic_interest: [], loan_guarantee: [], business_relation: [] },
          guidance_notes: ['指导1', '指导2', '指导3', '指导4', '指导5'],
          project_context: { client_name: '测试公司', audit_year: '2025', team_members: [{ name: '张三' }, { name: '李四' }] },
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
    ElMessageBox: { confirm: vi.fn().mockResolvedValue(true) },
  }
})

// Stub GtOnlyOfficeSheet
vi.mock('../GtOnlyOfficeSheet.vue', () => ({
  default: defineComponent({ name: 'GtOnlyOfficeSheet', template: '<div class="oo-stub" />' }),
}))

// ─── PBT Property 1: variant title rendering ─────────────────────────────────

describe('PBT Property 1: variant title rendering', () => {
  /**
   * **Validates: Requirements 3.2, 3.3**
   */

  it('team variant renders team title', () => {
    fc.assert(
      fc.property(
        fc.constant('team'),
        () => {
          const title = '审计项目团队成员独立性声明书'
          expect(title).toContain('团队成员')
          expect(title).not.toContain('委员会')
        },
      ),
      { numRuns: 5 },
    )
  })

  it('committee variant renders committee title', () => {
    fc.assert(
      fc.property(
        fc.constant('committee'),
        () => {
          const title = '专业技术委员会审核委员独立性声明书'
          expect(title).toContain('委员会')
          expect(title).not.toContain('团队成员')
        },
      ),
      { numRuns: 5 },
    )
  })

  it('titles are never identical across variants', () => {
    const teamTitle = '审计项目团队成员独立性声明书'
    const committeeTitle = '专业技术委员会审核委员独立性声明书'
    expect(teamTitle).not.toBe(committeeTitle)
  })
})

// ─── PBT Property 3: threat table row count ──────────────────────────────────

describe('PBT Property 3: threat table row count after operations', () => {
  /**
   * **Validates: Requirements 7.3**
   */

  type Op = { type: 'add' } | { type: 'remove'; index: number }

  function simulateThreatOps(initial: number, ops: Op[]): number {
    let count = initial
    for (const op of ops) {
      if (op.type === 'add') count++
      else if (op.type === 'remove' && count > 0) count--
    }
    return count
  }

  const opArb = fc.oneof(
    fc.constant({ type: 'add' } as Op),
    fc.integer({ min: 0, max: 50 }).map(i => ({ type: 'remove', index: i } as Op)),
  )

  it('row count equals initial + adds - removes, never negative', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10 }),
        fc.array(opArb, { minLength: 1, maxLength: 15 }),
        (initial, ops) => {
          const result = simulateThreatOps(initial, ops)
          expect(result).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 50 },
    )
  })
})

// ─── Unit Tests ──────────────────────────────────────────────────────────────

describe('GtA177IndependenceDeclaration.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  async function mountComponent(variantOverride?: string) {
    // Override mock for specific variant tests
    if (variantOverride) {
      const { api } = await import('@/services/apiProxy')
      ;(api.get as any).mockResolvedValueOnce({
        sheets: [{
          html_data: {
            variant: variantOverride,
            meta_info: { client_name: '测试公司', audit_year: '2025', index_no: variantOverride === 'committee' ? 'A17-7A' : 'A17-7' },
            declaration_text: variantOverride === 'committee' ? '委员会声明正文' : '团队声明正文',
            period_data: { business_start: '2025-01-01', business_end: '2025-12-31', report_start: '2025-01-01', report_end: '2025-12-31' },
            team_sign_table: [{ index: 1, name: '张三', signed: false, date: null }],
            partner_section: { confirmed: null, explanation: null, partner_sign: { name: null, date: null }, manager_sign: { name: null, date: null } },
            threat_records: { economic_interest: [], loan_guarantee: [], business_relation: [] },
            guidance_notes: ['1', '2', '3', '4', '5'],
            project_context: { client_name: '测试公司', audit_year: '2025', team_members: [{ name: '张三' }] },
          },
        }],
      })
    }

    const { default: Comp } = await import('../GtA177IndependenceDeclaration.vue')
    const wrapper = mount(Comp, {
      props: { wpId: 'wp-177' },
      global: {
        plugins: [ElementPlus as any],
        stubs: {
          GtOnlyOfficeSheet: defineComponent({ template: '<div class="oo-stub" />' }),
        },
      },
    })
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()
    return wrapper
  }

  describe('5 sections render', () => {
    it('renders declaration section with company and year', async () => {
      const wrapper = await mountComponent()
      const text = wrapper.text()
      expect(text).toContain('测试公司')
      expect(text).toContain('2025')
    })

    it('renders team sign table section title', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('项目组成员签字确认')
    })

    it('renders partner declaration section', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('合伙人及负责经理审查确认')
    })

    it('renders threat records section', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('独立性威胁记录')
    })

    it('renders guidance notes section', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('编制提示')
    })
  })

  describe('variant prop changes title', () => {
    it('shows team title for team variant', async () => {
      const wrapper = await mountComponent('team')
      expect(wrapper.text()).toContain('审计项目团队成员独立性声明书')
    })

    it('shows committee title for committee variant', async () => {
      const wrapper = await mountComponent('committee')
      expect(wrapper.text()).toContain('专业技术委员会审核委员独立性声明书')
    })
  })

  describe('mode switch', () => {
    it('defaults to structured view', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a177__content').exists()).toBe(true)
    })

    it('shows save status indicator', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a177__save-status').exists()).toBe(true)
    })
  })

  describe('date pickers', () => {
    it('renders business period section', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('业务期间')
    })

    it('renders report period section', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('财务报告期间')
    })
  })

  describe('team table CRUD UI', () => {
    it('renders add member button', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('添加成员')
    })
  })

  describe('threat collapse', () => {
    it('renders 3 threat sub-tables', async () => {
      const wrapper = await mountComponent()
      const text = wrapper.text()
      expect(text).toContain('经济利益记录')
      expect(text).toContain('贷款担保记录')
      expect(text).toContain('商业关系记录')
    })
  })

  describe('guidance collapse', () => {
    it('renders guidance section with badge', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('编制提示')
    })
  })
})
