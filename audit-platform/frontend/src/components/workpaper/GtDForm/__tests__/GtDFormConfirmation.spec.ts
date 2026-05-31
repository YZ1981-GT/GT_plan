/**
 * GtDFormConfirmation.spec.ts — D 类函证子组件单元测试
 *
 * 验证：
 * 1. 函证状态切换：generation→dispatch→reply→discrepancy 阶段流转
 * 2. 差异调节计算：金额差异 / 百分比差异（formula 自动派生）
 * 3. save payload：状态切换后 payload 结构正确
 *
 * 复用 GtDFormQA.spec.ts 范式（Element Plus stubs + fake timers + mount props）
 *
 * Validates: Requirements 2.1, 2.2, 2.3, 2.4
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtDFormConfirmation from '../GtDFormConfirmation.vue'
import { elementPlusStubs } from './stubs'

// ─── Mock GtIndexChip ───────────────────────────────────────────────────────

vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    template: '<span class="gt-index-chip">{{ value }}</span>',
    props: ['value', 'validate'],
  },
}))

// ─── Element Plus stubs（复用共享超集）────────────────────────────────────────

const globalStubs = elementPlusStubs

// ─── Schema / Data builders ─────────────────────────────────────────────────

function buildConfirmationSchema(overrides: Record<string, any> = {}) {
  return {
    component_type: 'd-form',
    form_type: 'confirmation',
    confirmation_type: 'receivable',
    fixed_cells: { A3: '测试公司', A4: '2025-12-31', L3: 'D0-1' },
    fields: [
      { name: 'counterparty', label: '对方单位', type: 'text', cell: 'B5' },
      { name: 'account_code', label: '科目编码', type: 'text', cell: 'B6', readonly: true },
    ],
    confirmation_workflow: {
      stages: [
        {
          stage: 'generation',
          title: '函证生成',
          description: '生成函证清单',
          fields: [
            { name: 'sample_count', label: '抽样数量', type: 'number', cell: 'C10' },
            { name: 'total_amount', label: '总金额', type: 'number', cell: 'C11', render: 'amount' },
          ],
          actions: [
            { name: 'generate_letters', label: '生成函证', api: '/api/confirmation/generate' },
          ],
        },
        {
          stage: 'dispatch',
          title: '函证发出',
          description: '发出函证',
          fields: [
            { name: 'dispatch_date', label: '发出日期', type: 'date', cell: 'D10' },
            { name: 'dispatch_method', label: '发出方式', type: 'enum', enum: ['邮寄', '电子', '当面'], cell: 'D11' },
            { name: 'dispatch_count', label: '发出数量', type: 'number', cell: 'D12' },
          ],
        },
        {
          stage: 'reply',
          title: '回函收集',
          description: '收集回函',
          fields: [
            { name: 'reply_count', label: '回函数量', type: 'number', cell: 'E10' },
            { name: 'reply_amount', label: '回函金额', type: 'number', cell: 'E11', render: 'amount' },
            { name: 'book_amount', label: '账面金额', type: 'number', cell: 'E12', render: 'amount' },
            { name: 'variance_amount', label: '差异金额', type: 'number', cell: 'E13', render: 'amount', readonly: true, formula: 'reply_amount - book_amount' },
            { name: 'variance_pct', label: '差异百分比', type: 'percent', cell: 'E14', readonly: true, formula: '(reply_amount - book_amount) / book_amount * 100' },
          ],
        },
        {
          stage: 'discrepancy',
          title: '差异调节',
          description: '处理差异',
          fields: [
            { name: 'discrepancy_reason', label: '差异原因', type: 'textarea', cell: 'F10' },
            { name: 'resolution', label: '调节结论', type: 'enum', enum: ['已调节', '无需调节', '需进一步核实'], cell: 'F11' },
          ],
        },
      ],
    },
    dynamic_table: {
      max_rows: 100,
      columns: {
        B: { field: 'seq', label: '序号', type: 'number', readonly: true, width: 60 },
        C: { field: 'counterparty_name', label: '对方单位', type: 'text' },
        D: { field: 'account_balance', label: '账面余额', type: 'number', render: 'amount' },
        E: { field: 'reply_amount', label: '回函金额', type: 'number', render: 'amount' },
        F: { field: 'discrepancy', label: '差异', type: 'number', render: 'amount', readonly: true, formula: 'account_balance - reply_amount' },
        G: { field: 'receipt_status', label: '回函状态', type: 'enum', enum: ['已回函相符', '已回函不符', '未回函'], render: 'tag' },
      },
    },
    conclusion: {
      mode: 'composite',
      audit_explanation_field: {
        name: 'audit_explanation',
        label: '审计说明',
        type: 'textarea',
        max_length: 2000,
        hint: '请说明函证程序的执行情况及结论',
      },
      overall_conclusion_field: {
        name: 'overall_conclusion',
        label: '整体结论',
        required: true,
        enum: [
          { value: 'confirmed', label: '函证相符', class: 'success', icon: 'CircleCheckFilled' },
          { value: 'minor_diff', label: '存在微小差异', class: 'warning', icon: 'WarningFilled' },
          { value: 'major_diff', label: '存在重大差异', class: 'danger', icon: 'CircleCloseFilled' },
        ],
      },
    },
    ...overrides,
  }
}

function buildHtmlData(overrides: Record<string, any> = {}) {
  return {
    context: {
      counterparty: '北京测试有限公司',
      account_code: '1122',
    },
    workflow: {
      generation: { sample_count: 10, total_amount: 500000 },
      dispatch: { dispatch_date: '2025-03-01', dispatch_method: '邮寄', dispatch_count: 10 },
      reply: { reply_count: 8, reply_amount: 480000, book_amount: 500000, variance_amount: null, variance_pct: null },
      discrepancy: { discrepancy_reason: '', resolution: '' },
    },
    active_stage: 'generation',
    rows: [],
    conclusion: {
      audit_explanation: '',
      overall_conclusion: '',
    },
    ...overrides,
  }
}

function mountConfirmation(propsOverrides: Record<string, any> = {}, dataOverrides: Record<string, any> = {}) {
  return mount(GtDFormConfirmation, {
    props: {
      wpId: 'wp-conf-001',
      sheetName: '应收函证',
      schema: buildConfirmationSchema() as any,
      htmlData: buildHtmlData(dataOverrides),
      ...propsOverrides,
    },
    global: { stubs: globalStubs },
  })
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('GtDFormConfirmation — 函证状态切换', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('初始 active_stage 为 generation，activeStageIdx 为 0', () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any
    expect(vm.activeStageNo).toBe('generation')
    expect(vm.activeStageIdx).toBe(0)
  })

  it('goToStage 切换到 dispatch（idx=1）', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    vm.goToStage(1)
    await nextTick()

    expect(vm.activeStageNo).toBe('dispatch')
    expect(vm.activeStageIdx).toBe(1)
  })

  it('goToStage 切换到 reply（idx=2）', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    vm.goToStage(2)
    await nextTick()

    expect(vm.activeStageNo).toBe('reply')
    expect(vm.activeStageIdx).toBe(2)
  })

  it('goToStage 切换到 discrepancy（idx=3）', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    vm.goToStage(3)
    await nextTick()

    expect(vm.activeStageNo).toBe('discrepancy')
    expect(vm.activeStageIdx).toBe(3)
  })

  it('完整流转路径 generation→dispatch→reply→discrepancy', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    expect(vm.activeStageNo).toBe('generation')

    vm.goToStage(1)
    await nextTick()
    expect(vm.activeStageNo).toBe('dispatch')

    vm.goToStage(2)
    await nextTick()
    expect(vm.activeStageNo).toBe('reply')

    vm.goToStage(3)
    await nextTick()
    expect(vm.activeStageNo).toBe('discrepancy')
  })

  it('goToStage 越界不生效（负数 / 超出 stages.length）', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    vm.goToStage(-1)
    await nextTick()
    expect(vm.activeStageNo).toBe('generation')

    vm.goToStage(99)
    await nextTick()
    expect(vm.activeStageNo).toBe('generation')
  })

  it('stepStatus 返回正确状态', () => {
    const wrapper = mountConfirmation({}, { active_stage: 'reply' })
    const vm = wrapper.vm as any

    // reply is idx=2
    expect(vm.stepStatus(0)).toBe('finish')
    expect(vm.stepStatus(1)).toBe('finish')
    expect(vm.stepStatus(2)).toBe('process')
    expect(vm.stepStatus(3)).toBe('wait')
  })

  it('htmlData.active_stage 初始化为指定阶段', () => {
    const wrapper = mountConfirmation({}, { active_stage: 'discrepancy' })
    const vm = wrapper.vm as any
    expect(vm.activeStageNo).toBe('discrepancy')
    expect(vm.activeStageIdx).toBe(3)
  })
})

describe('GtDFormConfirmation — 差异调节计算', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('setStageField 触发 formula 重算 variance_amount', async () => {
    const wrapper = mountConfirmation({}, { active_stage: 'reply' })
    const vm = wrapper.vm as any

    const replyField = { name: 'reply_amount', label: '回函金额', type: 'number', cell: 'E11', render: 'amount' }
    vm.setStageField('reply', replyField, 480000)
    await nextTick()

    // book_amount=500000, reply_amount=480000 → variance = 480000 - 500000 = -20000
    expect(vm.stageData['reply'].variance_amount).toBe(-20000)
  })

  it('setStageField 触发 formula 重算 variance_pct', async () => {
    const wrapper = mountConfirmation({}, { active_stage: 'reply' })
    const vm = wrapper.vm as any

    const replyField = { name: 'reply_amount', label: '回函金额', type: 'number', cell: 'E11', render: 'amount' }
    vm.setStageField('reply', replyField, 480000)
    await nextTick()

    // (480000 - 500000) / 500000 * 100 = -4
    expect(vm.stageData['reply'].variance_pct).toBe(-4)
  })

  it('金额差异为 0 时百分比差异也为 0', async () => {
    const wrapper = mountConfirmation({}, { active_stage: 'reply' })
    const vm = wrapper.vm as any

    const replyField = { name: 'reply_amount', label: '回函金额', type: 'number', cell: 'E11', render: 'amount' }
    vm.setStageField('reply', replyField, 500000)
    await nextTick()

    // 500000 - 500000 = 0
    expect(vm.stageData['reply'].variance_amount).toBe(0)
    // 0 / 500000 * 100 = 0
    expect(vm.stageData['reply'].variance_pct).toBe(0)
  })

  it('book_amount 修改后 formula 重算', async () => {
    const wrapper = mountConfirmation({}, { active_stage: 'reply' })
    const vm = wrapper.vm as any

    const bookField = { name: 'book_amount', label: '账面金额', type: 'number', cell: 'E12', render: 'amount' }
    vm.setStageField('reply', bookField, 400000)
    await nextTick()

    // reply_amount=480000, book_amount=400000 → variance = 480000 - 400000 = 80000
    expect(vm.stageData['reply'].variance_amount).toBe(80000)
    // 80000 / 400000 * 100 = 20
    expect(vm.stageData['reply'].variance_pct).toBe(20)
  })

  it('setStageField emit field-change 带 workflow 前缀', async () => {
    const wrapper = mountConfirmation({}, { active_stage: 'reply' })
    const vm = wrapper.vm as any

    const replyField = { name: 'reply_amount', label: '回函金额', type: 'number', cell: 'E11', render: 'amount' }
    vm.setStageField('reply', replyField, 480000)
    await nextTick()

    const emitted = wrapper.emitted('field-change')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toMatchObject({
      field_name: 'workflow.reply.reply_amount',
      new_value: 480000,
      cell: 'E11',
    })
  })
})

describe('GtDFormConfirmation — save payload', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('setStageField 后 1.5s debounce 触发 save', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    const field = { name: 'sample_count', label: '抽样数量', type: 'number', cell: 'C10' }
    vm.setStageField('generation', field, 20)

    expect(wrapper.emitted('save')).toBeUndefined()

    vi.advanceTimersByTime(1500)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)
  })

  it('save payload 包含 context / workflow / active_stage / rows / conclusion', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    const field = { name: 'sample_count', label: '抽样数量', type: 'number', cell: 'C10' }
    vm.setStageField('generation', field, 20)

    vi.advanceTimersByTime(1500)
    await nextTick()

    const payload = wrapper.emitted('save')![0][0] as any
    expect(payload.context).toBeDefined()
    expect(payload.context.counterparty).toBe('北京测试有限公司')
    expect(payload.workflow).toBeDefined()
    expect(payload.workflow.generation.sample_count).toBe(20)
    expect(payload.active_stage).toBe('generation')
    expect(payload.rows).toBeDefined()
    expect(Array.isArray(payload.rows)).toBe(true)
    expect(payload.conclusion).toBeDefined()
  })

  it('阶段切换后 save payload 的 active_stage 更新', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    vm.goToStage(2)
    await nextTick()

    // 触发一次字段修改以触发 save
    const field = { name: 'reply_count', label: '回函数量', type: 'number', cell: 'E10' }
    vm.setStageField('reply', field, 8)

    vi.advanceTimersByTime(1500)
    await nextTick()

    const payload = wrapper.emitted('save')![0][0] as any
    expect(payload.active_stage).toBe('reply')
  })

  it('save payload 包含 formula 计算后的值', async () => {
    const wrapper = mountConfirmation({}, { active_stage: 'reply' })
    const vm = wrapper.vm as any

    const field = { name: 'reply_amount', label: '回函金额', type: 'number', cell: 'E11', render: 'amount' }
    vm.setStageField('reply', field, 480000)

    vi.advanceTimersByTime(1500)
    await nextTick()

    const payload = wrapper.emitted('save')![0][0] as any
    expect(payload.workflow.reply.variance_amount).toBe(-20000)
    expect(payload.workflow.reply.variance_pct).toBe(-4)
  })

  it('多次修改在 debounce 窗口内只触发一次 save', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    const field1 = { name: 'sample_count', label: '抽样数量', type: 'number', cell: 'C10' }
    const field2 = { name: 'total_amount', label: '总金额', type: 'number', cell: 'C11', render: 'amount' }

    vm.setStageField('generation', field1, 20)
    vi.advanceTimersByTime(500)
    vm.setStageField('generation', field2, 1000000)
    vi.advanceTimersByTime(500)

    expect(wrapper.emitted('save')).toBeUndefined()

    vi.advanceTimersByTime(1000)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)

    const payload = emitted![0][0] as any
    expect(payload.workflow.generation.sample_count).toBe(20)
    expect(payload.workflow.generation.total_amount).toBe(1000000)
  })

  it('readonly 模式下不触发 save', async () => {
    const wrapper = mountConfirmation({ readonly: true })
    const vm = wrapper.vm as any

    const field = { name: 'sample_count', label: '抽样数量', type: 'number', cell: 'C10' }
    vm.setStageField('generation', field, 20)

    vi.advanceTimersByTime(2000)
    await nextTick()

    expect(wrapper.emitted('save')).toBeUndefined()
  })

  it('conclusion 修改后 save payload 包含结论数据', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    vm.onConclusionFieldChange('audit_explanation')
    vi.advanceTimersByTime(1500)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.conclusion).toBeDefined()
    expect(payload.conclusion).toHaveProperty('audit_explanation')
    expect(payload.conclusion).toHaveProperty('overall_conclusion')
  })

  it('表格行添加后 save payload 包含 rows', async () => {
    const wrapper = mountConfirmation()
    const vm = wrapper.vm as any

    vm.handleAddRow()
    vi.advanceTimersByTime(1500)
    await nextTick()

    const payload = wrapper.emitted('save')![0][0] as any
    expect(payload.rows.length).toBe(1)
    expect(payload.rows[0]).toHaveProperty('counterparty_name')
    expect(payload.rows[0]).toHaveProperty('account_balance')
    expect(payload.rows[0]).toHaveProperty('reply_amount')
  })
})

// ─── 复盘改进 #1：防御性边界测试 ─────────────────────────────────────────────

describe('GtDFormConfirmation — 边界/防御', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('schema 缺失 confirmation_workflow 时 stages 为空且 activeStageIdx=0', () => {
    const schema = buildConfirmationSchema({ confirmation_workflow: undefined })
    const wrapper = mount(GtDFormConfirmation, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.stages.length).toBe(0)
    expect(vm.activeStageIdx).toBe(0)
    expect(vm.currentStage).toBeNull()
  })

  it('book_amount=0 时差异百分比公式除零不产生 NaN/Infinity', () => {
    // 复盘改进 #1：formula 除零防御 —— evalFormula 对非有限结果返回 null，字段保持原值
    const wrapper = mountConfirmation({}, { active_stage: 'reply' })
    const vm = wrapper.vm as any

    const bookField = { name: 'book_amount', label: '账面金额', type: 'number', cell: 'E12', render: 'amount' }
    vm.setStageField('reply', bookField, 0)
    vi.advanceTimersByTime(1500)

    // variance_amount = reply_amount(480000) - 0 = 480000（有限，正常计算）
    expect(vm.stageData['reply'].variance_amount).toBe(480000)
    // variance_pct 除零 → Infinity → evalFormula 返回 null → 不写入 NaN/Infinity
    const pct = vm.stageData['reply'].variance_pct
    expect(Number.isNaN(pct)).toBe(false)
    expect(pct).not.toBe(Infinity)
  })

  it('formula 引用缺失字段时按 0 处理不崩溃', () => {
    const wrapper = mountConfirmation({}, {
      active_stage: 'reply',
      workflow: { reply: { reply_amount: 100000 } }, // book_amount 缺失
    })
    const vm = wrapper.vm as any

    const replyField = { name: 'reply_amount', label: '回函金额', type: 'number', cell: 'E11', render: 'amount' }
    vm.setStageField('reply', replyField, 100000)

    // book_amount 缺失按 0 → variance_amount = 100000 - 0 = 100000
    expect(vm.stageData['reply'].variance_amount).toBe(100000)
  })

  it('htmlData 为空对象时各 stage bucket 初始化不崩溃', () => {
    const wrapper = mountConfirmation({}, {})
    const vm = wrapper.vm as any
    expect(vm.stageData['generation']).toBeDefined()
    expect(vm.tableRows).toEqual([])
    expect(vm.conclusionData.audit_explanation).toBe('')
    expect(vm.conclusionData.overall_conclusion).toBe('')
  })

  it('schema 缺失 conclusion 时 hasComposite=false', () => {
    const schema = buildConfirmationSchema({ conclusion: undefined })
    const wrapper = mount(GtDFormConfirmation, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.hasComposite).toBe(false)
  })

  it('达到 max_rows 时 handleAddRow 不再新增', () => {
    const schema = buildConfirmationSchema()
    ;(schema as any).dynamic_table.max_rows = 2
    const wrapper = mount(GtDFormConfirmation, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    vm.handleAddRow()
    vm.handleAddRow()
    expect(vm.tableRows.length).toBe(2)
    expect(vm.reachedMaxRows).toBe(true)
    vm.handleAddRow() // 超限不增
    expect(vm.tableRows.length).toBe(2)
  })
})
