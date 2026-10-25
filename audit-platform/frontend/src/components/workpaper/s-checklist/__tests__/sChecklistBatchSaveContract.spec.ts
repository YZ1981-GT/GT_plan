import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
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
import S10AdjudicationSheet from '../S10AdjudicationSheet.vue'
import S10InternalControlSheet from '../S10InternalControlSheet.vue'
import S17NonRecurringDetailSheet from '../S17NonRecurringDetailSheet.vue'
import S17ReconciliationSheet from '../S17ReconciliationSheet.vue'
import S17TaxImpactSheet from '../S17TaxImpactSheet.vue'

const buttonStub = { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }
const slotStub = { template: '<div><slot /><slot name="header" /><slot name="dropdown" /></div>' }
const emptyStub = { template: '<span />' }
const stubs = {
  'el-button': buttonStub, 'el-card': slotStub, 'el-dropdown': slotStub,
  'el-table': slotStub, 'el-table-column': emptyStub, 'el-alert': emptyStub,
  'el-input': emptyStub, 'el-input-number': emptyStub, 'el-radio': emptyStub,
  'el-select': emptyStub, 'el-option': emptyStub, 'el-tag': emptyStub,
  'el-segmented': emptyStub, 'el-checkbox': emptyStub, 'el-upload': emptyStub,
  'el-dropdown-menu': emptyStub, 'el-dropdown-item': emptyStub,
  GtIndexChip: emptyStub, WpAmountInput: emptyStub,
}

const writableComponents = [
  { component: S1RegulationRecordSheet, itemId: 'S1-1-sheet-data', payloadKeys: ['regulation_rows', 'overall_conclusion'] },
  { component: S8AdjudicationSheet, itemId: 'S8-1-sheet-data', payloadKeys: ['adjudication_rows', 'conclusion'] },
  { component: S9AdjudicationSheet, itemId: 'S9-1-sheet-data', payloadKeys: ['adjudication_rows', 'conclusion'] },
  { component: S9InternalControlSheet, itemId: 'S9-2-sheet-data', payloadKeys: ['checklist_rows', 'conclusion'] },
  { component: S10AdjudicationSheet, itemId: 'S10-1-sheet-data', payloadKeys: ['adjudication_rows', 'conclusion'] },
  { component: S10InternalControlSheet, itemId: 'S10-2-sheet-data', payloadKeys: ['checklist_rows', 'conclusion'] },
  { component: S17NonRecurringDetailSheet, itemId: 'S17-1-sheet-data', payloadKeys: ['adjudication_rows', 'consolidated_rows', 'individual_rows', 'conclusion'] },
  { component: S17ReconciliationSheet, itemId: 'S17-11-sheet-data', payloadKeys: ['sections', 'conclusion'] },
  { component: S17TaxImpactSheet, itemId: 'S17-21-sheet-data', payloadKeys: ['tax_rate', 'tax_rows', 'audit_note'] },
] as const

const checklistDir = resolve(process.cwd(), 'src/components/workpaper/s-checklist')

describe('D4.1 S-checklist BatchSaveRequest contract', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockGet.mockResolvedValue({ data: { sheets: [] } })
    mockPut.mockReset()
    mockPut.mockResolvedValue({ data: [] })
  })

  it.each(writableComponents)('sends the real request body for $itemId', async ({ component, itemId, payloadKeys }) => {
    const wrapper = mount(component, {
      props: { wpId: 'wp-1', projectId: 'project-1', readonly: false },
      global: { stubs },
    })
    await flushPromises()
    const saveButton = wrapper.findAll('button').find((button) => button.text().trim() === '保存')
    expect(saveButton).toBeDefined()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(mockPut).toHaveBeenCalledTimes(1)
    const [url, body] = mockPut.mock.calls[0]
    expect(url).toBe('/api/workpapers/wp-1/checklist-responses')
    expect(body).toEqual({
      project_id: 'project-1',
      items: [{ item_id: itemId, conclusion: null, remark: expect.any(String) }],
    })
    expect(Object.keys(body.items[0]).sort()).toEqual(['conclusion', 'item_id', 'remark'])
    expect(body).not.toHaveProperty('sheet_name')
    expect(body).not.toHaveProperty('data')
    expect(Object.keys(JSON.parse(body.items[0].remark))).toEqual(payloadKeys)
    wrapper.unmount()
  })

  it('keeps the three reference components read-only and save-free', () => {
    for (const file of ['S9LegalRegulationsSheet.vue', 'S9ProgramDescriptionSheet.vue', 'S10EnvironmentalRegulationsSheet.vue']) {
      const source = readFileSync(`${checklistDir}/${file}`, 'utf-8')
      expect(source).not.toMatch(/http\.(?:put|post|patch|delete)\s*\(/)
      expect(source).not.toMatch(/handleSave\s*\(/)
    }
  })
})
