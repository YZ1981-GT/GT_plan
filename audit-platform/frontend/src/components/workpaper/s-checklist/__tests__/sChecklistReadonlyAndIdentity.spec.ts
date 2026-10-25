import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockGet, mockPut } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPut: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: { get: mockGet, put: mockPut } }))

import S1RegulationRecordSheet from '../S1RegulationRecordSheet.vue'
import S8AdjudicationSheet from '../S8AdjudicationSheet.vue'
import S9AdjudicationSheet from '../S9AdjudicationSheet.vue'
import S9InternalControlSheet from '../S9InternalControlSheet.vue'
import S9LegalRegulationsSheet from '../S9LegalRegulationsSheet.vue'
import S9ProgramDescriptionSheet from '../S9ProgramDescriptionSheet.vue'
import S10AdjudicationSheet from '../S10AdjudicationSheet.vue'
import S10InternalControlSheet from '../S10InternalControlSheet.vue'
import S10EnvironmentalRegulationsSheet from '../S10EnvironmentalRegulationsSheet.vue'
import S17NonRecurringDetailSheet from '../S17NonRecurringDetailSheet.vue'
import S17ReconciliationSheet from '../S17ReconciliationSheet.vue'
import S17TaxImpactSheet from '../S17TaxImpactSheet.vue'
import type { SChecklistComponentType } from '../sChecklistItemIds'
import { sChecklistItemIds } from '../sChecklistItemIds'

const buttonStub = defineComponent({
  props: { disabled: Boolean, loading: Boolean },
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
})
const slotStub = { template: '<div><slot /><slot name="header" /><slot name="dropdown" /></div>' }
const emptyStub = { template: '<span />' }
const stubs = {
  'el-button': buttonStub,
  'el-card': slotStub,
  'el-dropdown': slotStub,
  'el-table': slotStub,
  'el-table-column': emptyStub,
  'el-alert': emptyStub,
  'el-input': emptyStub,
  'el-input-number': emptyStub,
  'el-radio': emptyStub,
  'el-select': emptyStub,
  'el-option': emptyStub,
  'el-tag': emptyStub,
  'el-segmented': emptyStub,
  'el-checkbox': emptyStub,
  'el-upload': emptyStub,
  'el-dropdown-menu': emptyStub,
  'el-dropdown-item': emptyStub,
  GtIndexChip: emptyStub,
  WpAmountInput: emptyStub,
}

