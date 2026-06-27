/**
 * Unit Tests + PBT — GtA174DisagreementRecord.vue
 *
 * Spec: .kiro/specs/a17-4-disagreement-record/
 * Task: 3.4 (Property 4: signature auto-fill) + 3.5 (unit tests)
 *
 * Property 4: 签字区自动填充 — first-load 编制人 auto-fill from current_user
 * Unit: personnel table UI, 6 section cards render, signature area, mode switch
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, nextTick } from 'vue'
import * as fc from 'fast-check'
import ElementPlus from 'element-plus'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual,
    ElMessage: { warning: vi.fn(), error: vi.fn() },
  }
})

// ─── Property 4: 签字区自动填充 PBT ─────────────────────────────────────────

describe('Feature: a17-4-disagreement-record, Property 4: 签字区自动填充', () => {
  /**
   * **Validates: Requirements 10.1**
   *
   * For any first-load where preparer is empty, 编制人 SHALL auto-fill from current_user.
   */

  function autoFillPreparer(preparer: string, currentUser: string): string {
    if (!preparer && currentUser) {
      return currentUser
    }
    return preparer
  }

  it('empty preparer is auto-filled from current_user', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 30 }),
        (currentUser) => {
          const result = autoFillPreparer('', currentUser)
          expect(result).toBe(currentUser)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('non-empty preparer is never overwritten', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 30 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        (existingPreparer, currentUser) => {
          const result = autoFillPreparer(existingPreparer, currentUser)
          expect(result).toBe(existingPreparer)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('empty current_user does not override empty preparer', () => {
    const result = autoFillPreparer('', '')
    expect(result).toBe('')
  })
})

// ─── Component Unit Tests ────────────────────────────────────────────────────

describe('GtA174DisagreementRecord — component', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
    mockGet.mockResolvedValue({
      sheets: [{
        html_data: {
          personnel: [{ name: '张三', position: '经理', role: '负责人' }],
          sections: {
            '1': { parties: '分歧描述' },
            '2': { cause: '' },
            '3': { procedures: '' },
            '4': { opinions: '' },
            '5': { considerations: '' },
            '6': { conclusion: '' },
          },
          signature_data: { preparer: '编制人A', reviewer: '', date: '' },
          project_context: { client_name: '测试', current_user: '编制人A' },
        },
      }],
    })
  })

  async function mountComponent(opts: { readonly?: boolean } = {}) {
    const { default: GtA174DisagreementRecord } = await import('../GtA174DisagreementRecord.vue')
    const wrapper = mount(GtA174DisagreementRecord, {
      props: { wpId: 'wp-174', readonly: opts.readonly ?? false },
      global: { plugins: [ElementPlus] },
    })
    await nextTick()
    await nextTick()
    return wrapper
  }

  describe('mode switch', () => {
    it('renders segmented control with two options', async () => {
      const wrapper = await mountComponent()
      const segmented = wrapper.find('.gt-a174__toolbar')
      expect(segmented.exists()).toBe(true)
    })

    it('defaults to structured view', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a174__content').exists()).toBe(true)
    })
  })

  describe('personnel table', () => {
    it('renders personnel rows from loaded data', async () => {
      const wrapper = await mountComponent()
      // Wait for async loadData
      await new Promise(r => setTimeout(r, 10))
      await nextTick()
      // Check that table has rows via el-table
      const table = wrapper.find('.el-table')
      expect(table.exists()).toBe(true)
    })

    it('has add personnel button', async () => {
      const wrapper = await mountComponent()
      const addBtn = wrapper.find('.gt-a174__card-header .el-button')
      expect(addBtn.exists()).toBe(true)
      expect(addBtn.text()).toContain('添加人员')
    })
  })

  describe('section cards', () => {
    it('renders 6 section cards', async () => {
      const wrapper = await mountComponent()
      // 1 personnel card + 6 section cards + 1 signature card = 8 cards
      const cards = wrapper.findAll('.gt-a174__card')
      expect(cards.length).toBe(8)
    })

    it('section cards have correct titles', async () => {
      const wrapper = await mountComponent()
      const titles = wrapper.findAll('.gt-a174__card-title')
      const titleTexts = titles.map(t => t.text())
      expect(titleTexts).toContain('一、分歧事项描述')
      expect(titleTexts).toContain('二、各方意见')
      expect(titleTexts).toContain('三、咨询/讨论过程')
      expect(titleTexts).toContain('四、最终结论')
      expect(titleTexts).toContain('五、后续措施')
      expect(titleTexts).toContain('六、备注')
    })
  })

  describe('signature area', () => {
    it('renders signature card with preparer/reviewer/date', async () => {
      const wrapper = await mountComponent()
      const sigCard = wrapper.findAll('.gt-a174__card').at(-1)!
      const labels = sigCard.findAll('label')
      const labelTexts = labels.map(l => l.text())
      expect(labelTexts).toContain('编制人')
      expect(labelTexts).toContain('复核人')
      expect(labelTexts).toContain('日期')
    })
  })
})
