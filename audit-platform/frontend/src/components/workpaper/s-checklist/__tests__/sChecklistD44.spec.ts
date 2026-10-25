import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockGet, mockPut } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPut: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: { get: mockGet, put: mockPut } }))

import S1RegulationRecordSheet from '../S1RegulationRecordSheet.vue'
import S17NonRecurringDetailSheet from '../S17NonRecurringDetailSheet.vue'
import S17TaxImpactSheet from '../S17TaxImpactSheet.vue'
import { resolveSChecklistHtmlData } from '../sChecklistRenderData'
import { sChecklistItemIds } from '../sChecklistItemIds'

const buttonStub = defineComponent({
  props: { disabled: Boolean, loading: Boolean },
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
})

const formControlStub = defineComponent({
  inheritAttrs: false,
  props: {
    disabled: Boolean,
    modelValue: { type: [String, Number, Boolean], default: undefined },
  },
  emits: ['update:modelValue', 'change'],
  template: '<input :disabled="disabled" :value="modelValue == null ? \'\' : String(modelValue)" />',
})

const segmentedStub = defineComponent({
  props: {
    modelValue: { type: String, default: '' },
    options: { type: Array, default: () => [] },
  },
  emits: ['update:modelValue'],
  template: `
    <div data-testid="s17-view-switcher">
      <button
        v-for="option in options"
        :key="option.value"
        :data-active="modelValue === option.value"
        @click="$emit('update:modelValue', option.value)"
      >{{ option.label }}</button>
    </div>
  `,
})

const tableStub = defineComponent({
  props: { data: { type: Array, default: () => [] } },
  template: '<div data-testid="s17-table">{{ data[0]?.itemName || data[0]?.item_name || "" }}</div>',
})

const slotStub = { template: '<div><slot name="header" /><slot /></div>' }
const emptyStub = { template: '<span><slot /></span>' }
const stubs = {
  'el-button': buttonStub,
  'el-card': slotStub,
  'el-dropdown': slotStub,
  'el-table': tableStub,
  'el-table-column': emptyStub,
  'el-alert': emptyStub,
  'el-input': formControlStub,
  'el-input-number': formControlStub,
  'el-radio': formControlStub,
  'el-select': emptyStub,
  'el-option': emptyStub,
  'el-tag': emptyStub,
  'el-segmented': segmentedStub,
  'el-checkbox': formControlStub,
  'el-upload': emptyStub,
  'el-dropdown-menu': emptyStub,
  'el-dropdown-item': emptyStub,
  GtIndexChip: emptyStub,
  WpAmountInput: formControlStub,
}

function baseProps(componentType: keyof typeof sChecklistItemIds, extra: Record<string, unknown> = {}) {
  return {
    wpId: 'wp-d44',
    projectId: 'project-d44',
    componentType,
    readonly: false,
    ...extra,
  }
}

beforeEach(() => {
  mockGet.mockReset()
  mockGet.mockResolvedValue({ data: { sheets: [] } })
  mockPut.mockReset()
  mockPut.mockResolvedValue({ data: [] })
})