const writableCases = [
  {
    component: S1RegulationRecordSheet,
    componentType: 's1-regulation-record',
    sheetName: '审定表S1-1',
    stateKey: 'regulationRows',
    stateLabelKey: 'lawName',
    payload: { regulation_rows: [{ law_name: '目标 S1 数据' }], overall_conclusion: '目标结论' },
    expectedLabel: '目标 S1 数据',
  },
  {
    component: S8AdjudicationSheet,
    componentType: 's8-adjudication',
    sheetName: '审定表S8-1',
    stateKey: 'adjudicationRows',
    stateLabelKey: 'accountName',
    payload: { adjudication_rows: [{ account_name: '目标 S8 数据' }], conclusion: '目标结论' },
    expectedLabel: '目标 S8 数据',
  },
  {
    component: S9AdjudicationSheet,
    componentType: 's9-adjudication',
    sheetName: '审定表S9-1',
    stateKey: 'adjudicationRows',
    stateLabelKey: 'accountName',
    payload: { adjudication_rows: [{ account_name: '目标 S9 数据' }], conclusion: '目标结论' },
    expectedLabel: '目标 S9 数据',
  },
  {
    component: S9InternalControlSheet,
    componentType: 's9-internal-control',
    sheetName: '内部控制调查表S9-2',
    stateKey: 'checklistRows',
    stateLabelKey: 'controlItem',
    payload: { checklist_rows: [{ control_item: '目标 S9 内控数据' }], conclusion: '目标结论' },
    expectedLabel: '目标 S9 内控数据',
  },
  {
    component: S10AdjudicationSheet,
    componentType: 's10-adjudication',
    sheetName: '审定表S10-1',
    stateKey: 'adjudicationRows',
    stateLabelKey: 'accountName',
    payload: { adjudication_rows: [{ account_name: '目标 S10 数据' }], conclusion: '目标结论' },
    expectedLabel: '目标 S10 数据',
  },
  {
    component: S10InternalControlSheet,
    componentType: 's10-internal-control',
    sheetName: '内控调查表S10-2',
    stateKey: 'checklistRows',
    stateLabelKey: 'controlItem',
    payload: { checklist_rows: [{ control_item: '目标 S10 内控数据' }], conclusion: '目标结论' },
    expectedLabel: '目标 S10 内控数据',
  },
  {
    component: S17NonRecurringDetailSheet,
    componentType: 's17-nonrecurring-detail',
    sheetName: '审核表（个别报表）S17-3',
    stateKey: 'individualRows',
    stateLabelKey: 'itemName',
    payload: { individual_rows: [{ itemName: '目标 S17-3 数据' }], conclusion: '目标结论' },
    expectedLabel: '目标 S17-3 数据',
  },
  {
    component: S17ReconciliationSheet,
    componentType: 's17-reconciliation',
    sheetName: '与营业外收支等核对表S17-11',
    stateKey: 'reconciliationSections',
    stateLabelKey: 'rows',
    payload: {
      sections: [{ id: 'target', title: '目标区段', rows: [{ item_name: '目标 S17-11 数据' }] }],
      conclusion: '目标结论',
    },
    expectedLabel: '目标 S17-11 数据',
  },
  {
    component: S17TaxImpactSheet,
    componentType: 's17-tax-impact',
    sheetName: '非经常性损益项目的所得税影响S17-21',
    stateKey: 'taxRows',
    stateLabelKey: 'itemName',
    payload: { tax_rows: [{ item_name: '目标 S17-21 数据' }], tax_rate: 25, audit_note: '目标说明' },
    expectedLabel: '目标 S17-21 数据',
  },
] as const satisfies ReadonlyArray<{
  component: any
  componentType: SChecklistComponentType
  sheetName: string
  stateKey: string
  stateLabelKey: string
  payload: Record<string, any>
  expectedLabel: string
}>

const referenceCases = [
  { component: S9LegalRegulationsSheet, componentType: 's9-legal-regulations' },
  { component: S9ProgramDescriptionSheet, componentType: 's9-program-description' },
  { component: S10EnvironmentalRegulationsSheet, componentType: 's10-environmental-regulations' },
] as const

function baseProps(componentType: SChecklistComponentType, extra: Record<string, unknown> = {}) {
  return {
    wpId: 'wp-1',
    projectId: 'project-1',
    readonly: true,
    componentType,
    ...extra,
  }
}

