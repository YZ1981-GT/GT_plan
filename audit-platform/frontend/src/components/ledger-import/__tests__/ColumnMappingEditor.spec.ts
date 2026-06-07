/**
 * ColumnMappingEditor 与 DetectionPreview 组件单元测试
 *
 * 6.4: 关键列未补齐时"确认映射并导入"按钮 disabled
 * 6.5: unknown sheet 人工改为 balance 后，从 DetectionPreview 确认可进入列映射
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, shallowMount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ColumnMappingEditor from '../ColumnMappingEditor.vue'
import DetectionPreview from '../DetectionPreview.vue'
import type { SheetDetection, ColumnMatch, LedgerDetectionResult } from '../LedgerImportDialog.vue'

// --- Mocks ---

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-001' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

// --- Global Element Plus stubs ---
const globalStubs = {
  'el-tabs': { template: '<div class="el-tabs"><slot /></div>', props: ['modelValue'] },
  'el-tab-pane': { template: '<div class="el-tab-pane"><slot /></div>', props: ['label', 'name'] },
  'el-collapse': { template: '<div class="el-collapse"><slot /></div>', props: ['modelValue'] },
  'el-collapse-item': { template: '<div class="el-collapse-item"><slot /><slot name="title" /></div>', props: ['name'] },
  'el-select': {
    template: '<select class="el-select" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
    props: ['modelValue', 'placeholder', 'filterable', 'clearable', 'size', 'loading', 'disabled'],
    emits: ['update:modelValue', 'change'],
  },
  'el-option': { template: '<option :value="value" :disabled="disabled">{{ label }}</option>', props: ['label', 'value', 'disabled'] },
  'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size', 'effect', 'style'] },
  'el-button': {
    template: '<button class="el-button" :disabled="disabled" :aria-label="ariaLabel" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'link', 'loading', 'ariaLabel'],
    emits: ['click'],
  },
  'el-alert': { template: '<div class="el-alert"><slot /><slot name="title" /><slot name="default" /></div>', props: ['title', 'type', 'closable', 'showIcon', 'style'] },
  'el-icon': { template: '<i class="el-icon"><slot /></i>' },
  'el-tooltip': { template: '<span class="el-tooltip"><slot /></span>', props: ['content', 'placement'] },
  'el-dialog': { template: '<div class="el-dialog" v-if="modelValue"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title', 'width', 'appendToBody'] },
  'el-form': { template: '<form class="el-form"><slot /></form>', props: ['labelWidth'] },
  'el-form-item': { template: '<div class="el-form-item"><slot /></div>', props: ['label'] },
  'el-table': { template: '<div class="el-table"><slot /></div>', props: ['data', 'border', 'stripe', 'style', 'maxHeight', 'size', 'rowClassName'] },
  'el-table-column': { template: '<div class="el-table-column"><slot /></div>', props: ['prop', 'label', 'minWidth', 'width', 'align', 'showOverflowTooltip'] },
  'el-descriptions': { template: '<div class="el-descriptions"><slot /></div>', props: ['column', 'border', 'size'] },
  'el-descriptions-item': { template: '<div class="el-descriptions-item"><slot /></div>', props: ['label'] },
  Right: { template: '<span class="icon-right" />' },
}

// --- Helpers ---

function makeColumnMatch(overrides: Partial<ColumnMatch> = {}): ColumnMatch {
  return {
    column_index: 0,
    column_header: '科目编码',
    standard_field: 'account_code',
    column_tier: 'key',
    confidence: 95,
    source: 'auto',
    sample_values: ['1001', '1002'],
    ...overrides,
  }
}

function makeSheet(overrides: Partial<SheetDetection> = {}): SheetDetection {
  return {
    file_name: '余额表.xlsx',
    sheet_name: 'Sheet1',
    row_count_estimate: 100,
    header_row_index: 0,
    data_start_row: 1,
    table_type: 'balance',
    table_type_confidence: 90,
    confidence_level: 'high',
    adapter_id: null,
    column_mappings: [
      makeColumnMatch({ column_index: 0, column_header: '科目编码', standard_field: 'account_code', column_tier: 'key' }),
      makeColumnMatch({ column_index: 1, column_header: '期初余额', standard_field: 'opening_balance', column_tier: 'key' }),
      makeColumnMatch({ column_index: 2, column_header: '借方', standard_field: 'debit_amount', column_tier: 'recommended' }),
    ],
    has_aux_dimension: false,
    aux_dimension_columns: [],
    preview_rows: [['科目编码', '期初余额', '借方'], ['1001', '10000', '500']],
    detection_evidence: {},
    warnings: [],
    ...overrides,
  }
}

// ─── 6.4: 关键列未补齐时不能确认 ─────────────────────────────────

describe('6.4 ColumnMappingEditor: 关键列未补齐时按钮 disabled', () => {
  it('当所有关键列已映射时，确认按钮可用', async () => {
    const sheet = makeSheet()
    const wrapper = mount(ColumnMappingEditor, {
      props: {
        sheets: [sheet],
        detectionResult: null,
      },
      global: { stubs: globalStubs },
    })
    await nextTick()

    const confirmBtn = wrapper.find('button[aria-label="确认映射并导入"]')
    expect(confirmBtn.exists()).toBe(true)
    expect(confirmBtn.attributes('disabled')).toBeUndefined()
  })

  it('当关键列 standard_field 为 null 时，确认按钮 disabled', async () => {
    const sheet = makeSheet({
      column_mappings: [
        makeColumnMatch({ column_index: 0, column_header: '科目编码', standard_field: 'account_code', column_tier: 'key' }),
        makeColumnMatch({ column_index: 1, column_header: '期初余额', standard_field: null, column_tier: 'key' }),
        makeColumnMatch({ column_index: 2, column_header: '借方', standard_field: 'debit_amount', column_tier: 'recommended' }),
      ],
    })

    const wrapper = mount(ColumnMappingEditor, {
      props: {
        sheets: [sheet],
        detectionResult: null,
      },
      global: { stubs: globalStubs },
    })
    await nextTick()

    const confirmBtn = wrapper.find('button[aria-label="确认映射并导入"]')
    expect(confirmBtn.exists()).toBe(true)
    expect(confirmBtn.attributes('disabled')).toBe('')
  })

  it('多个关键列全部未映射时 disabled', async () => {
    const sheet = makeSheet({
      column_mappings: [
        makeColumnMatch({ column_index: 0, column_header: '科目编码', standard_field: null, column_tier: 'key' }),
        makeColumnMatch({ column_index: 1, column_header: '期初余额', standard_field: null, column_tier: 'key' }),
        makeColumnMatch({ column_index: 2, column_header: '摘要', standard_field: 'summary', column_tier: 'extra' }),
      ],
    })

    const wrapper = mount(ColumnMappingEditor, {
      props: {
        sheets: [sheet],
        detectionResult: null,
      },
      global: { stubs: globalStubs },
    })
    await nextTick()

    const confirmBtn = wrapper.find('button[aria-label="确认映射并导入"]')
    expect(confirmBtn.attributes('disabled')).toBe('')
  })

  it('关键列缺失警告文本出现', async () => {
    const sheet = makeSheet({
      column_mappings: [
        makeColumnMatch({ column_index: 0, column_header: '科目编码', standard_field: null, column_tier: 'key' }),
        makeColumnMatch({ column_index: 1, column_header: '期初余额', standard_field: 'opening_balance', column_tier: 'key' }),
      ],
    })

    const wrapper = mount(ColumnMappingEditor, {
      props: {
        sheets: [sheet],
        detectionResult: null,
      },
      global: { stubs: globalStubs },
    })
    await nextTick()

    // el-alert shows missing key column names
    const html = wrapper.html()
    expect(html).toContain('科目编码')
    expect(html).toContain('缺失关键列')
  })
})

// ─── 6.5: unknown 人工改为 balance 后进入列映射 ─────────────────────

describe('6.5 DetectionPreview: unknown 人工改为 balance 后可进入列映射', () => {
  // el-table-column uses scoped slot #default="{ row }" which needs row data
  // We stub el-table-column to NOT render its default slot to avoid the error
  const previewStubs = {
    ...globalStubs,
    'el-table-column': { template: '<div class="el-table-column" />', props: ['prop', 'label', 'minWidth', 'width', 'align', 'showOverflowTooltip'] },
  }

  function makeDetectionResult(sheets: SheetDetection[]): LedgerDetectionResult {
    return {
      upload_token: 'token-001',
      detected_year: 2024,
      year_confidence: 90,
      files: [
        {
          file_name: '余额表.xlsx',
          file_size_bytes: 1024,
          file_type: 'xlsx',
          encoding: 'utf-8',
          sheets,
          errors: [],
        },
      ],
    } as unknown as LedgerDetectionResult
  }

  it('unknown sheet 改为 balance 后，确认时该 sheet 进入确认列表', async () => {
    const unknownSheet = makeSheet({
      table_type: 'unknown',
      table_type_confidence: 20,
      confidence_level: 'low',
    })

    const detectionResult = makeDetectionResult([unknownSheet])

    const wrapper = shallowMount(DetectionPreview, {
      props: { detectionResult },
      global: { stubs: previewStubs },
    })
    await nextTick()

    // Access internal sheetRows computed (reactive data derived from props)
    const vm = wrapper.vm as any
    const rows = vm.sheetRows
    expect(rows.length).toBe(1)
    expect(rows[0].table_type).toBe('unknown')

    // Simulate user changing table_type (el-select v-model binds to row.table_type)
    rows[0].table_type = 'balance'
    await nextTick()

    // Trigger confirm - should emit the sheet (no longer unknown)
    vm.doConfirm(false)
    await nextTick()

    const emitted = wrapper.emitted('confirm')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toHaveLength(1)
    expect((emitted![0][0] as SheetDetection[])[0].table_type).toBe('balance')
  })

  it('unknown sheet 未改类型时，确认不包含该 sheet', async () => {
    const unknownSheet = makeSheet({
      table_type: 'unknown',
      table_type_confidence: 20,
      confidence_level: 'low',
    })

    const detectionResult = makeDetectionResult([unknownSheet])

    const wrapper = shallowMount(DetectionPreview, {
      props: { detectionResult },
      global: { stubs: previewStubs },
    })
    await nextTick()

    const vm = wrapper.vm as any
    vm.doConfirm(false)
    await nextTick()

    const emitted = wrapper.emitted('confirm')
    expect(emitted).toBeTruthy()
    // unknown sheets are filtered out
    expect(emitted![0][0]).toHaveLength(0)
  })

  it('多 sheet 场景：1 unknown 改 balance + 1 已识别 ledger，确认包含两者', async () => {
    const unknownSheet = makeSheet({
      table_type: 'unknown',
      sheet_name: 'Sheet1',
      table_type_confidence: 15,
    })
    const ledgerSheet = makeSheet({
      table_type: 'ledger',
      sheet_name: 'Sheet2',
      table_type_confidence: 92,
    })

    const detectionResult = makeDetectionResult([unknownSheet, ledgerSheet])

    const wrapper = shallowMount(DetectionPreview, {
      props: { detectionResult },
      global: { stubs: previewStubs },
    })
    await nextTick()

    const vm = wrapper.vm as any
    // Change unknown to balance
    vm.sheetRows[0].table_type = 'balance'
    await nextTick()

    vm.doConfirm(false)
    await nextTick()

    const emitted = wrapper.emitted('confirm')
    expect(emitted).toBeTruthy()
    const sheets = emitted![0][0] as SheetDetection[]
    expect(sheets).toHaveLength(2)
    expect(sheets[0].table_type).toBe('balance')
    expect(sheets[1].table_type).toBe('ledger')
  })
})
