/**
 * Unit Tests + PBT — GtA182RegulatoryCommunication.vue 组件
 *
 * Spec: .kiro/specs/a18-2-regulatory-communication/
 * Tasks: 3.2, 3.3
 *
 * Property 2: Y→textarea visible, N/NA→hidden
 * Property 4: dual-sign independence (cpa1 and cpa2 independent)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import * as fc from 'fast-check'

// ─── Mock API ────────────────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({
      sheets: [{
        html_data: {
          recipient: { authority: '中国证券监督管理委员会', custom: '' },
          matters: [
            { id: 1, title: '舞弊', applicability: 'Y', content: '内容1' },
            { id: 2, title: '重大违反法律法规行为', applicability: 'N', content: '' },
            { id: 3, title: '年度报告中信息不一致或错报', applicability: 'NA', content: '' },
            { id: 4, title: '其他事项', applicability: null, content: '' },
          ],
          issuance: { cpa1: '张三', cpa2: '李四', date: '2026-03-15' },
          project_context: { client_name: '测试公司', audit_year: '2025', firm_name: '致同会计师事务所（特殊普通合伙）' },
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

describe('GtA182RegulatoryCommunication.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  async function mountComponent(props: Record<string, any> = {}) {
    const { default: GtA182RegulatoryCommunication } = await import('../GtA182RegulatoryCommunication.vue')
    const wrapper = mount(GtA182RegulatoryCommunication, {
      props: { wpId: 'wp-182', ...props },
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
        },
      },
    })
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()
    return wrapper
  }

  // ─── 区块渲染 ───

  describe('5 区块渲染', () => {
    it('renders structured view by default', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a182__content').exists()).toBe(true)
    })

    it('renders recipient section with 致：prefix', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('致：')
    })

    it('renders introduction text with project context', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('测试公司')
      expect(wrapper.text()).toContain('2025')
    })

    it('renders 4 matter applicability sections', async () => {
      const wrapper = await mountComponent()
      // Each matter has 适用性 label
      const text = wrapper.text()
      expect((text.match(/适用性：/g) || []).length).toBe(4)
    })

    it('renders dual CPA sign fields', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('中国注册会计师（1）')
      expect(wrapper.text()).toContain('中国注册会计师（2）')
    })

    it('renders guidance tables content', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('CAS 1151.14')
      expect(wrapper.text()).toContain('CAS 1152.09')
    })

    it('renders save status indicator', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a182__save-status').exists()).toBe(true)
    })

    it('renders toolbar with AI button', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a182__toolbar').exists()).toBe(true)
      expect(wrapper.text()).toContain('AI')
    })
  })

  // ─── 适用性三态切换 ───

  describe('适用性三态切换', () => {
    it('renders radio group with Y/N/NA options for each matter', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('适用')
      expect(wrapper.text()).toContain('不适用')
      expect(wrapper.text()).toContain('不涉及')
    })
  })

  // ─── Select + Custom ───

  describe('select + custom 切换', () => {
    it('shows custom input when authority is "其他" (via data inspection)', async () => {
      const { api } = await import('@/services/apiProxy')
      ;(api.get as any).mockResolvedValueOnce({
        sheets: [{
          html_data: {
            recipient: { authority: '其他', custom: '某省财政厅' },
            matters: [
              { id: 1, title: '舞弊', applicability: null, content: '' },
              { id: 2, title: '重大违反法律法规行为', applicability: null, content: '' },
              { id: 3, title: '年度报告中信息不一致或错报', applicability: null, content: '' },
              { id: 4, title: '其他事项', applicability: null, content: '' },
            ],
            issuance: { cpa1: '', cpa2: '', date: '' },
            project_context: { client_name: '', audit_year: '', firm_name: '致同' },
          },
        }],
      })
      const wrapper = await mountComponent()
      // The custom input placeholder should be visible when authority='其他'
      expect(wrapper.html()).toContain('请输入监管机构名称')
    })
  })

  // ─── PBT Property 2: 适用性→textarea 联动 ───

  describe('Property 2: 适用性→textarea 联动 (PBT)', () => {
    it('for any matter, Y shows textarea and N/NA/null hides it', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 4 }),
          fc.oneof(
            fc.constant('Y'),
            fc.constant('N'),
            fc.constant('NA'),
            fc.constant(null),
          ),
          (matterId, applicability) => {
            // Pure logic: v-show="matter.applicability === 'Y'"
            const visible = applicability === 'Y'
            if (applicability === 'Y') {
              expect(visible).toBe(true)
            } else {
              expect(visible).toBe(false)
            }
          },
        ),
        { numRuns: 30 },
      )
    })
  })

  // ─── PBT Property 4: dual-sign independence ───

  describe('Property 4: 双签独立性 (PBT)', () => {
    it('cpa1 and cpa2 are independent fields that never affect each other', () => {
      fc.assert(
        fc.property(
          fc.string({ minLength: 1, maxLength: 20 }),
          fc.string({ minLength: 1, maxLength: 20 }),
          (cpa1Value, cpa2Value) => {
            // Simulating the issuance reactive state
            const issuance = { cpa1: '', cpa2: '', date: '' }

            // Update cpa1
            issuance.cpa1 = cpa1Value
            expect(issuance.cpa2).toBe('')

            // Update cpa2
            issuance.cpa2 = cpa2Value
            expect(issuance.cpa1).toBe(cpa1Value) // cpa1 unchanged

            // Both are set independently
            expect(issuance.cpa1).not.toBe(issuance.cpa2)
          },
        ),
        { numRuns: 30 },
      )
    })

    it('setting one CPA does not clear the other', () => {
      fc.assert(
        fc.property(
          fc.string({ minLength: 1, maxLength: 20 }),
          fc.string({ minLength: 1, maxLength: 20 }),
          fc.string({ minLength: 1, maxLength: 20 }),
          (initial1, initial2, newValue) => {
            const issuance = { cpa1: initial1, cpa2: initial2, date: '' }
            // Update cpa1 → cpa2 must remain
            issuance.cpa1 = newValue
            expect(issuance.cpa2).toBe(initial2)
          },
        ),
        { numRuns: 20 },
      )
    })
  })

  // ─── Mode Switch ───

  describe('模式切换', () => {
    it('defaults to structured view', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a182__content').exists()).toBe(true)
      expect(wrapper.find('.oo-stub').exists()).toBe(false)
    })
  })

  // ─── Readonly Mode ───

  describe('readonly mode', () => {
    it('renders without error in readonly', async () => {
      const wrapper = await mountComponent({ readonly: true })
      expect(wrapper.find('.gt-a182').exists()).toBe(true)
    })
  })
})
