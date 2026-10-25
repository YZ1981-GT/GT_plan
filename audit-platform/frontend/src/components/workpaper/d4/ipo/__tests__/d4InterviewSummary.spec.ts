import { describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn().mockResolvedValue({ data: { status: 'healthy' } }), post: vi.fn() } }))
vi.mock('../../composables/useD4ImportExport', () => ({
  useD4ImportExport: () => ({ exportTemplate: vi.fn(), exportData: vi.fn(), importData: vi.fn(), importing: false }),
}))

import D4TabInterviewSummary from '../D4TabInterviewSummary.vue'

const FindingStub = defineComponent({ props: ['findings'], template: '<span />' })
const stubs = {
  D4IpoFindingWriteback: FindingStub,
  GtOnlyOfficeSheet: { template: '<div />' },
  GtIndexChip: { template: '<span />' },
  'el-button': { template: '<button><slot /></button>' },
  'el-dropdown': { template: '<div><slot /><slot name="dropdown" /></div>' },
  'el-dropdown-menu': { template: '<div><slot /></div>' },
  'el-dropdown-item': { template: '<div><slot /></div>' },
  'el-upload': { template: '<div><slot /></div>' },
  'el-segmented': { props: ['modelValue'], template: '<span />' },
  'el-tabs': { template: '<div><slot /></div>' },
  'el-tab-pane': { template: '<div />' },
  'el-input': { template: '<input />' },
  'el-table': { template: '<div><slot /></div>' },
  'el-table-column': { template: '<div />' },
  'el-empty': { template: '<div><slot /></div>' },
  'el-card': { template: '<div><slot /></div>' },
  'el-icon': { template: '<span><slot /></span>' },
}

function wrapperFor(fields: Record<string, string>) {
  const allResponses = new Map([['D4-30-customers', { remark: JSON.stringify({ customers: [{ id: 'c1', name: '客户甲', fields }], customDimensions: [] }) }]])
  return mount(D4TabInterviewSummary, { props: { wpId: 'wp', projectId: 'p', allResponses, isReadonly: false }, global: { stubs } })
}

describe('D4-30 访谈红旗 findings prop', () => {
  it.each([
    ['amountMatch', '不一致'], ['balanceMatch', '不一致'],
  ])('%s=不一致时出现候选发现', async (field, value) => {
    const wrapper = wrapperFor({ [field]: value })
    await nextTick()
    expect(wrapper.findComponent(FindingStub).props('findings')).toHaveLength(1)
    wrapper.unmount()
  })

  it.each(['一致', '是', '', undefined])('%s不产生候选发现', async value => {
    const wrapper = wrapperFor({ amountMatch: value as string })
    await nextTick()
    expect(wrapper.findComponent(FindingStub).props('findings')).toHaveLength(0)
    wrapper.unmount()
  })

  it('reason单独非空不产生候选发现', async () => {
    const wrapper = wrapperFor({ reason: '客户异常说明' })
    await nextTick()
    expect(wrapper.findComponent(FindingStub).props('findings')).toHaveLength(0)
    wrapper.unmount()
  })
})
