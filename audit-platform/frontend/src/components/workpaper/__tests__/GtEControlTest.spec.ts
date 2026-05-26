/**
 * GtEControlTest.spec.ts — E 类控制测试组件单元测试
 *
 * spec workpaper-html-renderer Task 6.3
 *
 * 验证：
 * 1. 3 种 test_type 路由（summary / single / evaluation_step）
 * 2. evaluation_step 渲染 el-steps + 6 步骤
 * 3. 步骤导航：advanceStep 推进 activeStepNo + emit step-advance
 * 4. 4 互斥结论 emit conclusion-change（control_effective / extended_effective /
 *    deviation_remains / systemic_deviation）
 * 5. ProcedureTrimming 联动建议写回：
 *    - control_effective / extended_effective → suggestion_type='reduce'
 *    - deviation_remains → suggestion_type='increase'
 *    - systemic_deviation → suggestion_type='full' + confidence='required'
 *
 * Validates: Requirements 3.6（E 类 322 sheet 6 步骤决策树 + 4 互斥结论 + 联动建议）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtEControlTest from '../GtEControlTest.vue'

// Mock GtIndexChip
vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    template: '<span class="gt-index-chip-mock">{{ value }}</span>',
    props: ['value', 'validate'],
    emits: ['click'],
  },
}))

// Element Plus stubs (lightweight, focused on E component needs)
const globalStubs = {
  'el-steps': {
    template: '<div class="el-steps" :data-active="active"><slot /></div>',
    props: ['active', 'processStatus', 'finishStatus', 'alignCenter'],
  },
  'el-step': {
    template:
      '<div class="el-step" :data-title="title" :data-description="description"></div>',
    props: ['title', 'description', 'status'],
  },
  'el-button': {
    template:
      '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'icon', 'link'],
    emits: ['click'],
  },
  'el-tag': {
    template:
      '<span class="el-tag" :data-type="type" :data-effect="effect"><slot /></span>',
    props: ['type', 'size', 'effect'],
  },
  'el-radio-group': {
    template: '<div class="el-radio-group"><slot /></div>',
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'change'],
  },
  'el-radio': {
    template:
      '<label class="el-radio" :data-value="value" @click="$parent.$emit(\'update:modelValue\', value); $parent.$emit(\'change\', value)"><slot /></label>',
    props: ['value'],
  },
  'el-radio-button': {
    template:
      '<label class="el-radio-button" :data-label="label" @click="$parent.$emit(\'update:modelValue\', label)"><slot /></label>',
    props: ['label'],
  },
  'el-form': {
    template: '<form class="el-form"><slot /></form>',
    props: ['model', 'labelPosition', 'disabled'],
  },
  'el-form-item': {
    template: '<div class="el-form-item" :data-label="label"><slot /></div>',
    props: ['label', 'required'],
  },
  'el-input': {
    template:
      '<input class="el-input" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['modelValue', 'type', 'rows', 'placeholder', 'maxlength', 'showWordLimit', 'disabled', 'size', 'clearable'],
    emits: ['update:modelValue'],
  },
  'el-input-number': {
    template:
      '<input class="el-input-number" type="number" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', Number($event.target.value))" />',
    props: ['modelValue', 'min', 'max', 'disabled', 'size', 'controlsPosition', 'precision'],
    emits: ['update:modelValue'],
  },
  'el-select': {
    template: '<select class="el-select" :value="modelValue" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
    props: ['modelValue', 'disabled', 'multiple', 'collapseTags', 'collapseTagsTooltip', 'size', 'clearable', 'placeholder'],
    emits: ['update:modelValue'],
  },
  'el-option': {
    template: '<option :value="value">{{ label }}</option>',
    props: ['label', 'value'],
  },
  'el-table': {
    template: '<div class="el-table"></div>',
    props: ['data', 'border', 'size', 'rowClassName', 'emptyText'],
  },
  'el-table-column': {
    template: '<div class="el-table-column"></div>',
    props: ['label', 'minWidth', 'fixed', 'width', 'resizable'],
  },
  'el-collapse': {
    template: '<div class="el-collapse"><slot /></div>',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-collapse-item': {
    template: '<div class="el-collapse-item" :data-name="name" :data-title="title"><slot /></div>',
    props: ['name', 'title'],
  },
  'el-icon': { template: '<i class="el-icon"><slot /></i>' },
  'InfoFilled': { template: '<span class="info-filled" />' },
  'PlusIcon': { template: '<span class="plus-icon" />' },
}

// ─── Schema builders ────────────────────────────────────────────────────────

function buildEvaluationStepSchema() {
  return {
    test_type: 'evaluation_step',
    fixed_cells: { A3: '宜宾大药房', A4: '2025-12-31', I3: 'C11-2' },
    fields: [
      { name: 'control_no', label: '控制编号', type: 'text', required: true, cell: 'B6' },
      { name: 'control_name', label: '控制名称', type: 'text', required: true, cell: 'B7' },
    ],
    steps: [
      {
        step: 1,
        id: 'step1_random_or_systemic',
        title: '步骤一：偏差是否随机发生？',
        description: '判定随机 / 系统性',
        fields: [
          {
            name: 'is_random',
            label: '是否随机',
            type: 'enum',
            enum: ['是', '否'],
            cell: 'B14',
          },
          {
            name: 'analysis_step1',
            label: '评价分析过程',
            type: 'textarea',
            required: true,
            cell: 'B16',
          },
        ],
        next_logic: [
          { when: "is_random == '是'", goto: 2 },
          { when: "is_random == '否'", goto: 6, reason: '系统性偏差直接进入步骤六' },
        ],
      },
      {
        step: 2,
        id: 'step2_extend_sample',
        title: '步骤二：是否扩大样本测试？',
        fields: [
          {
            name: 'extend_decision',
            label: '扩大测试决策',
            type: 'enum',
            enum: ['扩大', '不扩大'],
            cell: 'B23',
          },
        ],
        next_logic: [
          { when: "extend_decision == '扩大'", goto: 3 },
          { when: "extend_decision == '不扩大'", goto: 6 },
        ],
      },
      {
        step: 3,
        id: 'step3_extended_test_result',
        title: '步骤三：扩大测试结果如何？',
        fields: [
          {
            name: 'extended_test_result',
            label: '扩大测试结果',
            type: 'enum',
            enum: ['无新偏差', '有新偏差'],
            cell: 'B35',
          },
        ],
        next_logic: [
          { when: "extended_test_result == '无新偏差'", goto: 4 },
          { when: "extended_test_result == '有新偏差'", goto: 5 },
        ],
      },
      {
        step: 4,
        id: 'step4_root_cause_random',
        title: '步骤四：原偏差根本原因（随机偏差路径）',
        fields: [
          { name: 'root_cause', label: '根本原因分析', type: 'textarea', cell: 'B43', required: true },
        ],
        next_logic: [{ when: 'true', goto: 6, conclusion_hint: 'control_effective' }],
      },
      {
        step: 5,
        id: 'step5_persistent_deviation',
        title: '步骤五：扩大测试仍有偏差',
        fields: [
          { name: 'pattern_analysis', label: '偏差模式分析', type: 'textarea', cell: 'B53', required: true },
        ],
        next_logic: [{ when: 'true', goto: 6, conclusion_hint: 'deviation_remains' }],
      },
      {
        step: 6,
        id: 'step6_final_conclusion',
        title: '步骤六：最终评价结论',
        fields: [
          {
            name: 'final_conclusion',
            label: '最终结论',
            type: 'enum',
            cell: 'B63',
            required: true,
            enum: ['control_effective', 'extended_effective', 'deviation_remains', 'systemic_deviation'],
          },
        ],
        is_terminal: true,
      },
    ],
    conclusion: {
      mode: 'single',
      mutual_exclusive: true,
      cell: 'B63',
      options: [
        { value: 'control_effective', label: '控制有效', class: 'success' },
        { value: 'extended_effective', label: '扩大测试有效', class: 'warning' },
        { value: 'deviation_remains', label: '仍有偏差', class: 'danger' },
        { value: 'systemic_deviation', label: '系统性偏差', class: 'danger' },
      ],
    },
  }
}

function buildSummarySchema() {
  return {
    test_type: 'summary',
    fixed_cells: { A3: '宜宾大药房', A4: '2025-12-31', O3: 'C12' },
    dynamic_table: {
      start_row: 8,
      end_row: 'dynamic',
      header_row: 7,
      columns: {
        A: { field: 'sub_process', label: '子流程', type: 'text' },
        B: { field: 'control_no', label: '控制编号', type: 'text' },
      },
    },
  }
}

function buildSingleSchema() {
  return {
    test_type: 'single',
    fixed_cells: { A3: '宜宾大药房', A4: '2025-12-31', J3: 'C12-1-1' },
    segments: [
      {
        id: 'basic_info',
        title: '一、基本信息',
        fields: [{ name: 'control_no', label: '控制编号', type: 'text', required: true }],
      },
      {
        id: 'test_procedure',
        title: '二、测试程序',
        fields: [{ name: 'test_method', label: '测试方法', type: 'multi_enum', enum: ['询问', '观察'] }],
      },
    ],
    conclusion: {
      mode: 'single',
      options: [
        { value: 'control_effective', label: '控制有效', class: 'success' },
        { value: 'deviation_remains', label: '仍有偏差', class: 'danger' },
      ],
    },
  }
}

// ─── Test suites ────────────────────────────────────────────────────────────

describe('GtEControlTest — test_type 路由', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('test_type=evaluation_step 渲染 el-steps stepper', () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('.el-steps').exists()).toBe(true)
    // 6 steps in schema
    const steps = wrapper.findAll('.el-step')
    expect(steps.length).toBe(6)
  })

  it('test_type=summary 渲染汇总表（不渲染 el-steps）', () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '控制测试汇总表',
        schema: buildSummarySchema(),
        htmlData: { rows: [] },
      },
      global: { stubs: globalStubs },
    })

    // No el-steps stepper for summary
    expect(wrapper.find('.el-steps').exists()).toBe(false)
    expect(wrapper.find('.el-table').exists()).toBe(true)
  })

  it('test_type=single 渲染 segments 表单（不渲染 el-steps / el-table）', () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '单条控制测试',
        schema: buildSingleSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('.el-steps').exists()).toBe(false)
    // single mode renders el-form per segment
    const forms = wrapper.findAll('.el-form')
    // 2 segments + 1 conclusion form area => at least 2 forms
    expect(forms.length).toBeGreaterThanOrEqual(2)
  })
})

describe('GtEControlTest — evaluation_step stepper 校验', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('初始 activeStepNo=1 (第一步)', () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.activeStepNo).toBe(1)
    expect(vm.currentStep.step).toBe(1)
    expect(vm.activeStepIdx).toBe(0)
  })

  it('advanceStep 按 next_logic 推进到 step 2', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    // Set step 1 answer is_random='是' → goto 2
    vm.evalData.is_random = '是'
    vm.advanceStep()
    await nextTick()

    expect(vm.activeStepNo).toBe(2)
    const emitted = wrapper.emitted('step-advance')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toBe(2)
  })

  it('advanceStep 系统性偏差路径直接跳转到 step 6', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.evalData.is_random = '否'
    vm.advanceStep()
    await nextTick()

    expect(vm.activeStepNo).toBe(6)
  })

  it('isTerminalStep 在 step 6 为 true', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: { active_step: 6 },
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.activeStepNo).toBe(6)
    expect(vm.isTerminalStep).toBe(true)
  })

  it('goToStep 跳转到任意有效 step', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.goToStep(3) // index 3 = step 4
    await nextTick()
    expect(vm.activeStepNo).toBe(4)

    const emitted = wrapper.emitted('step-advance')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toBe(4)
  })

  it('htmlData.active_step 持久化恢复', () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: { active_step: 4 },
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.activeStepNo).toBe(4)
  })
})

describe('GtEControlTest — 4 互斥结论', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('选择 control_effective 触发 conclusion-change emit', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onConclusionChange('control_effective')
    await nextTick()

    const emitted = wrapper.emitted('conclusion-change')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toBe('control_effective')
    expect(vm.conclusionValue).toBe('control_effective')
  })

  it('依次选择 4 个互斥结论触发对应 emit', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const conclusions = [
      'control_effective',
      'extended_effective',
      'deviation_remains',
      'systemic_deviation',
    ]
    for (const c of conclusions) {
      vm.onConclusionChange(c)
    }
    await nextTick()

    const emitted = wrapper.emitted('conclusion-change')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(4)
    expect(emitted!.map((e: any[]) => e[0])).toEqual(conclusions)
  })

  it('结论 conclusionOptions 长度为 4', () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.conclusionOptions.length).toBe(4)
    expect(vm.conclusionOptions.map((o: any) => o.value)).toEqual([
      'control_effective',
      'extended_effective',
      'deviation_remains',
      'systemic_deviation',
    ])
  })
})

describe('GtEControlTest — ProcedureTrimming 联动建议', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('control_effective → suggestion_type=reduce + confidence=high', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onConclusionChange('control_effective')
    await nextTick()

    const emitted = wrapper.emitted('trigger-procedure-trimming-suggestion')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)
    const payload = emitted![0][0] as any
    expect(payload.wp_id).toBe('wp-001')
    expect(payload.sheet_name).toBe('评价控制偏差')
    expect(payload.conclusion).toBe('control_effective')
    expect(payload.suggestion_type).toBe('reduce')
    expect(payload.confidence).toBe('high')
    expect(payload.source).toBe('e-control-test')
  })

  it('extended_effective → suggestion_type=reduce + confidence=high', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onConclusionChange('extended_effective')
    await nextTick()

    const emitted = wrapper.emitted('trigger-procedure-trimming-suggestion')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.suggestion_type).toBe('reduce')
    expect(payload.confidence).toBe('high')
  })

  it('deviation_remains → suggestion_type=increase + confidence=high', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onConclusionChange('deviation_remains')
    await nextTick()

    const emitted = wrapper.emitted('trigger-procedure-trimming-suggestion')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.suggestion_type).toBe('increase')
    expect(payload.confidence).toBe('high')
  })

  it('systemic_deviation → suggestion_type=full + confidence=required', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onConclusionChange('systemic_deviation')
    await nextTick()

    const emitted = wrapper.emitted('trigger-procedure-trimming-suggestion')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.suggestion_type).toBe('full')
    expect(payload.confidence).toBe('required')
  })

  it('空结论不触发 trigger-procedure-trimming-suggestion', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onConclusionChange('')
    await nextTick()

    expect(wrapper.emitted('trigger-procedure-trimming-suggestion')).toBeUndefined()
  })

  it('未知结论值不触发 trigger-procedure-trimming-suggestion', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onConclusionChange('some_unknown_value')
    await nextTick()

    // suggestion_type 'none' 不发出 trigger 事件
    expect(wrapper.emitted('trigger-procedure-trimming-suggestion')).toBeUndefined()
    // 但 conclusion-change 仍发出
    expect(wrapper.emitted('conclusion-change')).toBeDefined()
  })
})

describe('GtEControlTest — debounce save', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('结论变更触发 debounce save', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onConclusionChange('control_effective')
    await nextTick()

    // Save not yet emitted (debounce 1.5s)
    expect(wrapper.emitted('save')).toBeUndefined()

    vi.advanceTimersByTime(1600)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.conclusion).toBe('control_effective')
  })

  it('readonly 模式不触发 save', async () => {
    const wrapper = mount(GtEControlTest, {
      props: {
        wpId: 'wp-001',
        sheetName: '评价控制偏差',
        schema: buildEvaluationStepSchema(),
        htmlData: {},
        readonly: true,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onConclusionChange('control_effective')
    vi.advanceTimersByTime(1600)
    await nextTick()

    expect(wrapper.emitted('save')).toBeUndefined()
  })
})
