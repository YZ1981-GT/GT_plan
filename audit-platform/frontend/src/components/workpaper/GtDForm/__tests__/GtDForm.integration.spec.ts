/**
 * GtDForm.integration.spec.ts — D 类顶层路由 → 真实子 shell 集成测试
 *
 * 复盘改进 #4（2026-05-30）：GtDForm.spec.ts 用 vi.mock 把 5 个子组件全部 stub，
 * 只验证了"分发到哪个 stub"，未验证 GtDForm → 真实 Review/Confirmation/Paragraph
 * shell 的 props 传递链路（wpId/sheetName/schema/htmlData/readonly）+ emit 冒泡。
 *
 * 本文件**不 mock 子组件**，挂载真实 shell，验证：
 * 1. form_type=review/confirmation/paragraph 时真实 shell 被渲染 + 接收正确 props
 * 2. 子 shell 触发 save / field-change 时 GtDForm 正确冒泡到顶层
 *
 * Validates: Requirements 4.1, 5.1, 6.1（拆分后父子集成不回归）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtDForm from '../GtDForm.vue'
import GtDFormReview from '../GtDFormReview.vue'
import GtDFormConfirmation from '../GtDFormConfirmation.vue'
import GtDFormParagraph from '../GtDFormParagraph.vue'
import { elementPlusStubs } from './stubs'

// ─── Mock element-plus 交互 API（Review 签字/状态机用）────────────────────────

vi.mock('element-plus', () => ({
  ElMessageBox: {
    confirm: vi.fn().mockResolvedValue(true),
    prompt: vi.fn().mockResolvedValue({ value: '测试原因说明' }),
  },
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  // Confirmation/Paragraph shell 直接 import ElInput 等组件作为动态 component
  ElInput: { name: 'ElInput', template: '<input class="el-input-real" />' },
  ElInputNumber: { name: 'ElInputNumber', template: '<input class="el-input-number-real" />' },
  ElDatePicker: { name: 'ElDatePicker', template: '<input class="el-date-picker-real" />' },
  ElSelect: { name: 'ElSelect', template: '<select class="el-select-real"><slot /></select>' },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { id: 'u1', username: 'reviewer', full_name: '张审计' } }),
}))

vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: { template: '<span class="gt-index-chip"><slot /></span>', props: ['value', 'refCode', 'validate'] },
}))

vi.mock('@/composables/useWpAiSuggest', () => ({
  useWpAiSuggest: () => ({
    aiEnabled: { value: false }, aiLoading: { value: false },
    currentSuggestion: { value: null }, showSuggestionPanel: { value: false },
    assistedFieldsList: { value: [] },
    requestSuggestion: vi.fn(), adoptSuggestion: vi.fn(), modifySuggestion: vi.fn(), ignoreSuggestion: vi.fn(),
  }),
}))

const globalStubs = { ...elementPlusStubs, 'el-result': { template: '<div class="el-result"><slot /><slot name="sub-title" /></div>', props: ['icon', 'title'] } }

function mountGtDForm(formType: string, schema: Record<string, any>, htmlData: Record<string, any> = {}, readonly = false) {
  return mount(GtDForm, {
    props: { wpId: 'wp-int-001', sheetName: '集成测试 sheet', schema: { form_type: formType, ...schema } as any, htmlData, readonly },
    global: { stubs: globalStubs },
  })
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('GtDForm 集成 — 真实子 shell 渲染 + props 传递', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('form_type=review → 挂载真实 GtDFormReview 并透传 props', () => {
    const wrapper = mountGtDForm('review', {
      state_machine: {
        states: [{ id: 'draft', label: '草稿', class: 'info' }],
        transitions: [], initial: 'draft', final: [], audit_log: true,
      },
      review_steps: [], fields: [],
    }, { state: 'draft' })

    const review = wrapper.findComponent(GtDFormReview)
    expect(review.exists()).toBe(true)
    expect(review.props('wpId')).toBe('wp-int-001')
    expect(review.props('sheetName')).toBe('集成测试 sheet')
    expect(review.props('readonly')).toBe(false)
    // 真实 shell 内部状态机已按 props.htmlData 初始化
    expect((review.vm as any).currentState).toBe('draft')
  })

  it('form_type=confirmation → 挂载真实 GtDFormConfirmation 并透传 props', () => {
    const wrapper = mountGtDForm('confirmation', {
      confirmation_workflow: { stages: [{ stage: 'generation', title: '生成', fields: [] }] },
    }, { active_stage: 'generation' })

    const conf = wrapper.findComponent(GtDFormConfirmation)
    expect(conf.exists()).toBe(true)
    expect(conf.props('wpId')).toBe('wp-int-001')
    expect((conf.vm as any).activeStageNo).toBe('generation')
  })

  it('form_type=paragraph → 挂载真实 GtDFormParagraph 并透传 props', () => {
    const wrapper = mountGtDForm('paragraph', {
      fixed_cells: { A3: '集成公司', A4: '2025-12-31', I3: 'D2-8' },
      segments: [{ id: 's1', seq: '一', title: '审计目标', editable: true, type: 'textarea', cell: 'B6' }],
    }, { segments: { s1: '已填内容' } })

    const para = wrapper.findComponent(GtDFormParagraph)
    expect(para.exists()).toBe(true)
    expect(para.props('wpId')).toBe('wp-int-001')
    expect((para.vm as any).entityName).toBe('集成公司')
    expect((para.vm as any).segmentValues['s1']).toBe('已填内容')
  })

  it('readonly=true 透传到真实子 shell', () => {
    const wrapper = mountGtDForm('paragraph', {
      fixed_cells: {}, segments: [{ id: 's1', seq: '一', title: 't', editable: true, type: 'textarea', cell: 'B6' }],
    }, {}, true)
    const para = wrapper.findComponent(GtDFormParagraph)
    expect(para.props('readonly')).toBe(true)
  })
})

describe('GtDForm 集成 — 子 shell emit 冒泡到顶层', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('Paragraph shell 的 save 事件冒泡到 GtDForm', async () => {
    const wrapper = mountGtDForm('paragraph', {
      fixed_cells: {}, segments: [{ id: 's1', seq: '一', title: 't', editable: true, type: 'textarea', cell: 'B6' }],
    }, {})

    const para = wrapper.findComponent(GtDFormParagraph)
    const vm = para.vm as any
    vm.segmentValues['s1'] = '新内容'
    vm.onSegmentChange('s1')
    vi.advanceTimersByTime(1500)
    await nextTick()

    // 子 shell save 应冒泡到顶层 GtDForm
    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    expect((emitted![0][0] as any).segments.s1).toBe('新内容')
  })

  it('Review shell 的 field-change 事件冒泡到 GtDForm', async () => {
    const wrapper = mountGtDForm('review', {
      state_machine: { states: [{ id: 'draft', label: '草稿' }], transitions: [], initial: 'draft', final: [] },
      review_steps: [{ step: 1, title: '步骤1', checklist: [{ id: 'ck1', label: 'x', cell: 'C10' }], fields: [] }],
      fields: [],
    }, { state: 'draft' })

    const review = wrapper.findComponent(GtDFormReview)
    const vm = review.vm as any
    const step = { step: 1, title: '步骤1', checklist: [{ id: 'ck1', label: 'x', cell: 'C10' }], fields: [] }
    vm.onChecklistChange(step, { id: 'ck1', label: 'x', cell: 'C10' }, true)
    await nextTick()

    const emitted = wrapper.emitted('field-change')
    expect(emitted).toBeDefined()
    expect((emitted![0][0] as any).field_name).toBe('step_1.checklist.ck1')
  })
})
