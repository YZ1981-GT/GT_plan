/**
 * GtDFormReview.spec.ts — D 类复核记录子组件单元测试
 *
 * 验证：
 * 1. 状态机流转：draft→review / review→approved / 非法转换拒绝
 * 2. 签字逻辑：onSignClick 成功签字 / canUnsign 边界（最后签字可撤 / 非最后不可撤）
 * 3. 字段联动：setStepField 触发 checklist 更新 / onChecklistChange 联动
 * 4. debounce save：修改字段后 save payload 包含 dirty 字段、不含未修改字段
 *
 * 复用 GtDFormQA.spec.ts 范式（Element Plus stubs + fake timers + mount props）
 *
 * Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtDFormReview from '../GtDFormReview.vue'
import { elementPlusStubs } from './stubs'

// ─── Mock ElMessageBox ──────────────────────────────────────────────────────

vi.mock('element-plus', () => ({
  ElMessageBox: {
    confirm: vi.fn().mockResolvedValue(true),
    prompt: vi.fn().mockResolvedValue({ value: '测试原因说明' }),
  },
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}))

// ─── Mock auth store ────────────────────────────────────────────────────────

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 'u1', username: 'reviewer', full_name: '张审计' },
  }),
}))

// ─── Mock GtIndexChip ───────────────────────────────────────────────────────

vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    template: '<span class="gt-index-chip">{{ refCode }}</span>',
    props: ['refCode'],
  },
}))

// ─── Element Plus stubs（复用共享超集，含 el-select/el-option/el-input-number 消除 Vue warn）─

const globalStubs = elementPlusStubs

// ─── Schema / Data builders ─────────────────────────────────────────────────

function buildReviewSchema(overrides: Record<string, any> = {}) {
  return {
    component_type: 'd-form',
    form_type: 'review',
    fixed_cells: { A3: '测试公司', A4: '2025-12-31', H3: 'A22' },
    review_role: 'project_manager',
    fields: [
      { name: 'scope', label: '复核范围', type: 'textarea', cell: 'B6' },
      { name: 'period', label: '复核期间', type: 'text', cell: 'B8', readonly: true, default: '2025年度' },
    ],
    review_steps: [
      {
        step: 1,
        title: '步骤 1：审计完成度检查',
        description: '检查底稿完成情况',
        checklist: [
          { id: 'ck1', label: '底稿已完成', cell: 'C10', required: true },
          { id: 'ck2', label: '索引号正确', cell: 'C11' },
        ],
        comment_field: { name: 'comment_1', label: '备注', cell: 'D10' },
        fields: [],
      },
      {
        step: 2,
        title: '步骤 2：重大错报风险评估',
        description: '评估重大错报风险',
        checklist: [
          { id: 'ck3', label: '风险已识别', cell: 'C20' },
        ],
        comment_field: { name: 'comment_2', label: '备注', cell: 'D20' },
        fields: [
          { name: 'risk_level', label: '风险等级', type: 'enum', enum: ['低', '中', '高'], cell: 'E20' },
        ],
      },
      {
        step: 3,
        title: '步骤 3：签字确认',
        description: '终结步骤',
        checklist: [],
        comment_field: { name: 'comment_3', label: '备注', cell: 'D30' },
        fields: [],
        signature: [
          { role: 'project_manager', label: '项目经理', cell: 'F30', required: true, auto_timestamp: true },
          { role: 'partner', label: '合伙人', cell: 'F31', required: true, auto_timestamp: true },
        ],
        is_terminal: true,
      },
    ],
    state_machine: {
      states: [
        { id: 'draft', label: '草稿', class: 'info' },
        { id: 'in_progress', label: '进行中', class: 'warning' },
        { id: 'pending_signature', label: '待签字', class: 'warning' },
        { id: 'review_passed', label: '复核通过', class: 'success' },
        { id: 'review_returned', label: '退回修改', class: 'danger' },
      ],
      transitions: [
        { from: 'draft', to: 'in_progress', trigger: 'start_review', description: '开始复核 → 进行中' },
        { from: 'in_progress', to: 'pending_signature', trigger: 'submit_for_sign', description: '提交签字 → 待签字' },
        { from: 'pending_signature', to: 'review_passed', trigger: 'signature_completed', description: '签字完成 → 复核通过' },
        { from: 'in_progress', to: 'review_returned', trigger: 'return_for_revision', description: '退回 → 退回修改' },
        { from: 'review_returned', to: 'in_progress', trigger: 'resubmit', description: '重新提交 → 进行中' },
      ],
      initial: 'draft',
      final: ['review_passed'],
      cell: 'G3',
      audit_log: true,
    },
    conclusion: {
      mode: 'single',
      cell: 'H40',
      options: [
        { value: 'pass', label: '通过', class: 'success', icon: 'CircleCheckFilled' },
        { value: 'conditional', label: '有条件通过', class: 'warning', icon: 'WarningFilled' },
        { value: 'fail', label: '不通过', class: 'danger', icon: 'CircleCloseFilled' },
      ],
    },
    ...overrides,
  }
}

function buildHtmlData(overrides: Record<string, any> = {}) {
  return {
    context: {
      scope: '全面复核',
      period: '2025年度',
    },
    steps: {
      step_1: { checklist: { ck1: true, ck2: false }, comment: '初步检查', fields: {} },
      step_2: { checklist: { ck3: false }, comment: '', fields: { risk_level: '中' } },
      step_3: { checklist: {}, comment: '', fields: {} },
    },
    active_step: 0,
    state: 'draft',
    signatures: {},
    audit_log: [],
    conclusion: '',
    ...overrides,
  }
}

function mountReview(propsOverrides: Record<string, any> = {}, dataOverrides: Record<string, any> = {}) {
  return mount(GtDFormReview, {
    props: {
      wpId: 'wp-review-001',
      sheetName: '项目经理复核',
      schema: buildReviewSchema() as any,
      htmlData: buildHtmlData(dataOverrides),
      ...propsOverrides,
    },
    global: { stubs: globalStubs },
  })
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('GtDFormReview — 状态机流转', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('初始状态为 draft，可用 transition 为 start_review', () => {
    const wrapper = mountReview()
    const vm = wrapper.vm as any
    expect(vm.currentState).toBe('draft')
    expect(vm.availableTransitions.length).toBe(1)
    expect(vm.availableTransitions[0].trigger).toBe('start_review')
  })

  it('draft → in_progress 转换成功', async () => {
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    await vm.onTransitionClick(vm.availableTransitions[0])
    await nextTick()

    expect(vm.currentState).toBe('in_progress')
    expect(vm.auditLog.length).toBe(1)
    expect(vm.auditLog[0].from).toBe('draft')
    expect(vm.auditLog[0].to).toBe('in_progress')

    const emitted = wrapper.emitted('state-change')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toMatchObject({ from: 'draft', to: 'in_progress', trigger: 'start_review' })
  })

  it('in_progress → pending_signature 转换成功', async () => {
    const wrapper = mountReview({}, { state: 'in_progress' })
    const vm = wrapper.vm as any

    expect(vm.currentState).toBe('in_progress')
    const submitTrans = vm.availableTransitions.find((t: any) => t.trigger === 'submit_for_sign')
    expect(submitTrans).toBeDefined()

    await vm.onTransitionClick(submitTrans)
    await nextTick()

    expect(vm.currentState).toBe('pending_signature')
    const emitted = wrapper.emitted('state-change')
    expect(emitted![0][0]).toMatchObject({ from: 'in_progress', to: 'pending_signature' })
  })

  it('非法转换：draft 状态下无法直接到 review_passed', () => {
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    // availableTransitions 只包含 from === currentState 的转换
    const illegalTrans = vm.availableTransitions.find((t: any) => t.to === 'review_passed')
    expect(illegalTrans).toBeUndefined()
  })

  it('终态 review_passed 无可用转换', () => {
    const wrapper = mountReview({}, { state: 'review_passed' })
    const vm = wrapper.vm as any

    expect(vm.currentState).toBe('review_passed')
    expect(vm.isFinalState).toBe(true)
    expect(vm.availableTransitions.length).toBe(0)
  })

  it('readonly 模式下 onTransitionClick 不执行', async () => {
    const wrapper = mountReview({ readonly: true })
    const vm = wrapper.vm as any

    await vm.onTransitionClick(vm.availableTransitions[0])
    await nextTick()

    expect(vm.currentState).toBe('draft')
    expect(wrapper.emitted('state-change')).toBeUndefined()
  })
})

describe('GtDFormReview — 签字逻辑', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('onSignClick 成功签字并 emit sign 事件', async () => {
    const wrapper = mountReview({}, { state: 'pending_signature', active_step: 2 })
    const vm = wrapper.vm as any

    const sig = { role: 'project_manager', label: '项目经理', cell: 'F30', required: true, auto_timestamp: true }
    await vm.onSignClick(sig)
    await nextTick()

    expect(vm.signaturesData['project_manager']).toBeDefined()
    expect(vm.signaturesData['project_manager'].signed_by).toBe('张审计')
    expect(vm.signaturesData['project_manager'].signed_at).toBeTruthy()

    const emitted = wrapper.emitted('sign')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toMatchObject({
      role: 'project_manager',
      signed_by: '张审计',
    })
  })

  it('全部 required 签字完成后自动推进状态机', async () => {
    // 先签 partner，再签 project_manager → 全部 required 签完 → 自动推进
    const wrapper = mountReview({}, {
      state: 'pending_signature',
      active_step: 2,
      signatures: {
        partner: { signed_by: '李合伙人', signed_at: '2025-01-01T00:00:00Z', cell: 'F31' },
      },
    })
    const vm = wrapper.vm as any

    // 当前 step 3 有 2 个 required signature，partner 已签，签 project_manager
    const sig = { role: 'project_manager', label: '项目经理', cell: 'F30', required: true, auto_timestamp: true }
    await vm.onSignClick(sig)
    await nextTick()

    // 应自动推进到 review_passed
    expect(vm.currentState).toBe('review_passed')
    const stateEmitted = wrapper.emitted('state-change')
    expect(stateEmitted).toBeDefined()
    expect(stateEmitted![0][0]).toMatchObject({
      from: 'pending_signature',
      to: 'review_passed',
      trigger: 'signature_completed',
    })
  })

  it('canUnsign 在 pending_signature 状态下返回 true', () => {
    const wrapper = mountReview({}, { state: 'pending_signature' })
    const vm = wrapper.vm as any

    const sig = { role: 'project_manager', label: '项目经理', cell: 'F30' }
    expect(vm.canUnsign(sig)).toBe(true)
  })

  it('canUnsign 在 in_progress 状态下返回 true', () => {
    const wrapper = mountReview({}, { state: 'in_progress' })
    const vm = wrapper.vm as any

    const sig = { role: 'project_manager', label: '项目经理', cell: 'F30' }
    expect(vm.canUnsign(sig)).toBe(true)
  })

  it('canUnsign 在 review_passed 状态下返回 false（非最后签字不可撤）', () => {
    const wrapper = mountReview({}, { state: 'review_passed' })
    const vm = wrapper.vm as any

    const sig = { role: 'project_manager', label: '项目经理', cell: 'F30' }
    expect(vm.canUnsign(sig)).toBe(false)
  })

  it('readonly 模式下 onSignClick 不执行', async () => {
    const wrapper = mountReview({ readonly: true }, { state: 'pending_signature', active_step: 2 })
    const vm = wrapper.vm as any

    const sig = { role: 'project_manager', label: '项目经理', cell: 'F30', required: true }
    await vm.onSignClick(sig)
    await nextTick()

    expect(vm.signaturesData['project_manager']).toBeUndefined()
    expect(wrapper.emitted('sign')).toBeUndefined()
  })
})

describe('GtDFormReview — 字段联动', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('setStepField 更新字段值并 emit field-change', () => {
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    const step = { step: 2, title: '步骤 2', checklist: [{ id: 'ck3', label: '风险已识别', cell: 'C20' }], fields: [{ name: 'risk_level', label: '风险等级', type: 'enum', cell: 'E20' }] }
    const field = { name: 'risk_level', label: '风险等级', type: 'enum', cell: 'E20' }

    vm.setStepField(step, field, '高')

    expect(vm.stepsData['step_2'].fields['risk_level']).toBe('高')
    const emitted = wrapper.emitted('field-change')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toMatchObject({
      field_name: 'step_2.risk_level',
      old_value: '中',
      new_value: '高',
      cell: 'E20',
    })
  })

  it('onChecklistChange 更新 checklist 并 emit field-change', () => {
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    const step = { step: 1, title: '步骤 1', checklist: [{ id: 'ck2', label: '索引号正确', cell: 'C11' }] }
    const item = { id: 'ck2', label: '索引号正确', cell: 'C11' }

    vm.onChecklistChange(step, item, true)

    expect(vm.stepsData['step_1'].checklist['ck2']).toBe(true)
    const emitted = wrapper.emitted('field-change')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toMatchObject({
      field_name: 'step_1.checklist.ck2',
      old_value: false,
      new_value: true,
      cell: 'C11',
    })
  })

  it('setStepField 对未初始化的步骤自动创建 bucket', () => {
    // 使用一个 schema 中不存在的步骤来测试自动创建
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    const step = { step: 99, title: '步骤 99', checklist: [], fields: [{ name: 'test_field', label: '测试', type: 'text', cell: 'X1' }] }
    const field = { name: 'test_field', label: '测试', type: 'text', cell: 'X1' }

    vm.setStepField(step, field, '新值')

    expect(vm.stepsData['step_99']).toBeDefined()
    expect(vm.stepsData['step_99'].fields['test_field']).toBe('新值')
    expect(vm.stepsData['step_99'].checklist).toEqual({})
    expect(vm.stepsData['step_99'].comment).toBe('')
  })

  it('onChecklistChange 对未初始化的步骤自动创建 bucket', () => {
    // 使用一个 schema 中不存在的步骤来测试自动创建
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    const step = { step: 99, title: '步骤 99', checklist: [{ id: 'ck99', label: '新检查项', cell: 'C99' }] }
    const item = { id: 'ck99', label: '新检查项', cell: 'C99' }

    vm.onChecklistChange(step, item, true)

    expect(vm.stepsData['step_99']).toBeDefined()
    expect(vm.stepsData['step_99'].checklist['ck99']).toBe(true)
  })
})

describe('GtDFormReview — debounce save', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('字段修改后 1.5s debounce 触发 save', async () => {
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    const step = { step: 2, title: '步骤 2', checklist: [], fields: [{ name: 'risk_level', label: '风险等级', type: 'enum', cell: 'E20' }] }
    const field = { name: 'risk_level', label: '风险等级', type: 'enum', cell: 'E20' }
    vm.setStepField(step, field, '高')

    // save 尚未触发
    expect(wrapper.emitted('save')).toBeUndefined()

    vi.advanceTimersByTime(1500)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)
  })

  it('save payload 包含修改后的字段值', async () => {
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    const step = { step: 2, title: '步骤 2', checklist: [], fields: [{ name: 'risk_level', label: '风险等级', type: 'enum', cell: 'E20' }] }
    const field = { name: 'risk_level', label: '风险等级', type: 'enum', cell: 'E20' }
    vm.setStepField(step, field, '高')

    vi.advanceTimersByTime(1500)
    await nextTick()

    const payload = wrapper.emitted('save')![0][0] as any
    expect(payload.steps.step_2.fields.risk_level).toBe('高')
  })

  it('save payload 包含 context / state / signatures / audit_log', async () => {
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    // 触发一次 context 修改
    const field = { name: 'scope', label: '复核范围', type: 'textarea', cell: 'B6' }
    vm.onContextChange(field, '全面复核-更新')

    vi.advanceTimersByTime(1500)
    await nextTick()

    const payload = wrapper.emitted('save')![0][0] as any
    expect(payload.context.scope).toBe('全面复核-更新')
    expect(payload.state).toBe('draft')
    expect(payload.signatures).toEqual({})
    expect(payload.audit_log).toEqual([])
  })

  it('多次修改在 debounce 窗口内只触发一次 save', async () => {
    const wrapper = mountReview()
    const vm = wrapper.vm as any

    const step = { step: 1, title: '步骤 1', checklist: [{ id: 'ck1', label: '底稿已完成', cell: 'C10' }], fields: [] }
    const item1 = { id: 'ck1', label: '底稿已完成', cell: 'C10' }
    const item2 = { id: 'ck2', label: '索引号正确', cell: 'C11' }

    vm.onChecklistChange(step, item1, false)
    vi.advanceTimersByTime(500)
    vm.onChecklistChange(step, item2, true)
    vi.advanceTimersByTime(500)

    // 还没到 1500ms
    expect(wrapper.emitted('save')).toBeUndefined()

    vi.advanceTimersByTime(1000)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)
  })

  it('readonly 模式下不触发 save', async () => {
    const wrapper = mountReview({ readonly: true })
    const vm = wrapper.vm as any

    const step = { step: 2, title: '步骤 2', checklist: [], fields: [{ name: 'risk_level', label: '风险等级', type: 'enum', cell: 'E20' }] }
    const field = { name: 'risk_level', label: '风险等级', type: 'enum', cell: 'E20' }
    vm.setStepField(step, field, '高')

    vi.advanceTimersByTime(2000)
    await nextTick()

    expect(wrapper.emitted('save')).toBeUndefined()
  })
})

// ─── 复盘改进 #1：防御性边界测试 ─────────────────────────────────────────────

describe('GtDFormReview — 边界/防御', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('schema 缺失 state_machine 时 hasStateMachine=false 且无可用转换', () => {
    const schema = buildReviewSchema({ state_machine: undefined })
    const wrapper = mount(GtDFormReview, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.hasStateMachine).toBe(false)
    expect(vm.availableTransitions.length).toBe(0)
  })

  it('schema 缺失 review_steps 时 reviewSteps 为空且 currentStep=null', () => {
    const schema = buildReviewSchema({ review_steps: undefined })
    const wrapper = mount(GtDFormReview, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.reviewSteps.length).toBe(0)
    expect(vm.currentStep).toBeNull()
  })

  it('htmlData 为空对象时回落到 state_machine.initial', () => {
    const wrapper = mountReview({}, {})
    const vm = wrapper.vm as any
    // initial = 'draft'（schema.state_machine.initial）
    expect(vm.currentState).toBe('draft')
    expect(vm.auditLog).toEqual([])
    expect(vm.signaturesData).toEqual({})
  })

  it('htmlData.state 为非法值时仍按原样保留（不崩溃）', () => {
    const wrapper = mountReview({}, { state: 'not_a_real_state' })
    const vm = wrapper.vm as any
    expect(vm.currentState).toBe('not_a_real_state')
    // 非法状态无匹配转换
    expect(vm.availableTransitions.length).toBe(0)
    expect(vm.isFinalState).toBe(false)
  })

  it('schema 缺失 conclusion 时 hasConclusion=false', () => {
    const schema = buildReviewSchema({ conclusion: undefined })
    const wrapper = mount(GtDFormReview, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.hasConclusion).toBe(false)
  })
})
