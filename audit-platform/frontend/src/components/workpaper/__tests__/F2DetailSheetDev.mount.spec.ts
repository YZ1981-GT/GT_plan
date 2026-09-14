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

import F2DetailSheetDev from '../f2/detail/F2DetailSheetDev.vue'

describe('F2DetailSheetDev mount', () => {
  it('renders three-table skeleton without crash', async () => {
    const wrapper = mount(F2DetailSheetDev, {
      props: {
        wpId: 'wp-1',
        projectId: 'p1',
        allResponses: new Map(),
        isReadonly: false,
      },
      global: {
        stubs: {
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
        },
      },
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('F2-10')
    expect(wrapper.text()).toMatch(/原值|跌价|净值/)
    expect(wrapper.text()).toContain('开发产品')
  })
})
