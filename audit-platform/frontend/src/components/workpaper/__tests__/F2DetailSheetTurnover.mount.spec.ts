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

import F2DetailSheetTurnover from '../f2/detail/F2DetailSheetTurnover.vue'

describe('F2DetailSheetTurnover mount', () => {
  it('renders grouped skeleton without crash', async () => {
    const wrapper = mount(F2DetailSheetTurnover, {
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
          'el-dialog': true,
          TurnoverLinesTable: true,
        },
      },
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('F2-5')
    expect(wrapper.text()).toContain('周转材料')
    expect(wrapper.text()).toContain('低值易耗品')
    expect(wrapper.text()).toContain('包装物')
    expect(wrapper.text()).toContain('摊销方法说明')
  })
})
