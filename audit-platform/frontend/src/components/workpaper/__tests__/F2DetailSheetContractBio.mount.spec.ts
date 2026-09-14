import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessageBox: { prompt: vi.fn().mockResolvedValue({ value: 'x' }), confirm: vi.fn() },
    ElMessage: { warning: vi.fn(), success: vi.fn() },
  }
})

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { data: { status: 'healthy' } } }),
    post: vi.fn(),
  },
}))

vi.mock('../shared/CycleImportExportDropdown.vue', () => ({
  default: defineComponent({ name: 'CycleImportExportDropdown', render: () => h('div') }),
}))
vi.mock('../GtIndexChip.vue', () => ({
  default: defineComponent({ name: 'GtIndexChip', render: () => h('div') }),
}))

import F2DetailSheetContractPerf from '../f2/detail/F2DetailSheetContractPerf.vue'
import F2DetailSheetBio from '../f2/detail/F2DetailSheetBio.vue'

const stubs = {
  'el-table': true,
  'el-table-column': true,
  'el-input': true,
  'el-input-number': true,
  'el-button': true,
  'el-tag': true,
  'el-alert': true,
  'el-select': true,
  'el-option': true,
  'el-radio-group': true,
  'el-radio-button': true,
}

describe('F2-12 / F2-13 mount', () => {
  it('renders F2-12 contract performance sheet', async () => {
    const wrapper = mount(F2DetailSheetContractPerf, {
      props: {
        wpId: 'wp-1',
        projectId: 'p1',
        allResponses: new Map(),
        isReadonly: false,
      },
      global: { stubs },
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('F2-12')
    expect(wrapper.text()).toContain('合同履约成本')
    expect(wrapper.text()).toContain('停建')
  })

  it('renders F2-13 bio asset sheet', async () => {
    const wrapper = mount(F2DetailSheetBio, {
      props: {
        wpId: 'wp-1',
        projectId: 'p1',
        allResponses: new Map(),
        isReadonly: false,
      },
      global: { stubs },
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('F2-13')
    expect(wrapper.text()).toContain('消耗性生物资产')
    expect(wrapper.text()).toMatch(/原值|跌价|净值/)
  })
})
