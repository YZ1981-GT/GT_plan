/**
 * MultiYearCompare.vue 单元测试
 *
 * 覆盖：
 * - 组件渲染（年度选择器 + 报表类型切换 + 表格）
 * - 年度切换触发数据加载
 * - 变动率 ≥ 20% 高亮
 * - 空数据状态
 * - 导出按钮
 *
 * Validates: Requirements F2.1~F2.3
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MultiYearCompare from './MultiYearCompare.vue'

// Mock axios
vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
  },
}))

// Mock useExcelIO
vi.mock('@/composables/useExcelIO', () => ({
  exportData: vi.fn(),
  useExcelIO: () => ({
    exportData: vi.fn(),
    exportTemplate: vi.fn(),
    parseFile: vi.fn(),
    onFileSelected: vi.fn(),
  }),
}))

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

import axios from 'axios'

const mockMultiYearResponse = {
  data: {
    years: [2023, 2024, 2025],
    report_type: 'balance_sheet',
    rows: [
      {
        line_code: 'BS-001',
        item_name: '货币资金',
        values: { '2023': 3000000, '2024': 4500000, '2025': 5000000 },
        yoy_changes: { '2024': 50.0, '2025': 11.11 },
      },
      {
        line_code: 'BS-002',
        item_name: '应收账款',
        values: { '2023': 1000000, '2024': 1250000, '2025': 1100000 },
        yoy_changes: { '2024': 25.0, '2025': -12.0 },
      },
      {
        line_code: 'BS-003',
        item_name: '存货',
        values: { '2023': 500000, '2024': null, '2025': 600000 },
        yoy_changes: { '2024': null, '2025': null },
      },
    ],
  },
}

describe('MultiYearCompare.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(axios.get as any).mockResolvedValue(mockMultiYearResponse)
  })

  const createWrapper = (props = {}) => {
    return mount(MultiYearCompare, {
      props: {
        projectId: 'test-project-id',
        currentYear: 2025,
        ...props,
      },
      global: {
        stubs: {
          'el-select': true,
          'el-option': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-button': true,
          'el-table': {
            template: '<div class="el-table-stub"><slot /></div>',
            props: ['data', 'maxHeight', 'border'],
          },
          'el-table-column': {
            template: '<div class="el-table-column-stub"><slot :row="row" /></div>',
            props: ['label', 'prop', 'fixed', 'align', 'width', 'minWidth'],
            setup() {
              return { row: {} }
            },
          },
        },
      },
    })
  }

  it('renders the component with controls', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    expect(wrapper.find('.gt-multi-year-compare').exists()).toBe(true)
    expect(wrapper.find('.gt-myc-controls').exists()).toBe(true)
  })

  it('defaults to current year and previous year selected', async () => {
    const wrapper = createWrapper({ currentYear: 2025 })
    await flushPromises()

    // Component should have called axios.get on mount with default years
    expect(axios.get).toHaveBeenCalled()
    const callUrl = (axios.get as any).mock.calls[0][0] as string
    expect(callUrl).toContain('2024')
    expect(callUrl).toContain('2025')
  })

  it('fetches data on mount', async () => {
    createWrapper()
    await flushPromises()

    expect(axios.get).toHaveBeenCalledTimes(1)
  })

  it('formats amounts correctly', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    // Access the formatAmount method via component instance
    const vm = wrapper.vm as any
    expect(vm.formatAmount(3000000)).toBe('3,000,000.00')
    expect(vm.formatAmount(null)).toBe('-')
    expect(vm.formatAmount(undefined)).toBe('-')
  })

  it('formats change rates correctly', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.formatChange(50.0)).toBe('+50.00%')
    expect(vm.formatChange(-12.0)).toBe('-12.00%')
    expect(vm.formatChange(null)).toBe('-')
    expect(vm.formatChange(0)).toBe('+0.00%')
  })

  it('returns correct arrow for changes', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.getArrow(50.0)).toBe('↑')
    expect(vm.getArrow(-12.0)).toBe('↓')
    expect(vm.getArrow(0)).toBe('→')
    expect(vm.getArrow(null)).toBe('')
  })

  it('highlights rows with change >= 20%', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    // BS-001 has 50% change → should highlight
    const highlightRow = { yoy_changes: { '2024': 50.0, '2025': 11.11 } }
    expect(vm.rowClassName({ row: highlightRow })).toBe('gt-myc-row--highlight')

    // BS-003 has null changes → no highlight
    const normalRow = { yoy_changes: { '2024': null, '2025': null } }
    expect(vm.rowClassName({ row: normalRow })).toBe('')

    // Row with 15% change → no highlight
    const belowThreshold = { yoy_changes: { '2024': 15.0 } }
    expect(vm.rowClassName({ row: belowThreshold })).toBe('')
  })

  it('applies alert class for change >= 20%', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.getChangeClass(50.0)).toContain('gt-myc-change--alert')
    expect(vm.getChangeClass(-25.0)).toContain('gt-myc-change--alert')
    expect(vm.getChangeClass(10.0)).toContain('gt-myc-change--up')
    expect(vm.getChangeClass(-5.0)).toContain('gt-myc-change--down')
    expect(vm.getChangeClass(null)).toBe('gt-myc-change')
  })

  it('shows empty state when no data', async () => {
    ;(axios.get as any).mockResolvedValue({ data: { years: [2023, 2024], report_type: 'balance_sheet', rows: [] } })

    const wrapper = createWrapper()
    await flushPromises()

    // The component loads with default years [2024, 2025] and gets empty rows
    // Check that tableData is empty
    const vm = wrapper.vm as any
    expect(vm.tableData.length).toBe(0)
    expect(vm.selectedYears.length).toBeGreaterThan(0)
  })

  it('exposes fetchData and onExport methods', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(typeof vm.fetchData).toBe('function')
    expect(typeof vm.onExport).toBe('function')
  })

  it('computes available years from currentYear', async () => {
    const wrapper = createWrapper({ currentYear: 2025 })
    await flushPromises()

    const vm = wrapper.vm as any
    const years = vm.availableYears
    expect(years[0]).toBe(2025)
    expect(years[years.length - 1]).toBe(2016)
    expect(years.length).toBe(10)
  })

  it('sorts selected years ascending', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.selectedYears = [2025, 2023, 2024]
    expect(vm.sortedYears).toEqual([2023, 2024, 2025])
  })
})
