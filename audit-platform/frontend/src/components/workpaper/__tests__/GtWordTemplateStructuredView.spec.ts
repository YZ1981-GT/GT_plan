/**
 * PBT — GtWordTemplateStructuredView.vue
 *
 * Feature: word-template-dual-mode, Property 14: AI button presence for text/textarea
 *
 * For any placeholder with data_type "text" or "textarea" in the rendered Structured View,
 * an AI Fill button SHALL be present adjacent to the input field.
 * For data_type "date" or "number", NO AI button SHALL be rendered.
 * The AI button SHALL be disabled with tooltip "AI 填充功能即将上线".
 *
 * **Validates: Requirements 7.1**
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import * as fc from 'fast-check'
import GtWordTemplateStructuredView from '../GtWordTemplateStructuredView.vue'
import type { TemplateStructure, PlaceholderDef } from '../composables/useWordTemplateStructured'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makePlaceholder(overrides: Partial<PlaceholderDef> & { field_id: string; data_type: string }): PlaceholderDef {
  return {
    field_id: overrides.field_id,
    label: overrides.label || `Label for ${overrides.field_id}`,
    data_type: overrides.data_type,
    default_value: overrides.default_value || '',
    position: overrides.position || { paragraph_index: 0 },
    pattern: overrides.pattern || `\${${overrides.field_id}}`,
    current_value: overrides.current_value || '',
  }
}

function makeStructure(placeholders: PlaceholderDef[]): TemplateStructure {
  return {
    placeholders,
    paragraphs: [
      {
        index: 0,
        text: '文档标题',
        style: 'Heading 1',
        heading_level: 1,
        placeholder_ids: [],
      },
      {
        index: 1,
        text: '内容段落',
        style: 'Normal',
        heading_level: 0,
        placeholder_ids: placeholders.map(p => p.field_id),
      },
    ],
    tables: [],
    metadata: { template_name: 'Test Template', wp_code: 'TEST-1', last_parsed_at: '2026-01-01T00:00:00Z' },
  }
}

// ─── Arbitraries ─────────────────────────────────────────────────────────────

/** field_id: lowercase alphanumeric + underscore, 1–20 chars */
const arbFieldId = fc.stringMatching(/^[a-z][a-z0-9_]{0,19}$/)

/** data_type that should show AI button */
const arbAiEnabledType = fc.constantFrom('text', 'textarea')

/** data_type that should NOT show AI button */
const arbAiDisabledType = fc.constantFrom('date', 'number')

/** All valid data_types */
const arbDataType = fc.constantFrom('text', 'textarea', 'date', 'number')

/** Random placeholder array with mixed data_types */
const arbPlaceholderArray = fc.array(
  fc.record({
    fieldId: arbFieldId,
    dataType: arbDataType,
    label: fc.string({ minLength: 1, maxLength: 20 }),
  }),
  { minLength: 1, maxLength: 8 },
).map(items => {
  // Deduplicate by fieldId
  const seen = new Set<string>()
  return items.filter(item => {
    if (seen.has(item.fieldId)) return false
    seen.add(item.fieldId)
    return true
  })
}).filter(arr => arr.length > 0)

// ─── Test Suite ──────────────────────────────────────────────────────────────

