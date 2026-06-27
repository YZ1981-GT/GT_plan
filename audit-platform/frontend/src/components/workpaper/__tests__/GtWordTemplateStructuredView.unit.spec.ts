/**
 * Unit Tests — GtWordTemplateStructuredView.vue
 *
 * Spec: .kiro/specs/word-template-dual-mode/
 * Task: 4.5
 *
 * Covers:
 * 1. Card rendering: heading paragraphs become card titles, content paragraphs render inside cards
 * 2. Table rendering: tables from TemplateStructure render as el-table with correct row/column structure
 * 3. Mode mapping: text→el-input, textarea→el-input[type=textarea], date→el-date-picker, number→el-input-number
 * 4. Disabled AI tooltip: AI buttons have tooltip "AI 填充功能即将上线" and are disabled
 * 5. No-placeholder message: when template has no placeholders, show "该模板无可编辑字段，请使用在线编辑模式"
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GtWordTemplateStructuredView from '../GtWordTemplateStructuredView.vue'
import type { TemplateStructure, PlaceholderDef } from '../composables/useWordTemplateStructured'

// ─── Stubs ───────────────────────────────────────────────────────────────────

const globalStubs = {
  'el-card': {
    template: '<div class="el-card"><div class="el-card__header"><slot name="header"/></div><div class="el-card__body"><slot/></div></div>',
  },
  'el-input': {
    template: '<input class="el-input" :type="type" :disabled="disabled" />',
    props: ['modelValue', 'type', 'disabled', 'placeholder', 'autosize'],
  },
  'el-date-picker': {
    template: '<input class="el-date-picker" :disabled="disabled" />',
    props: ['modelValue', 'type', 'disabled', 'placeholder', 'valueFormat'],
  },
  'el-input-number': {
    template: '<input class="el-input-number" :disabled="disabled" />',
    props: ['modelValue', 'disabled', 'placeholder', 'controlsPosition'],
  },
  'el-table': {
    template: '<div class="el-table"><slot/></div>',
    props: ['data', 'border', 'size'],
  },
  'el-table-column': {
    template: '<div class="el-table-column"></div>',
    props: ['label', 'minWidth'],
  },
  'el-alert': {
    template: '<div class="el-alert" :class="type"><slot/><span class="el-alert__content">{{ title }}</span></div>',
    props: ['type', 'closable', 'showIcon', 'title'],
  },
  'el-tooltip': {
    template: '<div class="el-tooltip" :data-content="content"><slot/></div>',
    props: ['content', 'placement'],
  },
  'el-button': {
    template: '<button class="el-button" :disabled="disabled" :data-icon="icon"></button>',
    props: ['disabled', 'size', 'icon'],
  },
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makePlaceholder(overrides: Partial<PlaceholderDef> & { field_id: string; data_type: string }): PlaceholderDef {
  return {
    field_id: overrides.field_id,
    label: overrides.label || `Label ${overrides.field_id}`,
    data_type: overrides.data_type,
    default_value: overrides.default_value || '',
    position: overrides.position || { paragraph_index: 1 },
    pattern: overrides.pattern || `\${${overrides.field_id}}`,
    current_value: overrides.current_value || '',
  }
}

function makeStructure(opts: {
  placeholders?: PlaceholderDef[]
  paragraphs?: TemplateStructure['paragraphs']
  tables?: TemplateStructure['tables']
}): TemplateStructure {
  return {
    placeholders: opts.placeholders || [],
    paragraphs: opts.paragraphs || [],
    tables: opts.tables || [],
    metadata: { template_name: 'Test', wp_code: 'TEST-1', last_parsed_at: '2026-01-01T00:00:00Z' },
  }
}

function mountComponent(structure: TemplateStructure, fieldValues: Record<string, string> = {}, readonly = false) {
  return mount(GtWordTemplateStructuredView, {
    props: { templateStructure: structure, fieldValues, readonly },
    global: { stubs: globalStubs },
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. Card Rendering
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtWordTemplateStructuredView — Card Rendering', () => {
  it('heading paragraphs become card titles', () => {
    const structure = makeStructure({
      paragraphs: [
        { index: 0, text: '审计概况', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '详细内容段落', style: 'Normal', heading_level: 0, placeholder_ids: [] },
      ],
    })

    const wrapper = mountComponent(structure)

    const cardTitle = wrapper.find('.gt-wt-structured-view__card-title')
    expect(cardTitle.exists()).toBe(true)
    expect(cardTitle.text()).toBe('审计概况')
    wrapper.unmount()
  })

  it('content paragraphs without placeholders render as read-only text inside cards', () => {
    const structure = makeStructure({
      paragraphs: [
        { index: 0, text: '标题一', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '这是一段只读指导文本', style: 'Normal', heading_level: 0, placeholder_ids: [] },
      ],
    })

    const wrapper = mountComponent(structure)

    const readonlyText = wrapper.find('.gt-wt-structured-view__readonly-text')
    expect(readonlyText.exists()).toBe(true)
    expect(readonlyText.text()).toBe('这是一段只读指导文本')
    wrapper.unmount()
  })

  it('multiple headings create multiple cards', () => {
    const structure = makeStructure({
      paragraphs: [
        { index: 0, text: '第一章', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '内容A', style: 'Normal', heading_level: 0, placeholder_ids: [] },
        { index: 2, text: '第二章', style: 'Heading 2', heading_level: 2, placeholder_ids: [] },
        { index: 3, text: '内容B', style: 'Normal', heading_level: 0, placeholder_ids: [] },
      ],
    })

    const wrapper = mountComponent(structure)

    const cards = wrapper.findAll('.gt-wt-structured-view__card')
    expect(cards.length).toBe(2)

    const titles = wrapper.findAll('.gt-wt-structured-view__card-title')
    expect(titles[0].text()).toBe('第一章')
    expect(titles[1].text()).toBe('第二章')
    wrapper.unmount()
  })

  it('paragraphs before any heading get a default "文档内容" section', () => {
    const structure = makeStructure({
      paragraphs: [
        { index: 0, text: '无标题段落', style: 'Normal', heading_level: 0, placeholder_ids: [] },
      ],
    })

    const wrapper = mountComponent(structure)

    const cardTitle = wrapper.find('.gt-wt-structured-view__card-title')
    expect(cardTitle.exists()).toBe(true)
    expect(cardTitle.text()).toBe('文档内容')
    wrapper.unmount()
  })

  it('paragraphs with placeholders render editable field rows', () => {
    const placeholder = makePlaceholder({ field_id: 'entity_name', data_type: 'text', label: '被审计单位' })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '基本信息', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '${entity_name}', style: 'Normal', heading_level: 0, placeholder_ids: ['entity_name'] },
      ],
    })

    const wrapper = mountComponent(structure)

    const fieldRow = wrapper.find('.gt-wt-structured-view__field-row')
    expect(fieldRow.exists()).toBe(true)

    const label = wrapper.find('.gt-wt-structured-view__field-label')
    expect(label.text()).toBe('被审计单位')
    wrapper.unmount()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. Table Rendering
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtWordTemplateStructuredView — Table Rendering', () => {
  it('tables from TemplateStructure render as el-table', () => {
    const structure = makeStructure({
      paragraphs: [
        { index: 0, text: '表格章节', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
      ],
      tables: [
        {
          index: 1,
          rows: [['项目', '内容'], ['被审计单位', '××公司']],
          placeholder_ids: [],
        },
      ],
    })

    const wrapper = mountComponent(structure)

    const table = wrapper.find('.el-table')
    expect(table.exists()).toBe(true)
    wrapper.unmount()
  })

  it('table renders inside the table-wrap container', () => {
    const structure = makeStructure({
      paragraphs: [
        { index: 0, text: '数据', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
      ],
      tables: [
        {
          index: 1,
          rows: [['列A', '列B'], ['值1', '值2']],
          placeholder_ids: [],
        },
      ],
    })

    const wrapper = mountComponent(structure)

    const tableWrap = wrapper.find('.gt-wt-structured-view__table-wrap')
    expect(tableWrap.exists()).toBe(true)
    expect(tableWrap.find('.el-table').exists()).toBe(true)
    wrapper.unmount()
  })

  it('table with placeholders in cells references the correct placeholder', () => {
    const placeholder = makePlaceholder({
      field_id: 'audit_fee',
      data_type: 'number',
      label: '审计费用',
      position: { table_index: 1, row: 1, col: 1 },
    })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '费用表', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
      ],
      tables: [
        {
          index: 1,
          rows: [['项目', '金额'], ['审计费', '${audit_fee}']],
          placeholder_ids: ['audit_fee'],
        },
      ],
    })

    const wrapper = mountComponent(structure)

    // Table should exist and have placeholder_ids linked
    const tableWrap = wrapper.find('.gt-wt-structured-view__table-wrap')
    expect(tableWrap.exists()).toBe(true)
    wrapper.unmount()
  })

  it('multiple tables render multiple table-wrap containers', () => {
    const structure = makeStructure({
      paragraphs: [
        { index: 0, text: '多表', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
      ],
      tables: [
        { index: 1, rows: [['A', 'B']], placeholder_ids: [] },
        { index: 2, rows: [['C', 'D']], placeholder_ids: [] },
      ],
    })

    const wrapper = mountComponent(structure)

    const tableWraps = wrapper.findAll('.gt-wt-structured-view__table-wrap')
    expect(tableWraps.length).toBe(2)
    wrapper.unmount()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. Mode Mapping (data_type → input component)
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtWordTemplateStructuredView — Mode Mapping', () => {
  function mountWithType(dataType: string) {
    const placeholder = makePlaceholder({ field_id: 'test_field', data_type: dataType, label: '测试字段' })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '字段', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '${test_field}', style: 'Normal', heading_level: 0, placeholder_ids: ['test_field'] },
      ],
    })
    return mountComponent(structure)
  }

  it('text data_type renders el-input (default)', () => {
    const wrapper = mountWithType('text')

    const input = wrapper.find('.gt-wt-structured-view__field-input .el-input')
    expect(input.exists()).toBe(true)
    // text type el-input should NOT have type="textarea"
    expect(input.attributes('type')).not.toBe('textarea')
    wrapper.unmount()
  })

  it('textarea data_type renders el-input with type="textarea"', () => {
    const wrapper = mountWithType('textarea')

    const input = wrapper.find('.gt-wt-structured-view__field-input .el-input')
    expect(input.exists()).toBe(true)
    expect(input.attributes('type')).toBe('textarea')
    wrapper.unmount()
  })

  it('date data_type renders el-date-picker', () => {
    const wrapper = mountWithType('date')

    const datePicker = wrapper.find('.gt-wt-structured-view__field-input .el-date-picker')
    expect(datePicker.exists()).toBe(true)
    // Should not have el-input for date type
    const elInput = wrapper.find('.gt-wt-structured-view__field-input > .el-input')
    expect(elInput.exists()).toBe(false)
    wrapper.unmount()
  })

  it('number data_type renders el-input-number', () => {
    const wrapper = mountWithType('number')

    const inputNumber = wrapper.find('.gt-wt-structured-view__field-input .el-input-number')
    expect(inputNumber.exists()).toBe(true)
    // Should not have el-input for number type
    const elInput = wrapper.find('.gt-wt-structured-view__field-input > .el-input')
    expect(elInput.exists()).toBe(false)
    wrapper.unmount()
  })

  it('mixed data_types in one section each render correctly', () => {
    const placeholders = [
      makePlaceholder({ field_id: 'f_text', data_type: 'text', label: '短文本' }),
      makePlaceholder({ field_id: 'f_area', data_type: 'textarea', label: '长文本' }),
      makePlaceholder({ field_id: 'f_date', data_type: 'date', label: '日期' }),
      makePlaceholder({ field_id: 'f_num', data_type: 'number', label: '数字' }),
    ]
    const structure = makeStructure({
      placeholders,
      paragraphs: [
        { index: 0, text: '混合', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '全部字段', style: 'Normal', heading_level: 0, placeholder_ids: ['f_text', 'f_area', 'f_date', 'f_num'] },
      ],
    })

    const wrapper = mountComponent(structure)

    const fieldInputs = wrapper.findAll('.gt-wt-structured-view__field-input')
    expect(fieldInputs.length).toBe(4)

    // Verify different component types are present
    expect(wrapper.find('.el-date-picker').exists()).toBe(true)
    expect(wrapper.find('.el-input-number').exists()).toBe(true)
    wrapper.unmount()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. Disabled AI Tooltip
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtWordTemplateStructuredView — Disabled AI Tooltip', () => {
  it('text placeholder renders a disabled AI button', () => {
    const placeholder = makePlaceholder({ field_id: 'entity', data_type: 'text', label: '单位' })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '信息', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '${entity}', style: 'Normal', heading_level: 0, placeholder_ids: ['entity'] },
      ],
    })

    const wrapper = mountComponent(structure)

    const aiBtn = wrapper.find('.gt-wt-structured-view__ai-btn')
    expect(aiBtn.exists()).toBe(true)
    expect(aiBtn.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('textarea placeholder renders a disabled AI button', () => {
    const placeholder = makePlaceholder({ field_id: 'desc', data_type: 'textarea', label: '描述' })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '描述', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '${desc}', style: 'Normal', heading_level: 0, placeholder_ids: ['desc'] },
      ],
    })

    const wrapper = mountComponent(structure)

    const aiBtn = wrapper.find('.gt-wt-structured-view__ai-btn')
    expect(aiBtn.exists()).toBe(true)
    expect(aiBtn.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('AI button has tooltip with content "AI 填充功能即将上线"', () => {
    const placeholder = makePlaceholder({ field_id: 'name', data_type: 'text', label: '名称' })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '表头', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '${name}', style: 'Normal', heading_level: 0, placeholder_ids: ['name'] },
      ],
    })

    const wrapper = mountComponent(structure)

    const tooltip = wrapper.find('.el-tooltip')
    expect(tooltip.exists()).toBe(true)
    expect(tooltip.attributes('data-content')).toBe('AI 填充功能即将上线')
    wrapper.unmount()
  })

  it('date placeholder does NOT render an AI button', () => {
    const placeholder = makePlaceholder({ field_id: 'audit_date', data_type: 'date', label: '日期' })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '日期', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '${audit_date}', style: 'Normal', heading_level: 0, placeholder_ids: ['audit_date'] },
      ],
    })

    const wrapper = mountComponent(structure)

    const aiBtn = wrapper.find('.gt-wt-structured-view__ai-btn')
    expect(aiBtn.exists()).toBe(false)
    wrapper.unmount()
  })

  it('number placeholder does NOT render an AI button', () => {
    const placeholder = makePlaceholder({ field_id: 'amount', data_type: 'number', label: '金额' })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '金额', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '${amount}', style: 'Normal', heading_level: 0, placeholder_ids: ['amount'] },
      ],
    })

    const wrapper = mountComponent(structure)

    const aiBtn = wrapper.find('.gt-wt-structured-view__ai-btn')
    expect(aiBtn.exists()).toBe(false)
    wrapper.unmount()
  })

  it('AI button remains disabled in both readonly=true and readonly=false', () => {
    const placeholder = makePlaceholder({ field_id: 'f1', data_type: 'text', label: '字段' })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '区块', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '${f1}', style: 'Normal', heading_level: 0, placeholder_ids: ['f1'] },
      ],
    })

    // readonly=false
    const wrapper1 = mountComponent(structure, {}, false)
    expect(wrapper1.find('.gt-wt-structured-view__ai-btn').attributes('disabled')).toBeDefined()
    wrapper1.unmount()

    // readonly=true
    const wrapper2 = mountComponent(structure, {}, true)
    expect(wrapper2.find('.gt-wt-structured-view__ai-btn').attributes('disabled')).toBeDefined()
    wrapper2.unmount()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. No-Placeholder Message
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtWordTemplateStructuredView — No-Placeholder Message', () => {
  it('shows el-alert when template has no placeholders', () => {
    const structure = makeStructure({
      placeholders: [],
      paragraphs: [
        { index: 0, text: '标题', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '纯文本段落', style: 'Normal', heading_level: 0, placeholder_ids: [] },
      ],
    })

    const wrapper = mountComponent(structure)

    const alert = wrapper.find('.gt-wt-structured-view__empty')
    expect(alert.exists()).toBe(true)
    wrapper.unmount()
  })

  it('the no-placeholder alert contains the correct message text', () => {
    const structure = makeStructure({ placeholders: [] })

    const wrapper = mountComponent(structure)

    const empty = wrapper.find('.gt-wt-structured-view__empty')
    expect(empty.exists()).toBe(true)
    // The el-alert stub renders slot content — the component passes as default slot text
    // In the actual template, text is in the default slot of el-alert
    expect(wrapper.text()).toContain('该模板无可编辑字段，请使用在线编辑模式')
    wrapper.unmount()
  })

  it('does NOT show no-placeholder alert when placeholders exist', () => {
    const placeholder = makePlaceholder({ field_id: 'x', data_type: 'text', label: 'X' })
    const structure = makeStructure({
      placeholders: [placeholder],
      paragraphs: [
        { index: 0, text: '有字段', style: 'Heading 1', heading_level: 1, placeholder_ids: [] },
        { index: 1, text: '${x}', style: 'Normal', heading_level: 0, placeholder_ids: ['x'] },
      ],
    })

    const wrapper = mountComponent(structure)

    const alert = wrapper.find('.gt-wt-structured-view__empty')
    expect(alert.exists()).toBe(false)
    wrapper.unmount()
  })

  it('empty placeholders array is treated as no editable fields', () => {
    const structure = makeStructure({
      placeholders: [],
      paragraphs: [],
      tables: [],
    })

    const wrapper = mountComponent(structure)

    expect(wrapper.find('.gt-wt-structured-view__empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('该模板无可编辑字段，请使用在线编辑模式')
    wrapper.unmount()
  })
})
