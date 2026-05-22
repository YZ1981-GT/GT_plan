/**
 * ExpenseAnalysisDialog.spec.ts — k-admin-cycle-post-review-fix Task 3.2
 *
 * 烟测目标（参照 FairValueTestDialog.spec.ts 模式）：
 * 1. mount — visible=true 时组件可挂载
 * 2. form 默认值 — wp_code/revenue/categories 默认值正确
 * 3. isFormValid — 至少一个类别同时填了 category 名 + 本年金额 > 0 才有效
 * 4. buildBody — 序列化 wp_code/current_year/prior_year/budget/industry_avg_rates/revenue/apply_to_sheet
 * 5. onCalc — 调用正确的 expense-analysis endpoint 并存储 result
 * 6. onApplyToSheet — 后端返回 applied_to_sheet 时 emit applied
 * 7. visible=false 时 result 重置（watch on visible）
 * 8. renderedExplanation — Markdown 渲染 + XSS 防护
 * 9. is_llm_stub=true 时 renderedExplanation 为空
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: (...args: any[]) => mockPost(...args),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import ExpenseAnalysisDialog from '../ExpenseAnalysisDialog.vue'

beforeEach(() => {
  mockPost.mockReset()
})

const PROPS_BASE = {
  visible: true,
  projectId: 'proj-1',
  wpId: 'wp-1',
  targetSheet: '审定表K8-1',
  defaultWpCode: 'K8' as const,
}

const STUBS = {
  'el-dialog': true, 'el-form': true, 'el-form-item': true,
  'el-radio-group': true, 'el-radio': true,
  'el-input-number': true, 'el-input': true, 'el-divider': true,
  'el-table': true, 'el-table-column': true, 'el-button': true,
  'el-alert': true, 'el-descriptions': true, 'el-descriptions-item': true,
  'el-tag': true, 'el-tabs': true, 'el-tab-pane': true,
}

describe('ExpenseAnalysisDialog (K-F7)', () => {
  it('1. visible=true 时组件可挂载', () => {
    const wrapper = mount(ExpenseAnalysisDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('2. 表单默认值正确（wp_code=K8 / 4 个默认类别）', () => {
    const wrapper = mount(ExpenseAnalysisDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.form.wp_code).toBe('K8')
    expect(vm.form.revenue).toBe(0)
    expect(vm.form.categories).toHaveLength(4)
    const names = vm.form.categories.map((c: any) => c.category)
    expect(names).toEqual(['职工薪酬', '差旅费', '折旧费', '其他'])
    expect(vm.result).toBeNull()
  })

  it('3. isFormValid：需至少一个类别有名字 + 本年金额 > 0', () => {
    const wrapper = mount(ExpenseAnalysisDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    // 默认 4 类全为 0 金额 → invalid
    expect(vm.isFormValid).toBe(false)
    // 仅填金额未填 category → invalid
    vm.form.categories[0].category = ''
    vm.form.categories[0].current = 100000
    expect(vm.isFormValid).toBe(false)
    // 同时有 category 名 + 金额 → valid
    vm.form.categories[0].category = '职工薪酬'
    vm.form.categories[0].current = 100000
    expect(vm.isFormValid).toBe(true)
  })

  it('4. buildBody：仅含 current/prior/budget/industry_rate > 0 的类别 + apply_to_sheet 可选', () => {
    const wrapper = mount(ExpenseAnalysisDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.wp_code = 'K8'
    vm.form.revenue = 5000000
    vm.form.categories = [
      { category: '职工薪酬', current: 200000, prior: 180000, budget: 190000, industry_rate: 0.04 },
      { category: '差旅费', current: 50000, prior: 0, budget: 0, industry_rate: 0 },
      { category: '空类别', current: 0, prior: 0, budget: 0, industry_rate: 0 },
    ]
    const body = vm.buildBody('审定表K8-1')
    expect(body.wp_code).toBe('K8')
    expect(body.revenue).toBe(5000000)
    expect(body.apply_to_sheet).toBe('审定表K8-1')
    expect(body.current_year).toEqual({ 职工薪酬: 200000, 差旅费: 50000 })
    expect(body.prior_year).toEqual({ 职工薪酬: 180000 })
    expect(body.budget).toEqual({ 职工薪酬: 190000 })
    expect(body.industry_avg_rates).toEqual({ 职工薪酬: 0.04 })
    // 不传 sheet 时 apply_to_sheet 为 null
    const bodyNoApply = vm.buildBody()
    expect(bodyNoApply.apply_to_sheet).toBeNull()
  })

  it('5. onCalc 调用正确 endpoint 并存储 result', async () => {
    const fakeResp = {
      yoy_changes: { 职工薪酬: { amount_change: 20000, rate_change: 0.111, flag: 'normal' } },
      budget_variances: null,
      industry_comparison: null,
      anomaly_flags: [],
      summary: '同比 1 类正常',
      is_llm_stub: true,
      applied_to_sheet: null,
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(ExpenseAnalysisDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.categories[0].current = 200000
    vm.form.categories[0].prior = 180000
    await vm.onCalc()

    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-1/workpapers/wp-1/k8/expense-analysis',
      expect.objectContaining({
        wp_code: 'K8',
        current_year: expect.any(Object),
      }),
    )
    expect(vm.result).toEqual(fakeResp)
  })

  it('6. onApplyToSheet：返回 applied_to_sheet 时 emit applied', async () => {
    const fakeResp = {
      yoy_changes: {},
      budget_variances: null,
      industry_comparison: null,
      anomaly_flags: [],
      summary: '已写回',
      is_llm_stub: true,
      applied_to_sheet: '审定表K8-1',
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(ExpenseAnalysisDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.categories[0].current = 200000
    await vm.onApplyToSheet()

    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-1/workpapers/wp-1/k8/expense-analysis',
      expect.objectContaining({ apply_to_sheet: '审定表K8-1' }),
    )
    const emitted = wrapper.emitted('applied')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual(['审定表K8-1'])
  })

  it('7. result 在弹窗关闭（visible=false）时重置', async () => {
    const wrapper = mount(ExpenseAnalysisDialog, {
      props: { ...PROPS_BASE, visible: true },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.result = {
      yoy_changes: {},
      budget_variances: null,
      industry_comparison: null,
      anomaly_flags: [],
      summary: 'stub',
      is_llm_stub: true,
    }
    await wrapper.setProps({ visible: false })
    expect(vm.result).toBeNull()
  })

  it('8. renderedExplanation：Markdown 渲染 + XSS 防护', () => {
    const wrapper = mount(ExpenseAnalysisDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.result = {
      yoy_changes: {},
      budget_variances: null,
      industry_comparison: null,
      anomaly_flags: [],
      summary: 'LLM 分析完成',
      is_llm_stub: false,
      ai_explanation: '## 异常分析\n\n- **职工薪酬**同比增长 11%\n- 建议执行`细节测试`\n\n> 风险等级：中',
    }
    const html = vm.renderedExplanation
    // Markdown 渲染正确
    expect(html).toContain('<h2>')
    expect(html).toContain('异常分析')
    expect(html).toContain('<strong>职工薪酬</strong>')
    expect(html).toContain('<li>')
    expect(html).toContain('<code>细节测试</code>')
    expect(html).toContain('<blockquote>')
  })

  it('8b. renderedExplanation：XSS 脚本被清除', () => {
    const wrapper = mount(ExpenseAnalysisDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.result = {
      yoy_changes: {},
      budget_variances: null,
      industry_comparison: null,
      anomaly_flags: [],
      summary: 'test',
      is_llm_stub: false,
      ai_explanation: '正常文本<script>alert("xss")</script>结束',
    }
    const html = vm.renderedExplanation
    expect(html).not.toContain('<script>')
    expect(html).toContain('正常文本')
    expect(html).toContain('结束')
  })

  it('9. is_llm_stub=true 时 renderedExplanation 为空', () => {
    const wrapper = mount(ExpenseAnalysisDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.result = {
      yoy_changes: {},
      budget_variances: null,
      industry_comparison: null,
      anomaly_flags: [],
      summary: 'stub 结果',
      is_llm_stub: true,
      ai_explanation: '## 这段不应渲染',
    }
    expect(vm.renderedExplanation).toBe('')
  })
})
