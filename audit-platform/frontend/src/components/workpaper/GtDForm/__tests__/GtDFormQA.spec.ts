/**
 * GtDFormQA.spec.ts — D 类是否问答型子组件单元测试
 *
 * spec workpaper-html-renderer Task 8.8（业务模式判定 D2-13 输出测试）
 *
 * 验证：
 * 1. 4 题 × N 组合矩阵渲染 + 增删组合
 * 2. auto_derivation 规则引擎（业务模式判定）：
 *    - q1=是 q2=是 q3=否 → '持有以收取合同现金流量' / '摊余成本' / 'BS-008'
 *    - q1=否 → '其他业务模式' / 'BS-002'
 *    - q1=是 q2=是 q3=是 q4=是 → 'FVOCI'
 *    - q2=否 → 'SPPI 失败' / 强制 FVTPL
 * 3. 不适用 / has_empty 兜底 → rule_default_pending
 * 4. 添加组合按钮 → combinations.length 增加
 * 5. 删除组合 → 缩减
 *
 * Validates: Requirements 3.5（D 子模式 3：是否问答型业务模式判定）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtDFormQA from '../GtDFormQA.vue'

// Element Plus stubs
const globalStubs = {
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
      '<input class="el-input" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', $event.target.value)" />',
    props: ['modelValue', 'type', 'rows', 'placeholder', 'maxlength', 'showWordLimit', 'disabled', 'size', 'readonly'],
    emits: ['update:modelValue', 'change'],
  },
  'el-icon': { template: '<i class="el-icon"><slot /></i>' },
  'el-tooltip': {
    template: '<div class="el-tooltip"><slot /><slot name="content" /></div>',
    props: ['content', 'placement', 'showAfter', 'popperClass'],
  },
  'el-button': {
    template:
      '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'icon', 'link'],
    emits: ['click'],
  },
  'el-radio-group': {
    template: '<div class="el-radio-group"><slot /></div>',
    props: ['modelValue', 'disabled', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-radio': {
    template:
      '<label class="el-radio" :data-value="value" @click="$parent.$emit(\'update:modelValue\', value); $parent.$emit(\'change\', value)"><slot /></label>',
    props: ['value'],
  },
  'el-tag': {
    template:
      '<span class="el-tag" :data-type="type" :data-effect="effect"><slot /></span>',
    props: ['type', 'size', 'effect'],
  },
  'el-empty': {
    template: '<div class="el-empty" :data-description="description" />',
    props: ['imageSize', 'description'],
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
  InfoFilled: { template: '<span class="info-filled" />' },
  QuestionFilledIcon: { template: '<span class="question-filled" />' },
  PlusIcon: { template: '<span class="plus-icon" />' },
  DeleteIcon: { template: '<span class="delete-icon" />' },
}

// ─── Build D2-13-like schema for business model derivation tests ────────────

function buildD2_13Schema() {
  return {
    component_type: 'd-form',
    form_type: 'qa',
    fixed_cells: { A3: '宜宾大药房', A4: '2025-12-31', E3: 'D2-13' },
    fields: [
      {
        name: 'audit_objective',
        label: '审计目标',
        type: 'textarea',
        cell: 'B6',
        readonly: true,
        default: '判定金融资产业务模式',
      },
      {
        name: 'financial_asset_scope',
        label: '应收账款明细范围',
        type: 'text',
        cell: 'B8',
      },
    ],
    qa_matrix: {
      mode: 'matrix',
      questions: [
        { id: 'q1', seq: '题 1', question: '持有目的是否为收取合同现金流量？', help_text: '...' },
        { id: 'q2', seq: '题 2', question: '合同现金流量是否仅为本金和利息（SPPI 测试）？' },
        { id: 'q3', seq: '题 3', question: '是否存在频繁出售情形？' },
        { id: 'q4', seq: '题 4', question: '出售目的是否为应对信用风险集中度？' },
      ],
      combinations: {
        start_col: 'C',
        end_col: 'dynamic',
        max_combinations: 10,
        column_def: {
          combination_name: { max_length: 100 },
        },
      },
    },
    auto_derivation: {
      description: '基于 4 题答案派生',
      rules: [
        {
          id: 'rule_held_to_collect',
          when: "q1=='是' AND q2=='是' AND q3=='否'",
          set: {
            business_model: '持有以收取合同现金流量',
            measurement_class: '摊余成本',
            report_line: 'BS-008',
            confidence: 'high',
          },
        },
        {
          id: 'rule_held_to_collect_and_sell',
          when: "q1=='是' AND q2=='是' AND q3=='是' AND q4=='是'",
          set: {
            business_model: '既以收取合同现金流量为目标又以出售为目标',
            measurement_class: 'FVOCI',
            report_line: 'BS-018',
            confidence: 'high',
          },
        },
        {
          id: 'rule_other_business_model',
          when: "q1=='否' OR (q3=='是' AND q4=='否')",
          set: {
            business_model: '其他业务模式',
            measurement_class: 'FVTPL',
            report_line: 'BS-002',
            confidence: 'high',
          },
        },
        {
          id: 'rule_sppi_failed',
          when: "q2=='否'",
          set: {
            business_model: '现金流量不符合 SPPI 测试',
            measurement_class: 'FVTPL（强制以公允价值计量）',
            report_line: 'BS-002',
            confidence: 'high',
          },
        },
        {
          id: 'rule_default_pending',
          when: "q1=='不适用' OR q2=='不适用' OR has_empty",
          set: {
            business_model: '待判定（请完成 4 题）',
            measurement_class: '—',
            report_line: '—',
            confidence: 'pending',
          },
        },
      ],
    },
    notes: [
      { id: 'note_1', label: '注 1：业务模式判定要点', content: '...', default_collapsed: true },
    ],
  }
}

function buildHtmlData(combinations: any[] = []) {
  return {
    context: {
      audit_objective: '判定金融资产业务模式',
      financial_asset_scope: '应收账款全部明细',
    },
    combinations,
    active_note_ids: [],
  }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('GtDFormQA — 业务模式判定（D2-13 推导）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('q1=是 q2=是 q3=否 → 持有以收取合同现金流量 + 摊余成本 + BS-008', () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '标准应收',
            q1_answer: '是',
            q2_answer: '是',
            q3_answer: '否',
            q4_answer: '',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const d = vm.derivations[0]
    expect(d.rule_id).toBe('rule_held_to_collect')
    expect(d.business_model).toBe('持有以收取合同现金流量')
    expect(d.measurement_class).toBe('摊余成本')
    expect(d.report_line).toBe('BS-008')
    expect(d.confidence).toBe('high')
  })

  it('q1=否 → 其他业务模式 + FVTPL + BS-002', () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '出售为主',
            q1_answer: '否',
            q2_answer: '是',
            q3_answer: '是',
            q4_answer: '否',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const d = vm.derivations[0]
    expect(d.rule_id).toBe('rule_other_business_model')
    expect(d.business_model).toBe('其他业务模式')
    expect(d.report_line).toBe('BS-002')
  })

  it('q1=是 q2=是 q3=是 q4=是 → FVOCI + BS-018', () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '兼具持有与出售',
            q1_answer: '是',
            q2_answer: '是',
            q3_answer: '是',
            q4_answer: '是',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const d = vm.derivations[0]
    expect(d.rule_id).toBe('rule_held_to_collect_and_sell')
    expect(d.measurement_class).toBe('FVOCI')
    expect(d.report_line).toBe('BS-018')
  })

  it('q2=否 → SPPI 失败 + 强制 FVTPL', () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '衍生工具',
            q1_answer: '是',
            q2_answer: '否',
            q3_answer: '否',
            q4_answer: '否',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const d = vm.derivations[0]
    // q1=='否' branch is mutually exclusive, q2='否' rule triggers
    // rule precedence: held_to_collect (no) → held_to_collect_and_sell (no) →
    // other_business_model (q1='是' so the OR with q3='是 AND q4=否' is false) → sppi_failed (q2='否') ✓
    expect(d.rule_id).toBe('rule_sppi_failed')
    expect(d.business_model).toBe('现金流量不符合 SPPI 测试')
    expect(d.report_line).toBe('BS-002')
  })

  it('q1=不适用 → fallback 到 rule_default_pending', () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '不适用项',
            q1_answer: '不适用',
            q2_answer: '是',
            q3_answer: '否',
            q4_answer: '',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const d = vm.derivations[0]
    expect(d.rule_id).toBe('rule_default_pending')
    expect(d.business_model).toBe('待判定（请完成 4 题）')
    expect(d.confidence).toBe('pending')
  })

  it('全空（has_empty）→ fallback 到 rule_default_pending', () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '空白',
            q1_answer: '',
            q2_answer: '',
            q3_answer: '',
            q4_answer: '',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const d = vm.derivations[0]
    // has_empty: any answer empty → rule_default_pending
    expect(d.rule_id).toBe('rule_default_pending')
    expect(d.confidence).toBe('pending')
  })

  it('多个组合各自独立派生', () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '标准应收',
            q1_answer: '是',
            q2_answer: '是',
            q3_answer: '否',
            q4_answer: '',
          },
          {
            combination_name: '出售为主',
            q1_answer: '否',
            q2_answer: '是',
            q3_answer: '是',
            q4_answer: '否',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.derivations.length).toBe(2)
    expect(vm.derivations[0].rule_id).toBe('rule_held_to_collect')
    expect(vm.derivations[1].rule_id).toBe('rule_other_business_model')
  })
})

describe('GtDFormQA — 组合增删', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('handleAddCombination 增加组合数', async () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.combinations.length).toBe(0)
    vm.handleAddCombination()
    await nextTick()
    expect(vm.combinations.length).toBe(1)
    // emit field-change for length
    const emitted = wrapper.emitted('field-change')
    expect(emitted).toBeDefined()
  })

  it('达到 max_combinations 时不再添加', async () => {
    const initialCombos = Array.from({ length: 10 }, (_, i) => ({
      combination_name: `组合${i + 1}`,
      q1_answer: '',
      q2_answer: '',
      q3_answer: '',
      q4_answer: '',
    }))
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData(initialCombos),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.combinations.length).toBe(10)
    expect(vm.reachedMaxCombinations).toBe(true)
    vm.handleAddCombination()
    await nextTick()
    expect(vm.combinations.length).toBe(10) // unchanged
  })

  it('handleRemoveCombination 删除指定索引组合', async () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '组合1',
            q1_answer: '',
            q2_answer: '',
            q3_answer: '',
            q4_answer: '',
          },
          {
            combination_name: '组合2',
            q1_answer: '',
            q2_answer: '',
            q3_answer: '',
            q4_answer: '',
          },
          {
            combination_name: '组合3',
            q1_answer: '',
            q2_answer: '',
            q3_answer: '',
            q4_answer: '',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.combinations.length).toBe(3)
    vm.handleRemoveCombination(1) // remove middle
    await nextTick()
    expect(vm.combinations.length).toBe(2)
    expect(vm.combinations[0].combination_name).toBe('组合1')
    expect(vm.combinations[1].combination_name).toBe('组合3')
  })

  it('handleRemoveLastCombination 删除末位', async () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '组合1',
            q1_answer: '',
            q2_answer: '',
            q3_answer: '',
            q4_answer: '',
          },
          {
            combination_name: '组合2',
            q1_answer: '',
            q2_answer: '',
            q3_answer: '',
            q4_answer: '',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.handleRemoveLastCombination()
    await nextTick()
    expect(vm.combinations.length).toBe(1)
    expect(vm.combinations[0].combination_name).toBe('组合1')
  })
})

describe('GtDFormQA — debounce save 包含派生快照', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('答案变更触发 debounce save 携带派生结果', async () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '标准应收',
            q1_answer: '是',
            q2_answer: '是',
            q3_answer: '否',
            q4_answer: '',
          },
        ]),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onAnswerChange(0, 'q1')
    await nextTick()

    // Save not yet emitted
    expect(wrapper.emitted('save')).toBeUndefined()

    vi.advanceTimersByTime(1600)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.combinations).toBeDefined()
    expect(payload.combinations.length).toBe(1)
    // Save payload contains enriched derivation snapshots
    expect(payload.combinations[0].business_model).toBe('持有以收取合同现金流量')
    expect(payload.combinations[0].report_line).toBe('BS-008')
  })

  it('readonly 模式不触发 save', async () => {
    const wrapper = mount(GtDFormQA, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: buildD2_13Schema() as any,
        htmlData: buildHtmlData([
          {
            combination_name: '标准',
            q1_answer: '是',
            q2_answer: '是',
            q3_answer: '否',
            q4_answer: '',
          },
        ]),
        readonly: true,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.onAnswerChange(0, 'q1')
    vi.advanceTimersByTime(1600)
    await nextTick()

    expect(wrapper.emitted('save')).toBeUndefined()
  })
})
