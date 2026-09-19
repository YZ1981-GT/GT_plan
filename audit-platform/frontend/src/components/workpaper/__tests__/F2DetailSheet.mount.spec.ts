/**
 * Mount smoke test for F2DetailSheet — catch render crashes
 */
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

vi.mock('../../shared/CycleImportExportDropdown.vue', () => ({
  default: defineComponent({ name: 'CycleImportExportDropdown', render: () => h('div') }),
}))
vi.mock('../../GtIndexChip.vue', () => ({
  default: defineComponent({ name: 'GtIndexChip', render: () => h('div') }),
}))

import F2DetailSheet from '../f2/detail/F2DetailSheet.vue'
import { F2_DETAIL_SHEET_CONFIGS } from '../f2/detail/f2DetailSheetConfigs'

describe('F2DetailSheet mount', () => {
  it('renders F2-3 without crash', async () => {
    const wrapper = mount(F2DetailSheet, {
      props: {
        config: F2_DETAIL_SHEET_CONFIGS['F2-3'],
        wpId: 'wp-1',
        projectId: 'p1',
        allResponses: new Map(),
        isReadonly: false,
      },
      global: {
        stubs: {
          'el-table-v2': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-popover': true,
          'el-dialog': true,
          'el-card': true,
          'el-alert': true,
          'el-tag': true,
          'el-button': true,
          'el-input': true,
          'el-input-number': true,
          'el-select': true,
          'el-option': true,
          'el-checkbox': true,
          'el-divider': true,
          'el-tooltip': true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('原材料明细表')
    expect(wrapper.text()).toContain('F2-3')
  })

  it('renders F2-4 inTransit without crash', async () => {
    const wrapper = mount(F2DetailSheet, {
      props: {
        config: F2_DETAIL_SHEET_CONFIGS['F2-4'],
        wpId: 'wp-1',
        projectId: 'p1',
        allResponses: new Map(),
        isReadonly: false,
      },
      global: {
        stubs: {
          'el-table-v2': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-popover': true,
          'el-dialog': true,
          'el-card': true,
          'el-alert': true,
          'el-tag': true,
          'el-button': true,
          'el-input': true,
          'el-input-number': true,
          'el-select': true,
          'el-option': true,
          'el-checkbox': true,
          'el-divider': true,
          'el-tooltip': true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('材料采购/在途物资')
    expect(wrapper.text()).toContain('F2-4')
  })

  it('renders F2-6 semi-finished without crash', async () => {
    const wrapper = mount(F2DetailSheet, {
      props: {
        config: F2_DETAIL_SHEET_CONFIGS['F2-6'],
        wpId: 'wp-1',
        projectId: 'p1',
        allResponses: new Map(),
        isReadonly: false,
      },
      global: {
        stubs: {
          'el-table-v2': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-popover': true,
          'el-dialog': true,
          'el-card': true,
          'el-alert': true,
          'el-tag': true,
          'el-button': true,
          'el-input': true,
          'el-input-number': true,
          'el-select': true,
          'el-option': true,
          'el-checkbox': true,
          'el-divider': true,
          'el-tooltip': true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('自制半成品')
    expect(wrapper.text()).toContain('F2-6')
  })

  const stubs = {
    'el-table-v2': true,
    'el-radio-group': true,
    'el-radio-button': true,
    'el-popover': true,
    'el-dialog': true,
    'el-card': true,
    'el-alert': true,
    'el-tag': true,
    'el-button': true,
    'el-input': true,
    'el-input-number': true,
    'el-select': true,
    'el-option': true,
    'el-checkbox': true,
    'el-divider': true,
    'el-tooltip': true,
    'el-table': true,
    'el-table-column': true,
  }

  it('renders F2-8 finished goods with sales ledger recon', async () => {
    const wrapper = mount(F2DetailSheet, {
      props: {
        config: F2_DETAIL_SHEET_CONFIGS['F2-8'],
        wpId: 'wp-1',
        projectId: 'p1',
        allResponses: new Map(),
        isReadonly: false,
      },
      global: { stubs },
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('库存商品')
    expect(wrapper.text()).toContain('F2-8')
    expect(wrapper.text()).toContain('销售出库数量')
    expect(wrapper.text()).toContain('差异')
  })

  it('renders F2-9 dispatched goods with party columns', async () => {
    const wrapper = mount(F2DetailSheet, {
      props: {
        config: F2_DETAIL_SHEET_CONFIGS['F2-9'],
        wpId: 'wp-1',
        projectId: 'p1',
        allResponses: new Map(),
        isReadonly: false,
      },
      global: { stubs },
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('发出商品')
    expect(wrapper.text()).toContain('F2-9')
    expect(wrapper.text()).toContain('销售出库数量')
    expect(wrapper.text()).toContain('资产负债表日后销售情况')
  })
})
