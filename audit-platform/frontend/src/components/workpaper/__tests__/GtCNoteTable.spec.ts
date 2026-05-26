/**
 * GtCNoteTable.spec.ts — C 类附注披露嵌套表组件单元测试
 *
 * spec workpaper-html-renderer Task 10.5
 *
 * 验证：
 * 1. 默认 standard='listed_standalone' → 仅显示 listed 子表，soe 专属子表隐藏
 * 2. 切换到 soe → ElMessageBox.confirm 弹出 + 取消保留前值
 * 3. 切换到 soe + 确认 → soe 专属子表可见 + listed 专属子表隐藏 +
 *    共有字段值保留（context.monetary_unit 等）
 * 4. inheritance_rules 实时校验：
 *    - single_provision 子表 sum(book_balance) ↔ by_category_period_end.cat_single
 *    - 不一致时 ruleStatuses[X].status='mismatch' + diff 计算
 * 5. onHideSubTable / onRestoreSubTable 软标记隐藏 + emit subtable-toggle
 * 6. onSyncToDisclosureNotes → emit sync-to-disclosure-notes 携带 section_id payload
 *
 * Validates: Requirements 3.4（C 类 166 sheet 版本切换 + 子表合计联动）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

// ─── Mocks ──────────────────────────────────────────────────────────────────

// Mock vue-router
const mockRoute = {
  params: { projectId: 'proj-123' },
  path: '/projects/proj-123/workpapers/wp-001/edit',
  query: {},
}
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
}))

// Mock apiProxy
const mockApiPost = vi.fn(() => Promise.resolve({ rows_synced: 5 }))
vi.mock('@/services/apiProxy', () => ({
  api: {
    post: (...args: any[]) => mockApiPost(...args),
  },
}))

// Mock element-plus ElMessageBox + ElMessage
const mockConfirm = vi.fn(() => Promise.resolve('confirm'))
const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()
const mockMessageWarning = vi.fn()
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessageBox: {
      confirm: (...args: any[]) => mockConfirm(...args),
    },
    ElMessage: {
      success: (...args: any[]) => mockMessageSuccess(...args),
      error: (...args: any[]) => mockMessageError(...args),
      warning: (...args: any[]) => mockMessageWarning(...args),
    },
  }
})

// Mock GtIndexChip
vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    template: '<span class="gt-index-chip-mock" @click="$emit(\'click\')">{{ value }}</span>',
    props: ['value', 'validate'],
    emits: ['click'],
  },
}))

// Mock formatAmount
vi.mock('@/utils/formatAmount', () => ({
  formatAmount: (v: any) =>
    v == null || v === '' ? '' : Number(v).toLocaleString('zh-CN'),
}))

// Now import component AFTER mocks
import GtCNoteTable from '../GtCNoteTable.vue'

// ─── Element Plus stubs ─────────────────────────────────────────────────────

const globalStubs = {
  'el-form': {
    template: '<form class="el-form"><slot /></form>',
    props: ['model', 'labelPosition', 'labelWidth', 'inline', 'disabled', 'size'],
  },
  'el-form-item': {
    template: '<div class="el-form-item" :data-label="label"><slot /></div>',
    props: ['label'],
  },
  'el-input': {
    template:
      '<input class="el-input" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['modelValue', 'disabled', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-select': {
    template:
      '<select class="el-select" :value="modelValue" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
    props: ['modelValue', 'disabled', 'clearable', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-option': {
    template: '<option :value="value">{{ label }}</option>',
    props: ['label', 'value'],
  },
  'el-radio-group': {
    template: '<div class="el-radio-group"><slot /></div>',
    props: ['modelValue', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-radio-button': {
    template:
      '<label class="el-radio-button" :data-value="value" @click="$parent.$emit(\'update:modelValue\', value); $parent.$emit(\'change\', value)"><slot /></label>',
    props: ['value'],
  },
  'el-tag': {
    template:
      '<span class="el-tag" :data-type="type" :data-effect="effect"><slot /></span>',
    props: ['type', 'size', 'effect', 'closable'],
    emits: ['close'],
  },
  'el-button': {
    template:
      '<button class="el-button" :class="{ disabled: disabled }" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'icon', 'plain', 'loading', 'link'],
    emits: ['click'],
  },
  'el-table': {
    template: '<div class="el-table"></div>',
    props: ['data', 'border', 'size', 'rowClassName', 'emptyText'],
  },
  'el-table-column': {
    template: '<div class="el-table-column"></div>',
    props: ['label', 'minWidth', 'align', 'resizable', 'width', 'fixed'],
  },
  'el-collapse': {
    template: '<div class="el-collapse"><slot /></div>',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-collapse-item': {
    template:
      '<div class="el-collapse-item" :data-name="name"><slot name="title" /><slot /></div>',
    props: ['name'],
  },
  'el-alert': {
    template: '<div class="el-alert"><slot /></div>',
    props: ['type', 'closable', 'showIcon'],
  },
  'el-checkbox': {
    template:
      '<input type="checkbox" class="el-checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue'],
  },
  'el-input-number': {
    template:
      '<input type="number" class="el-input-number" :value="modelValue" @input="$emit(\'update:modelValue\', Number($event.target.value))" />',
    props: ['modelValue', 'disabled', 'size', 'min', 'max', 'precision', 'controlsPosition'],
    emits: ['update:modelValue'],
  },
  'el-date-picker': {
    template: '<input class="el-date-picker" />',
    props: ['modelValue', 'type', 'format', 'valueFormat'],
  },
  'el-icon': { template: '<i class="el-icon"><slot /></i>' },
  'el-tooltip': {
    template: '<div class="el-tooltip"><slot /></div>',
    props: ['content', 'placement'],
  },
  PlusIcon: { template: '<span class="plus-icon" />' },
  UploadIcon: { template: '<span class="upload-icon" />' },
  InfoFilled: { template: '<span class="info-filled" />' },
  CircleCheckFilled: { template: '<span class="check-filled" />' },
  WarningFilled: { template: '<span class="warning-filled" />' },
  CircleCloseFilled: { template: '<span class="close-filled" />' },
}

// ─── Schema builder ─────────────────────────────────────────────────────────

function buildCD2DisclosureSchema() {
  return {
    component_type: 'c-note-table',
    applicable_standard: 'listed_standalone',
    fixed_cells: { A3: '宜宾大药房', A4: '2025-12-31', I3: 'D2-2' },
    fields: [
      { name: 'section_id', label: '附注章节号', type: 'text', cell: 'B6', readonly: true, default: '五-1-1 应收账款' },
      {
        name: 'monetary_unit',
        label: '金额单位',
        type: 'enum',
        cell: 'F6',
        default: '元',
        enum: ['元', '千元', '万元'],
      },
      { name: 'currency_code', label: '币种', type: 'enum', cell: 'H6', default: 'CNY', enum: ['CNY', 'USD'] },
    ],
    version_variants: {
      listed: {
        label: '上市公司版',
        extra_subtables: ['single_provision_listed_disclosure'],
      },
      soe: {
        label: '国企版',
        extra_subtables: ['parent_voting_rights_explanation'],
      },
    },
    sub_tables: [
      // 通用子表（共有，listed/soe 都可见）
      {
        id: 'by_category_period_end',
        title: '一、应收账款按种类披露（期末数）',
        type: 'static_rows',
        applicable_to_sub_class: ['listed', 'soe'],
        order: 1,
        columns: {
          A: { field: 'category_label', type: 'text', label: '类别', readonly: true },
          B: { field: 'book_balance', type: 'number', label: '账面余额', render: 'amount' },
          D: { field: 'bad_debt_provision', type: 'number', label: '坏账准备', render: 'amount' },
        },
        static_rows: [
          { id: 'cat_single', label: '一、单项计提', is_subtotal: true },
          { id: 'cat_portfolio', label: '二、组合计提', is_subtotal: true },
          { id: 'cat_total', label: '合计', is_grand_total: true },
        ],
      },
      // 单项计提（dynamic_rows）
      {
        id: 'single_provision',
        title: '二、单项计提坏账准备',
        type: 'dynamic_rows',
        applicable_to_sub_class: ['listed', 'soe'],
        order: 2,
        max_rows: 200,
        columns: {
          A: { field: 'seq', type: 'number', label: '序号' },
          B: { field: 'debtor_name', type: 'text', label: '欠款方名称', required: true },
          C: { field: 'book_balance', type: 'number', label: '期末余额', render: 'amount' },
          D: { field: 'provision_amount', type: 'number', label: '坏账准备', render: 'amount' },
        },
        footer_total: { enabled: true, label: '合计', sum_columns: ['C', 'D'] },
      },
      // 上市专属子表
      {
        id: 'single_provision_listed_disclosure',
        title: '七、信用风险敞口分析（上市公司专属）',
        type: 'static_rows',
        applicable_to_sub_class: ['listed'],
        order: 9,
        columns: {
          A: { field: 'ecl_stage', type: 'text', label: 'ECL 阶段', readonly: true },
          B: { field: 'gross_carrying_amount', type: 'number', label: '账面余额' },
        },
        static_rows: [{ id: 'stage_1', label: '阶段1' }],
      },
      // 国企专属子表
      {
        id: 'parent_voting_rights_explanation',
        title: '七、母公司表决权说明（国企专属）',
        type: 'dynamic_rows',
        applicable_to_sub_class: ['soe'],
        order: 10,
        max_rows: 50,
        columns: {
          A: { field: 'seq', type: 'number', label: '序号' },
          B: { field: 'related_party_name', type: 'text', label: '关联方名称', required: true },
        },
      },
    ],
    inheritance_rules: [
      // 单项计提子表合计 = 按种类期末「单项」行
      {
        id: 'single_to_category_end',
        source: { sub_table: 'single_provision', sum_field: 'book_balance' },
        target: { sub_table: 'by_category_period_end', row: 'cat_single', column: 'B' },
        formula: 'SUM',
        validation: 'equal',
        on_mismatch: 'error',
        description: '单项子表余额合计 = 按种类期末"单项"行',
      },
    ],
    hidden_subtables: { default: [] },
    cross_refs: [],
    linkage: {
      downstream: [
        {
          target: 'disclosure_notes',
          condition: 'on_save',
          action: 'sync_to_disclosure_notes',
          description: 'C → 附注模块',
        },
      ],
    },
  }
}

function buildHtmlData(overrides: any = {}) {
  return {
    sub_table_data: overrides.sub_table_data ?? {
      by_category_period_end: [
        { id: 'cat_single', book_balance: 100000, bad_debt_provision: 5000 },
        { id: 'cat_portfolio', book_balance: 200000, bad_debt_provision: 10000 },
        { id: 'cat_total', book_balance: 300000, bad_debt_provision: 15000 },
      ],
      single_provision: [
        { _row_id: 'r1', seq: 1, debtor_name: '客户A', book_balance: 60000, provision_amount: 3000 },
        { _row_id: 'r2', seq: 2, debtor_name: '客户B', book_balance: 40000, provision_amount: 2000 },
      ],
    },
    hidden_subtables: overrides.hidden_subtables ?? [],
    current_standard: overrides.current_standard ?? 'listed_standalone',
    context: overrides.context ?? {
      section_id: '五-1-1 应收账款',
      monetary_unit: '元',
      currency_code: 'CNY',
    },
  }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('GtCNoteTable — 默认 standard 渲染', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockConfirm.mockReturnValue(Promise.resolve('confirm'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('默认 listed_standalone 时 listed 专属子表可见 + soe 专属隐藏', () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.currentStandardSubClass).toBe('listed')
    const visibleIds = vm.visibleSubTables.map((st: any) => st.id)
    expect(visibleIds).toContain('single_provision_listed_disclosure')
    expect(visibleIds).not.toContain('parent_voting_rights_explanation')
    // 通用子表也都可见
    expect(visibleIds).toContain('by_category_period_end')
    expect(visibleIds).toContain('single_provision')
  })

  it('默认 soe_standalone 时 soe 专属子表可见 + listed 专属隐藏', () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData({ current_standard: 'soe_standalone' }) as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.currentStandardSubClass).toBe('soe')
    const visibleIds = vm.visibleSubTables.map((st: any) => st.id)
    expect(visibleIds).toContain('parent_voting_rights_explanation')
    expect(visibleIds).not.toContain('single_provision_listed_disclosure')
  })
})

describe('GtCNoteTable — standard 切换（确认 / 取消）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('切换到 soe 触发 ElMessageBox.confirm + 确认后切换成功', async () => {
    mockConfirm.mockReturnValue(Promise.resolve('confirm'))
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.currentStandardSubClass).toBe('listed')

    // Simulate user clicking soe radio → v-model first updates currentStandardSubClass
    vm.currentStandardSubClass = 'soe'
    await vm.onStandardSwitch('soe')
    await flushPromises()

    expect(mockConfirm).toHaveBeenCalled()
    expect(vm.currentStandardSubClass).toBe('soe')

    const emitted = wrapper.emitted('standard-switch')
    expect(emitted).toBeDefined()
    // The new standard string should preserve scope=standalone
    expect(emitted![0][0]).toBe('soe_standalone')
  })

  it('切换到 soe 取消 → 回退到 listed 不发出 standard-switch 事件', async () => {
    mockConfirm.mockReturnValue(Promise.reject(new Error('cancel')))
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.currentStandardSubClass).toBe('listed')

    // Simulate v-model already changed to soe (radio selection), then user cancels
    vm.currentStandardSubClass = 'soe'
    await vm.onStandardSwitch('soe')
    await flushPromises()

    expect(mockConfirm).toHaveBeenCalled()
    // Should revert to listed
    expect(vm.currentStandardSubClass).toBe('listed')
    expect(wrapper.emitted('standard-switch')).toBeUndefined()
  })

  it('切换 standard 后共有字段值保留（context.monetary_unit 等不丢失）', async () => {
    mockConfirm.mockReturnValue(Promise.resolve('confirm'))
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData({
          context: { section_id: '五-1-1', monetary_unit: '万元', currency_code: 'USD' },
        }) as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.contextData.monetary_unit).toBe('万元')
    expect(vm.contextData.currency_code).toBe('USD')

    vm.currentStandardSubClass = 'soe'
    await vm.onStandardSwitch('soe')
    await flushPromises()

    // Context (shared fields) preserved across standard switch
    expect(vm.contextData.monetary_unit).toBe('万元')
    expect(vm.contextData.currency_code).toBe('USD')
    expect(vm.contextData.section_id).toBe('五-1-1')
  })
})

describe('GtCNoteTable — inheritance_rules 实时校验', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('source 合计 = target → ruleStatuses 状态为 ok', () => {
    // single_provision sum book_balance = 60000 + 40000 = 100000
    // by_category_period_end.cat_single.book_balance = 100000 → equal
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const statuses = vm.ruleStatuses
    expect(statuses.length).toBeGreaterThan(0)
    const single = statuses.find((s: any) => s.ruleId === 'single_to_category_end')
    expect(single).toBeDefined()
    expect(single.status).toBe('ok')
    expect(single.diff).toBe(0)
  })

  it('source 合计 ≠ target → ruleStatuses 状态为 mismatch + diff 非零', () => {
    // single_provision sum = 60000 + 40000 = 100000
    // 修改 cat_single.book_balance = 90000 → diff = 10000
    const data = buildHtmlData()
    data.sub_table_data.by_category_period_end[0].book_balance = 90000
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: data as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const single = vm.ruleStatuses.find((s: any) => s.ruleId === 'single_to_category_end')
    expect(single).toBeDefined()
    expect(single.status).toBe('mismatch')
    expect(single.diff).toBe(10000)
    expect(single.label).toContain('差异')
  })

  it('子表合计变化（动态行修改）→ ruleStatuses 重新计算', async () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    let single = vm.ruleStatuses.find((s: any) => s.ruleId === 'single_to_category_end')
    expect(single.status).toBe('ok')

    // Modify dynamic row in single_provision
    vm.subTableData.single_provision[0].book_balance = 70000 // was 60000, now total 70000+40000=110000 != 100000
    await nextTick()

    single = vm.ruleStatuses.find((s: any) => s.ruleId === 'single_to_category_end')
    expect(single.status).toBe('mismatch')
    expect(Math.abs(single.diff)).toBeCloseTo(10000, 2)
  })
})

describe('GtCNoteTable — 子表"不适用"软标记', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockConfirm.mockReturnValue(Promise.resolve('confirm'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('onHideSubTable 加入 hiddenSubtables + emit subtable-toggle', async () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.hiddenSubtables.length).toBe(0)

    await vm.onHideSubTable('single_provision')
    await flushPromises()

    expect(mockConfirm).toHaveBeenCalled()
    expect(vm.hiddenSubtables).toContain('single_provision')
    const visibleIds = vm.visibleSubTables.map((st: any) => st.id)
    expect(visibleIds).not.toContain('single_provision')

    const emitted = wrapper.emitted('subtable-toggle')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toBe('single_provision')
  })

  it('onRestoreSubTable 从 hiddenSubtables 移除 + emit subtable-toggle', async () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData({ hidden_subtables: ['single_provision'] }) as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.hiddenSubtables).toContain('single_provision')

    vm.onRestoreSubTable('single_provision')
    await nextTick()

    expect(vm.hiddenSubtables).not.toContain('single_provision')
    const emitted = wrapper.emitted('subtable-toggle')
    expect(emitted).toBeDefined()
  })
})

describe('GtCNoteTable — 同步到附注模块', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiPost.mockReturnValue(Promise.resolve({ rows_synced: 5 }))
  })

  it('onSyncToDisclosureNotes emit sync-to-disclosure-notes 携带 section_id payload', async () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    await vm.onSyncToDisclosureNotes()
    await flushPromises()

    const emitted = wrapper.emitted('sync-to-disclosure-notes')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.wp_id).toBe('wp-001')
    expect(payload.sheet_name).toBe('应收账款附注披露信息')
    expect(payload.section_id).toBe('五-1-1 应收账款')
    expect(payload.sub_table_data).toBeDefined()
    expect(payload.current_standard).toBe('listed_standalone')
  })

  it('onSyncToDisclosureNotes 缺少 section_id 时弹 warning 不发 emit', async () => {
    // Build a schema variant where section_id field has no default so empty context
    // really resolves to empty string (the default in the original schema would
    // otherwise fall through via the sectionId computed fallback).
    const schemaNoDefault = buildCD2DisclosureSchema()
    const sectionField = (schemaNoDefault.fields as any[]).find(
      (f: any) => f.name === 'section_id',
    )
    if (sectionField) delete sectionField.default
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: schemaNoDefault as any,
        htmlData: buildHtmlData({
          context: { section_id: '', monetary_unit: '元', currency_code: 'CNY' },
        }) as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.sectionId).toBe('')
    await vm.onSyncToDisclosureNotes()
    await flushPromises()

    expect(mockMessageWarning).toHaveBeenCalled()
    expect(wrapper.emitted('sync-to-disclosure-notes')).toBeUndefined()
  })

  it('onSyncToDisclosureNotes 调用后端 API + 成功提示', async () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    await vm.onSyncToDisclosureNotes()
    await flushPromises()

    expect(mockApiPost).toHaveBeenCalledWith(
      '/api/projects/proj-123/disclosure-notes/sync-from-workpaper',
      expect.objectContaining({
        wp_id: 'wp-001',
        section_id: '五-1-1 应收账款',
      }),
    )
    expect(mockMessageSuccess).toHaveBeenCalled()
  })
})

describe('GtCNoteTable — debounce save / 数据持久化', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockConfirm.mockReturnValue(Promise.resolve('confirm'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('单元格变更触发 debounce save', async () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.subTableData.single_provision[0].book_balance = 65000
    vm.onCellChange(
      vm.schema.sub_tables.find((s: any) => s.id === 'single_provision'),
      vm.subTableData.single_provision[0],
      { field: 'book_balance', _cellKey: 'C' } as any,
    )
    await nextTick()

    expect(wrapper.emitted('save')).toBeUndefined()
    vi.advanceTimersByTime(1600)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.sub_table_data.single_provision[0].book_balance).toBe(65000)
    expect(payload.current_standard).toBe('listed_standalone')
  })

  it('readonly 模式不触发 save', async () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
        readonly: true,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.subTableData.single_provision[0].book_balance = 65000
    vm.onCellChange(
      vm.schema.sub_tables.find((s: any) => s.id === 'single_provision'),
      vm.subTableData.single_provision[0],
      { field: 'book_balance', _cellKey: 'C' } as any,
    )
    vi.advanceTimersByTime(1600)
    await nextTick()

    expect(wrapper.emitted('save')).toBeUndefined()
  })

  it('动态行新增/删除 → debounce save', async () => {
    const wrapper = mount(GtCNoteTable, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款附注披露信息',
        schema: buildCD2DisclosureSchema() as any,
        htmlData: buildHtmlData() as any,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const st = vm.schema.sub_tables.find((s: any) => s.id === 'single_provision')

    vm.onAddDynamicRow(st)
    await nextTick()
    expect(vm.subTableData.single_provision.length).toBe(3)

    vi.advanceTimersByTime(1600)
    await nextTick()
    expect(wrapper.emitted('save')).toBeDefined()
  })
})