describe('D4.2 real S-checklist component behavior', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockGet.mockResolvedValue({ data: { sheets: [] } })
    mockPut.mockReset()
    mockPut.mockResolvedValue({ data: [] })
  })

  it.each([...writableCases, ...referenceCases])(
    'uses readonly prop and sends no write request for $componentType',
    async ({ component, componentType }) => {
      const wrapper = mount(component, {
        props: baseProps(componentType),
        global: { stubs },
      })
      await flushPromises()

      expect(wrapper.findAll('button').some((button) => button.text().trim() === '保存')).toBe(false)
      expect(mockPut).not.toHaveBeenCalled()
      wrapper.unmount()
    },
  )

  it.each(writableCases)(
    'loads $componentType by exact componentType and sheet identity',
    async ({ component, componentType, sheetName, stateKey, stateLabelKey, payload, expectedLabel }) => {
      mockGet.mockResolvedValue({
        data: {
          sheets: [
            {
              componentType,
              sheet_name: `相似标题-${sheetName}`,
              html_data: {
                component_type: componentType,
                item_id: 'wrong-item-identity',
                sheet_name: `相似标题-${sheetName}`,
                ...payload,
              },
            },
            {
              componentType,
              sheet_name: sheetName,
              html_data: {
                component_type: componentType,
                item_id: sChecklistItemIds[componentType],
                sheet_name: sheetName,
                ...payload,
              },
            },
          ],
        },
      })

      const wrapper = mount(component, {
        props: baseProps(componentType, { sheetName }),
        global: { stubs },
      })
      await flushPromises()

      const state = (wrapper.vm as any)[stateKey]
      if (componentType === 's17-reconciliation') {
        expect(state[0].rows[0].itemName).toBe(expectedLabel)
      } else {
        expect(state[0][stateLabelKey]).toBe(expectedLabel)
      }
      expect(mockPut).not.toHaveBeenCalled()
      wrapper.unmount()
    },
  )

  it('maps an exact S17-3 sheet identity to the individual view', async () => {
    const wrapper = mount(S17NonRecurringDetailSheet, {
      props: baseProps('s17-nonrecurring-detail', { sheetName: '审核表（个别报表）S17-3' }),
      global: { stubs },
    })
    await flushPromises()

    expect((wrapper.vm as any).activeView).toBe('individual')
    expect(mockPut).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})


describe('D4.3 S17 sheet identity and disabled import/export entry', () => {
  const s17ViewCases = [
    { sheetName: 'S17-1', expectedView: 'adjudication' },
    { sheetName: 'S17-2', expectedView: 'consolidated' },
    { sheetName: 'S17-3', expectedView: 'individual' },
  ] as const

  it.each(s17ViewCases)('maps exact sheetName $sheetName to its view', async ({ sheetName, expectedView }) => {
    const wrapper = mount(S17NonRecurringDetailSheet, {
      props: baseProps('s17-nonrecurring-detail', {
        sheetName,
        htmlData: {
          component_type: 's17-nonrecurring-detail',
          item_id: sChecklistItemIds['s17-nonrecurring-detail'],
          sheet_name: sheetName,
        },
      }),
      global: { stubs },
    })
    await flushPromises()

    expect((wrapper.vm as any).activeView).toBe(expectedView)
    expect(mockGet.mock.calls.filter(([url]) => String(url).startsWith('/api/s-special/'))).toHaveLength(0)
    wrapper.unmount()
  })

  it.each([
    {
      component: S1RegulationRecordSheet,
      componentType: 's1-regulation-record' as const,
      sheetName: '审定表S1-1',
      htmlData: {
        component_type: 's1-regulation-record',
        item_id: sChecklistItemIds['s1-regulation-record'],
        sheet_name: '审定表S1-1',
      },
    },
    {
      component: S17NonRecurringDetailSheet,
      componentType: 's17-nonrecurring-detail' as const,
      sheetName: 'S17-2',
      htmlData: {
        component_type: 's17-nonrecurring-detail',
        item_id: sChecklistItemIds['s17-nonrecurring-detail'],
        sheet_name: 'S17-2',
      },
    },
  ])('keeps the $componentType import/export entry visible but disabled without requests', async ({
    component,
    componentType,
    sheetName,
    htmlData,
  }) => {
    for (const readonly of [true, false]) {
      const wrapper = mount(component, {
        props: baseProps(componentType, { readonly, sheetName, htmlData }),
        global: { stubs },
      })
      await flushPromises()

      const entry = wrapper.findAll('button').find((button) =>
        button.text().trim() === '导入导出（开发中）',
      )
      expect(entry?.exists()).toBe(true)
      expect(entry?.attributes('disabled')).toBeDefined()
      expect(mockGet.mock.calls.filter(([url]) => String(url).startsWith('/api/s-special/'))).toHaveLength(0)

      mockGet.mockClear()
      mockPut.mockClear()
      if (entry) await entry.trigger('click')
      expect(mockGet).not.toHaveBeenCalled()
      expect(mockPut).not.toHaveBeenCalled()
      wrapper.unmount()
    }
  })
})
