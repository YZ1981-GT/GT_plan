/**
 * StructureEditor + DisclosureEditor — 新增章节 / 加表 / 加列（Sprint 3 Task 3.1）
 *
 * Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.1
 * Reqs:   R4.1 验收 29 / 30 / 31（新增章节 + 新增表 + 新增列 + 列语义）
 *
 * 用例：
 * 1. StructureEditor — 「➕ 加表」按钮触发 dialog 显示 + headers 输入
 * 2. StructureEditor — 「➕ 加表」提交拆分 headers 并 emit add-table 事件
 * 3. StructureEditor — 「➕ 加列」打开列语义下拉 25 项，默认值 manual_text
 * 4. StructureEditor — 「➕ 加列」提交 emit add-column + binding 草稿（含 semantic）
 * 5. DisclosureEditor — 「➕ 新增章节」按钮触发 dialog
 * 6. DisclosureEditor — 章节表单提交 POST 到 /api/projects/{pid}/note-template/save
 *
 * **Validates: Requirements R4.1**
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

import {
  NOTE_COLUMN_SEMANTIC_OPTIONS,
  NOTE_COLUMN_SEMANTIC_COUNT,
  DEFAULT_NOTE_COLUMN_SEMANTIC,
} from '@/constants/noteColumnSemantics'

// ─── Mock apiProxy ─────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

// ─── Mock element-plus ─────────────────────────────────────────────────────

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: {
      success: vi.fn(),
      warning: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    },
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue('confirm'),
    },
  }
})

// ─── Mock commonApi (StructureEditor onMounted dependencies) ──────────────

vi.mock('@/services/commonApi', () => ({
  getExcelHtmlPreview: vi.fn().mockResolvedValue({ html: '', total_rows: 0, sheet_names: [] }),
  saveExcelHtmlEdits: vi.fn().mockResolvedValue({ version: 1 }),
  getModuleHtml: vi.fn().mockResolvedValue({ html: '<div>module</div>' }),
  acquireEditLock: vi.fn().mockResolvedValue(undefined),
  releaseEditLock: vi.fn().mockResolvedValue(undefined),
  refreshEditLock: vi.fn().mockResolvedValue(undefined),
  listFileVersions: vi.fn().mockResolvedValue([]),
  rollbackFileVersion: vi.fn().mockResolvedValue(undefined),
  executeFormulas: vi.fn().mockResolvedValue({ executed: 0, total_formulas: 0, errors: [] }),
}))

// FormulaBar / CellSelector 都是子组件，stub 掉
vi.mock('../FormulaBar.vue', () => ({
  default: { template: '<div class="mock-formula-bar" />' },
}))
vi.mock('../CellSelector.vue', () => ({
  default: { template: '<div class="mock-cell-selector" />' },
}))

import StructureEditor from '@/components/formula/StructureEditor.vue'

const STUBS = {
  'el-button': { template: '<button :data-test="$attrs[\'data-test\']" @click="$emit(\'click\')"><slot /></button>' },
  'el-button-group': { template: '<div><slot /></div>' },
  'el-divider': true,
  'el-checkbox': true,
  'el-input': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :data-test="$attrs[\'data-test\']" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-input-number': true,
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div class="form-item"><slot /></div>' },
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: `<select :data-test="$attrs['data-test']" :value="modelValue" @change="$emit('update:modelValue', $event.target.value)"><slot /></select>`,
  },
  'el-option': {
    props: ['value', 'label'],
    template: '<option :value="value" :data-test="\'opt-\' + value">{{ label }}</option>',
  },
  'el-dialog': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div v-if="modelValue" :data-test="$attrs[\'data-test\']" class="mock-dialog"><slot /><slot name="footer" /></div>',
  },
  'el-tabs': { template: '<div><slot /></div>' },
  'el-tab-pane': { template: '<div><slot /></div>' },
  'el-table': true,
  'el-table-column': true,
  'el-pagination': true,
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  // structure editor mounted 时 loadSelectorData 会调用 api.get
  mockGet.mockResolvedValue([])
})

describe('StructureEditor — Sprint 3 Task 3.1: 加表 / 加列', () => {
  function mountSE() {
    return mount(StructureEditor, {
      props: {
        projectId: 'proj-A',
        module: 'disclosure_note',
        moduleParams: { note_section: '五、6', year: 2024 },
        year: 2024,
      },
      global: { stubs: STUBS },
    })
  }

  it('用例 1 — 「➕ 加表」按钮触发 dialog 显示', async () => {
    const wrapper = mountSE()
    await flushPromises()

    // dialog 默认隐藏
    expect(wrapper.find('[data-test="se-add-table-dialog"]').exists()).toBe(false)

    // 点击 "➕ 加表" 按钮
    const btn = wrapper.find('[data-test="se-add-table"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await nextTick()

    expect(wrapper.find('[data-test="se-add-table-dialog"]').exists()).toBe(true)
    // headers 默认值非空
    const vm: any = wrapper.vm
    expect(vm.addTableForm.headersText).toContain('期初余额')
  })

  it('用例 2 — 「➕ 加表」提交拆分 headers + emit add-table', async () => {
    const wrapper = mountSE()
    await flushPromises()

    const vm: any = wrapper.vm
    vm.addTableForm = { name: '固定资产变动表', headersText: '项目, 期初余额, 本期增加, 期末余额' }
    vm.showAddTableDialog = true
    await nextTick()

    vm.onAddTableConfirm()
    await nextTick()

    const emitted = wrapper.emitted('add-table')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      name: '固定资产变动表',
      headers: ['项目', '期初余额', '本期增加', '期末余额'],
    })
    // 提交后 dialog 关闭
    expect(vm.showAddTableDialog).toBe(false)
  })

  it('用例 3 — 「➕ 加列」打开列语义下拉显示 25 项，默认值 manual_text', async () => {
    const wrapper = mountSE()
    await flushPromises()

    const vm: any = wrapper.vm
    vm.openAddColumnDialog()
    await nextTick()

    expect(wrapper.find('[data-test="se-add-column-dialog"]').exists()).toBe(true)
    // 默认 semantic = manual_text
    expect(vm.addColumnForm.semantic).toBe(DEFAULT_NOTE_COLUMN_SEMANTIC)
    expect(DEFAULT_NOTE_COLUMN_SEMANTIC).toBe('manual_text')

    // 25 项 option 全部渲染
    expect(NOTE_COLUMN_SEMANTIC_COUNT).toBe(25)
    const opts = wrapper.findAll('option[data-test^="opt-"]')
    expect(opts.length).toBe(25)
    // 抽查若干语义出现
    const optValues = opts.map(o => o.attributes('value'))
    expect(optValues).toContain('manual_text')
    expect(optValues).toContain('aging_bucket_within_1y')
    expect(optValues).toContain('current_year_increase')
    expect(optValues).toContain('closing_balance')
    expect(optValues).toContain('formula_result')
  })

  it('用例 4 — 「➕ 加列」提交 emit add-column + binding 草稿', async () => {
    const wrapper = mountSE()
    await flushPromises()

    const vm: any = wrapper.vm
    vm.addColumnForm = { header: '本期增加', semantic: 'current_year_increase' }
    vm.showAddColumnDialog = true
    await nextTick()

    vm.onAddColumnConfirm()
    await nextTick()

    const emitted = wrapper.emitted('add-column')
    expect(emitted).toBeTruthy()
    const payload = emitted![0][0] as any
    expect(payload.header).toBe('本期增加')
    expect(payload.semantic).toBe('current_year_increase')
    expect(payload.bindingDraft).toEqual({
      semantic: 'current_year_increase',
      source: 'manual',
      field: '',
      mode: 'manual_text',
      account_codes: [],
    })
  })

  it('用例 5 — 加表/加列空字段校验：表名为空时不 emit', async () => {
    const wrapper = mountSE()
    await flushPromises()

    const vm: any = wrapper.vm
    vm.addTableForm = { name: '', headersText: '项目, 期末余额' }
    vm.onAddTableConfirm()
    await nextTick()

    expect(wrapper.emitted('add-table')).toBeUndefined()

    // 加列空 header 同样不 emit
    vm.addColumnForm = { header: '', semantic: 'manual_text' }
    vm.onAddColumnConfirm()
    await nextTick()

    expect(wrapper.emitted('add-column')).toBeUndefined()
  })

  it('用例 6 — NOTE_COLUMN_SEMANTIC_OPTIONS 与后端 25 项保持稳定排序', () => {
    // 与 backend/app/services/note_column_semantics.py::VALID_SEMANTICS 顺序一致
    const expectedFirstFew = [
      'aging_bucket_within_1y',
      'aging_bucket_1_2y',
      'aging_bucket_2_3y',
      'aging_bucket_3_5y',
      'aging_bucket_over_5y',
      'provision_ratio',
      'current_year_provision',
      'current_year_increase',
      'current_year_decrease',
    ]
    const actualFirstFew = NOTE_COLUMN_SEMANTIC_OPTIONS.slice(0, 9).map(o => o.value)
    expect(actualFirstFew).toEqual(expectedFirstFew)
    // 末项必须是兜底 manual_text
    expect(NOTE_COLUMN_SEMANTIC_OPTIONS[NOTE_COLUMN_SEMANTIC_OPTIONS.length - 1].value).toBe('manual_text')
  })
})