describe('Feature: word-template-dual-mode, Property 14: AI button presence for text/textarea', () => {
  /**
   * **Validates: Requirements 7.1**
   *
   * For any placeholder with data_type "text" or "textarea", an AI Fill button SHALL
   * be present adjacent to the input field. The button SHALL be disabled.
   */
  it('text/textarea placeholders always render a disabled AI Fill button', () => {
    fc.assert(
      fc.property(
        arbFieldId,
        arbAiEnabledType,
        (fieldId, dataType) => {
          const placeholder = makePlaceholder({ field_id: fieldId, data_type: dataType })
          const structure = makeStructure([placeholder])

          const wrapper = mount(GtWordTemplateStructuredView, {
            props: {
              templateStructure: structure,
              fieldValues: {},
              readonly: false,
            },
            global: {
              stubs: {
                'el-card': { template: '<div class="el-card"><slot name="header"/><slot/></div>' },
                'el-input': { template: '<input class="el-input" />', props: ['modelValue'] },
                'el-date-picker': { template: '<input class="el-date-picker" />', props: ['modelValue'] },
                'el-input-number': { template: '<input class="el-input-number" />', props: ['modelValue'] },
                'el-table': { template: '<table class="el-table"><slot/></table>' },
                'el-table-column': { template: '<td><slot/></td>' },
                'el-alert': { template: '<div class="el-alert"><slot/></div>' },
                'el-tooltip': { template: '<div class="el-tooltip" data-testid="ai-tooltip"><slot/></div>', props: ['content'] },
                'el-button': {
                  template: '<button class="el-button" :disabled="disabled" data-testid="ai-btn"></button>',
                  props: ['disabled', 'size', 'icon'],
                },
              },
            },
          })

          // AI button should exist for text/textarea
          const aiBtn = wrapper.find('.gt-wt-structured-view__ai-btn')
          expect(aiBtn.exists()).toBe(true)

          // AI button should be disabled
          expect(aiBtn.attributes('disabled')).toBeDefined()

          // Tooltip wrapper should exist
          const tooltip = wrapper.find('[data-testid="ai-tooltip"]')
          expect(tooltip.exists()).toBe(true)

          wrapper.unmount()
        },
      ),
      { numRuns: 100 },
    )
  })

  /**
   * For any placeholder with data_type "date" or "number", NO AI Fill button SHALL be rendered.
   */
  it('date/number placeholders do NOT render an AI Fill button', () => {
    fc.assert(
      fc.property(
        arbFieldId,
        arbAiDisabledType,
        (fieldId, dataType) => {
          const placeholder = makePlaceholder({ field_id: fieldId, data_type: dataType })
          const structure = makeStructure([placeholder])

          const wrapper = mount(GtWordTemplateStructuredView, {
            props: {
              templateStructure: structure,
              fieldValues: {},
              readonly: false,
            },
            global: {
              stubs: {
                'el-card': { template: '<div class="el-card"><slot name="header"/><slot/></div>' },
                'el-input': { template: '<input class="el-input" />', props: ['modelValue'] },
                'el-date-picker': { template: '<input class="el-date-picker" />', props: ['modelValue'] },
                'el-input-number': { template: '<input class="el-input-number" />', props: ['modelValue'] },
                'el-table': { template: '<table class="el-table"><slot/></table>' },
                'el-table-column': { template: '<td><slot/></td>' },
                'el-alert': { template: '<div class="el-alert"><slot/></div>' },
                'el-tooltip': { template: '<div class="el-tooltip" data-testid="ai-tooltip"><slot/></div>', props: ['content'] },
                'el-button': {
                  template: '<button class="el-button" :disabled="disabled" data-testid="ai-btn"></button>',
                  props: ['disabled', 'size', 'icon'],
                },
              },
            },
          })

          // AI button should NOT exist for date/number
          const aiBtn = wrapper.find('.gt-wt-structured-view__ai-btn')
          expect(aiBtn.exists()).toBe(false)

          // No tooltip for AI either
          const tooltip = wrapper.find('[data-testid="ai-tooltip"]')
          expect(tooltip.exists()).toBe(false)

          wrapper.unmount()
        },
      ),
      { numRuns: 100 },
    )
  })

  /**
   * Mixed placeholder arrays: AI buttons appear exactly for text/textarea types,
   * and the count matches the number of text+textarea placeholders.
   */
  it('in a mixed-type placeholder list, AI button count equals text+textarea placeholder count', () => {
    fc.assert(
      fc.property(
        arbPlaceholderArray,
        (items) => {
          const placeholders = items.map(item =>
            makePlaceholder({ field_id: item.fieldId, data_type: item.dataType, label: item.label }),
          )
          const structure = makeStructure(placeholders)

          const wrapper = mount(GtWordTemplateStructuredView, {
            props: {
              templateStructure: structure,
              fieldValues: {},
              readonly: false,
            },
            global: {
              stubs: {
                'el-card': { template: '<div class="el-card"><slot name="header"/><slot/></div>' },
                'el-input': { template: '<input class="el-input" />', props: ['modelValue'] },
                'el-date-picker': { template: '<input class="el-date-picker" />', props: ['modelValue'] },
                'el-input-number': { template: '<input class="el-input-number" />', props: ['modelValue'] },
                'el-table': { template: '<table class="el-table"><slot/></table>' },
                'el-table-column': { template: '<td><slot/></td>' },
                'el-alert': { template: '<div class="el-alert"><slot/></div>' },
                'el-tooltip': { template: '<div class="el-tooltip" data-testid="ai-tooltip"><slot/></div>', props: ['content'] },
                'el-button': {
                  template: '<button class="el-button" :disabled="disabled" data-testid="ai-btn"></button>',
                  props: ['disabled', 'size', 'icon'],
                },
              },
            },
          })

          const expectedAiCount = items.filter(i => i.dataType === 'text' || i.dataType === 'textarea').length
          const aiBtns = wrapper.findAll('.gt-wt-structured-view__ai-btn')
          expect(aiBtns.length).toBe(expectedAiCount)

          // All AI buttons should be disabled
          for (const btn of aiBtns) {
            expect(btn.attributes('disabled')).toBeDefined()
          }

          wrapper.unmount()
        },
      ),
      { numRuns: 100 },
    )
  })

  /**
   * AI button disabled state holds regardless of readonly prop.
   */
  it('AI button remains disabled regardless of readonly prop value', () => {
    fc.assert(
      fc.property(
        arbFieldId,
        arbAiEnabledType,
        fc.boolean(),
        (fieldId, dataType, isReadonly) => {
          const placeholder = makePlaceholder({ field_id: fieldId, data_type: dataType })
          const structure = makeStructure([placeholder])

          const wrapper = mount(GtWordTemplateStructuredView, {
            props: {
              templateStructure: structure,
              fieldValues: {},
              readonly: isReadonly,
            },
            global: {
              stubs: {
                'el-card': { template: '<div class="el-card"><slot name="header"/><slot/></div>' },
                'el-input': { template: '<input class="el-input" />', props: ['modelValue', 'disabled'] },
                'el-date-picker': { template: '<input class="el-date-picker" />', props: ['modelValue', 'disabled'] },
                'el-input-number': { template: '<input class="el-input-number" />', props: ['modelValue', 'disabled'] },
                'el-table': { template: '<table class="el-table"><slot/></table>' },
                'el-table-column': { template: '<td><slot/></td>' },
                'el-alert': { template: '<div class="el-alert"><slot/></div>' },
                'el-tooltip': { template: '<div class="el-tooltip" data-testid="ai-tooltip"><slot/></div>', props: ['content'] },
                'el-button': {
                  template: '<button class="el-button" :disabled="disabled" data-testid="ai-btn"></button>',
                  props: ['disabled', 'size', 'icon'],
                },
              },
            },
          })

          const aiBtn = wrapper.find('.gt-wt-structured-view__ai-btn')
          expect(aiBtn.exists()).toBe(true)
          // AI button is always disabled (Phase3 not deployed)
          expect(aiBtn.attributes('disabled')).toBeDefined()

          wrapper.unmount()
        },
      ),
      { numRuns: 100 },
    )
  })
})
