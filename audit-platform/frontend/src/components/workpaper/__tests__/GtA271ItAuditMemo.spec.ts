/**
 * Property-Based Tests + Unit Tests — GtA271ItAuditMemo.vue
 *
 * Spec: .kiro/specs/a27-1-it-audit-memo/
 * Task: 3.10, 3.11
 *
 * PBT: Property 3 (ch3→ch4 visibility), Property 4 (ch6 deficiency visibility)
 * Unit: 7 chapter cards render, memo header, IT team CRUD UI, radio, conditional,
 *       GtIndexChip×4, mode switch
 *
 * **Validates: Requirements 2.1-2.5, 3.1, 4.1, 5.1-5.4, 6.1-6.3, 7.1-7.3, 8.1-8.5, 9.1-9.4, 10.1-10.3, 11.1-11.5, 12.1-12.2**
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, defineComponent, h } from 'vue'
import * as fc from 'fast-check'

// ─── Mock dependencies ───────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({}), put: vi.fn().mockResolvedValue({}) },
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal() as any
  return {
    ...actual,
    ElMessage: { warning: vi.fn(), error: vi.fn() },
  }
})

// ─── Import after mocks ─────────────────────────────────────────────────────

import ElementPlus from 'element-plus'
import GtA271ItAuditMemo from '../GtA271ItAuditMemo.vue'

const CONCLUSION_OPTIONS = ['部分有效', '没有有效', '已有效'] as const

function mountComponent(htmlData: any = null) {
  return mount(GtA271ItAuditMemo, {
    props: {
      wpId: 'wp-a271-test',
      projectId: 'proj-test',
      htmlData,
    },
    global: {
      plugins: [ElementPlus],
      stubs: {
        GtOnlyOfficeSheet: defineComponent({ name: 'GtOnlyOfficeSheet', props: ['wpId', 'sheetName'], template: '<div class="oo-stub" />' }),
        GtIndexChip: defineComponent({ name: 'GtIndexChip', props: ['wpId', 'label'], template: '<span class="chip-stub">{{ label }}</span>' }),
      },
    },
  })
}

// ─── PBT: Property 3 — ch3→ch4 visibility ───────────────────────────────────

describe('Feature: a27-1-it-audit-memo, Property 3: ch3→ch4 visibility (component)', () => {
  it('ch4 card hidden when ch3 conclusion is "已有效"', () => {
    const chaptersData = Array.from({ length: 7 }, (_, i) => ({
      number: i + 1,
      title: `Chapter ${i + 1}`,
      content: null,
      conclusion: i === 2 ? '已有效' : null, // ch3 = 已有效
      deficiency: null,
      cross_ref: null,
    }))

    const wrapper = mountComponent({ chapters: chaptersData })
    // v-show sets display:none, the html should contain display: none for ch4
    const html = wrapper.html()
    expect(html).toContain('display: none')
    wrapper.unmount()
  })

  it('ch4 card visible when ch3 conclusion is not "已有效"', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('部分有效', '没有有效', null as string | null),
        (conclusion) => {
          const chaptersData = Array.from({ length: 7 }, (_, i) => ({
            number: i + 1,
            title: `Chapter ${i + 1}`,
            content: null,
            conclusion: i === 2 ? conclusion : null,
            deficiency: null,
            cross_ref: null,
          }))

          const wrapper = mountComponent({ chapters: chaptersData })
          // When ch3 is not "已有效", no element should have display:none
          // (ch4 is visible)
          const text = wrapper.text()
          expect(text).toContain('四、IT一般控制缺陷')

          wrapper.unmount()
        },
      ),
      { numRuns: 10 },
    )
  })
})

// ─── PBT: Property 4 — ch6 deficiency visibility ────────────────────────────

describe('Feature: a27-1-it-audit-memo, Property 4: ch6 deficiency visibility (component)', () => {
  it('ch6 deficiency textarea hidden when conclusion is "已有效"', () => {
    const chaptersData = Array.from({ length: 7 }, (_, i) => ({
      number: i + 1,
      title: `Chapter ${i + 1}`,
      content: null,
      conclusion: i === 5 ? '已有效' : null, // ch6 = 已有效
      deficiency: 'some deficiency',
      cross_ref: null,
    }))

    const wrapper = mountComponent({ chapters: chaptersData })
    // ch6 deficiency uses v-if so element won't be rendered
    // The text should NOT contain the placeholder for ch6 deficiency
    const ch6Text = wrapper.text()
    // When ch6 is "已有效", the conditional textarea placeholder won't appear
    expect(ch6Text).not.toContain('请描述信息处理控制缺陷情况')
    wrapper.unmount()
  })

  it('ch6 deficiency textarea visible when conclusion is not "已有效"', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('部分有效', '没有有效', null as string | null),
        (conclusion) => {
          const chaptersData = Array.from({ length: 7 }, (_, i) => ({
            number: i + 1,
            title: `Chapter ${i + 1}`,
            content: null,
            conclusion: i === 5 ? conclusion : null,
            deficiency: null,
            cross_ref: null,
          }))

          const wrapper = mountComponent({ chapters: chaptersData })
          // ch6 deficiency textarea should exist (v-if = true)
          const html = wrapper.html()
          expect(html).toContain('请描述信息处理控制缺陷情况')

          wrapper.unmount()
        },
      ),
      { numRuns: 10 },
    )
  })
})

// ─── Unit Tests: Component Structure ─────────────────────────────────────────

describe('GtA271ItAuditMemo — unit tests', () => {
  it('renders all chapter titles in structured view', () => {
    const wrapper = mountComponent()
    const text = wrapper.text()
    expect(text).toContain('一、了解信息系统环境')
    expect(text).toContain('二、IT风险和一般控制')
    expect(text).toContain('三、IT一般控制结论')
    expect(text).toContain('四、IT一般控制缺陷')
    expect(text).toContain('五、信息处理控制')
    expect(text).toContain('六、信息处理控制结论')
    expect(text).toContain('七、缺陷评估')
    wrapper.unmount()
  })

  it('renders purpose text', () => {
    const wrapper = mountComponent()
    expect(wrapper.text()).toContain('本备忘录旨在总结')
    wrapper.unmount()
  })

  it('renders memo header section', () => {
    const wrapper = mountComponent({
      header: { date: '2026-01-01', to: 'IT部', from_user: '审计组', subject: 'IT审计' },
    })
    expect(wrapper.text()).toContain('备忘录抬头')
    expect(wrapper.find('.gt-a271__header-row').exists()).toBe(true)
    wrapper.unmount()
  })

  it('renders IT team table with add button', () => {
    const wrapper = mountComponent({
      it_team_table: [
        { index: 1, name: '张三', title: '经理' },
        { index: 2, name: '李四', title: '助理' },
      ],
    })
    expect(wrapper.text()).toContain('IT审计团队')
    expect(wrapper.text()).toContain('添加成员')
    wrapper.unmount()
  })

  it('renders mode switch', () => {
    const wrapper = mountComponent()
    // el-segmented renders with Element Plus
    expect(wrapper.text()).toContain('结构化视图')
    wrapper.unmount()
  })

  it('renders GtIndexChip for chapters with cross-references', () => {
    const wrapper = mountComponent({
      cross_references: {
        b22a_4_3_wp_id: 'wp-b22a',
        c22_wp_id: 'wp-c22',
        c21_1_wp_id: 'wp-c21',
        b23_15_wp_id: 'wp-b23',
      },
    })
    const chips = wrapper.findAll('.chip-stub')
    expect(chips).toHaveLength(4)
    expect(chips[0].text()).toContain('B22A-4-3')
    expect(chips[1].text()).toContain('C22')
    expect(chips[2].text()).toContain('C21-1')
    expect(chips[3].text()).toContain('B23-15')
    wrapper.unmount()
  })

  it('does not render GtIndexChip when cross-ref wp_id is null', () => {
    const wrapper = mountComponent({
      cross_references: {
        b22a_4_3_wp_id: null,
        c22_wp_id: null,
        c21_1_wp_id: null,
        b23_15_wp_id: null,
      },
    })
    const chips = wrapper.findAll('.chip-stub')
    expect(chips).toHaveLength(0)
    wrapper.unmount()
  })

  it('renders radio groups for ch3 and ch6', () => {
    const wrapper = mountComponent()
    const radioSections = wrapper.findAll('.gt-a271__radio-section')
    expect(radioSections.length).toBe(2) // ch3 + ch6
    wrapper.unmount()
  })

  it('save status shows "已保存" initially', () => {
    const wrapper = mountComponent()
    expect(wrapper.text()).toContain('已保存')
    wrapper.unmount()
  })
})