describe('D4.4 S-checklist behavior not duplicated by D4.1–D4.3', () => {
  it.each([
    {
      component: S1RegulationRecordSheet,
      componentType: 's1-regulation-record' as const,
      sheetName: 'S1-1对法律法规的考虑记录表',
      htmlData: {
        component_type: 's1-regulation-record',
        item_id: 'S1-1-sheet-data',
        sheet_name: 'S1-1对法律法规的考虑记录表',
        regulation_rows: [{ id: 'loaded-s1', law_name: '按 identity 加载的法规' }],
        overall_conclusion: '按 identity 加载的结论',
      },
      expected: {
        item_id: 'S1-1-sheet-data',
        marker: '按 identity 加载的法规',
      },
    },
    {
      component: S17TaxImpactSheet,
      componentType: 's17-tax-impact' as const,
      sheetName: '非经常性损益项目的所得税影响S17-21',
      htmlData: {
        component_type: 's17-tax-impact',
        item_id: 'S17-21-sheet-data',
        sheet_name: '非经常性损益项目的所得税影响S17-21',
        tax_rate: 17,
        tax_rows: [{
          id: 'loaded-s17-21',
          item_name: '按 identity 加载的税影响项目',
          gross_amount: 100,
          deductible: true,
          effective_rate: 17,
          tax_impact: 17,
          net_amount: 83,
        }],
        audit_note: '按 identity 加载的税影响说明',
      },
      expected: {
        item_id: 'S17-21-sheet-data',
        marker: '按 identity 加载的税影响项目',
      },
    },
  ])(
    'serializes the loaded $componentType identity payload, not default data',
    async ({ component, componentType, sheetName, htmlData, expected }) => {
      const wrapper = mount(component, {
        props: baseProps(componentType, { sheetName, htmlData }),
        global: { stubs },
      })
      await flushPromises()

      const saveButton = wrapper.findAll('button').find((button) => button.text().trim() === '保存')
      expect(saveButton).toBeDefined()
      await saveButton!.trigger('click')
      await flushPromises()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const [url, body] = mockPut.mock.calls[0]
      expect(url).toBe('/api/workpapers/wp-d44/checklist-responses')
      expect(body.project_id).toBe('project-d44')
      expect(body.items).toHaveLength(1)
      expect(body.items[0]).toMatchObject({ item_id: expected.item_id, conclusion: null })
      const saved = JSON.parse(body.items[0].remark)
      const serialized = JSON.stringify(saved)
      expect(serialized).toContain(expected.marker)
      expect(serialized).not.toContain('非流动资产处置损益')
      wrapper.unmount()
    },
  )

  it('requires the writable item identity when resolving a similarly named sheet', () => {
    const result = resolveSChecklistHtmlData({
      componentType: 's1-regulation-record',
      sheetName: '审定表S1-1',
      response: {
        data: {
          sheets: [
            {
              componentType: 's1-regulation-record',
              sheet_name: '审定表S1-1',
              html_data: {
                component_type: 's1-regulation-record',
                sheet_name: '审定表S1-1',
                regulation_rows: [{ law_name: '缺失 item_id 的错误候选' }],
              },
            },
            {
              componentType: 's1-regulation-record',
              sheet_name: '审定表S1-1',
              html_data: {
                component_type: 's1-regulation-record',
                item_id: 'S1-1-sheet-data',
                sheet_name: '审定表S1-1',
                regulation_rows: [{ law_name: '严格 identity 的正确候选' }],
              },
            },
          ],
        },
      },
    })

    expect(result?.regulation_rows).toEqual([{ law_name: '严格 identity 的正确候选' }])
  })

  it('exposes readonly controls as disabled and remains write-free', async () => {
    const wrapper = mount(S17TaxImpactSheet, {
      props: baseProps('s17-tax-impact', {
        readonly: true,
        sheetName: '非经常性损益项目的所得税影响S17-21',
        htmlData: {
          component_type: 's17-tax-impact',
          item_id: 'S17-21-sheet-data',
          sheet_name: '非经常性损益项目的所得税影响S17-21',
          tax_rows: [{ item_name: '只读项目', gross_amount: 10, deductible: true }],
          audit_note: '只读说明',
        },
      }),
      global: { stubs },
    })
    await flushPromises()

    const controls = wrapper.findAll('input')
    expect(controls.length).toBeGreaterThanOrEqual(2)
    expect(controls.every((control) => control.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.findAll('button').some((button) => button.text().trim() === '保存')).toBe(false)
    await (wrapper.vm as any).handleSave()
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('switches S17 detail views through the visible segmented control', async () => {
    const htmlData = {
      component_type: 's17-nonrecurring-detail',
      item_id: 'S17-1-sheet-data',
      sheet_name: 'S17-1',
      adjudication_rows: [{ itemName: 'S17-1 identity row' }],
      consolidated_rows: [{ itemName: 'S17-2 identity row' }],
      individual_rows: [{ itemName: 'S17-3 identity row' }],
    }
    const wrapper = mount(S17NonRecurringDetailSheet, {
      props: baseProps('s17-nonrecurring-detail', {
        sheetName: 'S17-1',
        htmlData,
      }),
      global: { stubs },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="s17-table"]').text()).toContain('S17-1 identity row')
    const switcher = wrapper.get('[data-testid="s17-view-switcher"]')
    await switcher.findAll('button')[1].trigger('click')
    expect(wrapper.get('[data-testid="s17-table"]').text()).toContain('S17-2 identity row')
    await switcher.findAll('button')[2].trigger('click')
    expect(wrapper.get('[data-testid="s17-table"]').text()).toContain('S17-3 identity row')
    expect(mockPut).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('updates the detail view when the exact sheetName changes', async () => {
    const wrapper = mount(S17NonRecurringDetailSheet, {
      props: baseProps('s17-nonrecurring-detail', {
        sheetName: 'S17-1',
        htmlData: {
          component_type: 's17-nonrecurring-detail',
          item_id: 'S17-1-sheet-data',
          sheet_name: 'S17-1',
          adjudication_rows: [{ itemName: '初始 S17-1 行' }],
        },
      }),
      global: { stubs },
    })
    await flushPromises()

    await wrapper.setProps({
      sheetName: '审核表（个别报表）S17-3',
      htmlData: {
        component_type: 's17-nonrecurring-detail',
        item_id: 'S17-1-sheet-data',
        sheet_name: '审核表（个别报表）S17-3',
        individual_rows: [{ itemName: '切换后的 S17-3 行' }],
      },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="s17-table"]').text()).toContain('切换后的 S17-3 行')
    expect((wrapper.vm as any).activeView).toBe('individual')
    wrapper.unmount()
  })
})
