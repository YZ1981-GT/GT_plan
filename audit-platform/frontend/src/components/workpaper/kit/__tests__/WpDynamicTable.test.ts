/**
 * WpDynamicTable 单元测试
 *
 * Feature: platform-global-hardening
 * Requirements: 4.5, 4.7
 *
 * 注：el-table 在 jsdom 中不渲染行数据（依赖 DOM 测量），
 * 因此测试侧重于组件逻辑（合计计算、列合并、事件 emit）而非 el-table 渲染输出。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import WpDynamicTable from '../WpDynamicTable.vue'
import type { WpDynamicColumn, DynamicRow, AgingBand } from '../WpDynamicTable.vue'

// Mock displayPrefs store
const mockFmtAmount = vi.fn((v: any) => {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
})
const mockAmountClass = vi.fn((v: any) => {
  const n = Number(v)
  if (!isNaN(n) && n < 0) return 'gt-amount--negative'
  return ''
})

vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({
    fmtAmount: mockFmtAmount,
    amountClass: mockAmountClass,
  }),
}))

const baseColumns: WpDynamicColumn[] = [
  { key: 'name', label: '客户名称', minWidth: '120px' },
  { key: 'amount', label: '金额', isAmount: true, width: '120px' },
  { key: 'total', label: '合计', isAmount: true, autoCalc: true, tooltip: '自动汇总' },
]

const baseRows: DynamicRow[] = [
  { _id: 'r1', name: '客户A', amount: 10000, total: 10000 },
  { _id: 'r2', name: '客户B', amount: 20000, total: 20000 },
]

function mountTable(propsData: any) {
  return mount(WpDynamicTable, {
    props: propsData,
    global: {
      plugins: [ElementPlus],
    },
  })
}

beforeEach(() => {
  mockFmtAmount.mockClear()
  mockAmountClass.mockClear()
})

describe('WpDynamicTable', () => {
  describe('组件结构', () => {
    it('渲染根容器 .wp-dynamic-table', () => {
      const wrapper = mountTable({ columns: baseColumns, rows: baseRows })
      expect(wrapper.find('.wp-dynamic-table').exists()).toBe(true)
    })

    it('渲染合计行区域', () => {
      const wrapper = mountTable({
        columns: [{ key: 'amt', label: '金额', isAmount: true }],
        rows: [{ _id: 'r1', amt: 500 }],
      })
      expect(wrapper.find('.wp-dynamic-table__totals').exists()).toBe(true)
    })

    it('非只读模式渲染新增行按钮和行数统计', () => {
      const wrapper = mountTable({
        columns: baseColumns,
        rows: baseRows,
        readonly: false,
      })
      expect(wrapper.find('.wp-dynamic-table__footer').exists()).toBe(true)
      expect(wrapper.find('.wp-dynamic-table__row-count').text()).toContain('共 2 行')
    })

    it('只读模式不渲染 footer（无新增按钮）', () => {
      const wrapper = mountTable({
        columns: baseColumns,
        rows: baseRows,
        readonly: true,
      })
      expect(wrapper.find('.wp-dynamic-table__footer').exists()).toBe(false)
    })
  })

  describe('新增/删除行', () => {
    it('点击新增行按钮 emit update:rows 增加一行', async () => {
      const wrapper = mountTable({
        columns: [{ key: 'name', label: '名称' }],
        rows: [],
        readonly: false,
      })
      const addBtn = wrapper.find('.wp-dynamic-table__footer .el-button')
      await addBtn.trigger('click')
      const emitted = wrapper.emitted('update:rows')
      expect(emitted).toBeTruthy()
      expect(emitted![0][0]).toHaveLength(1)
      // 新增行应有 _id 和各列默认值
      const newRow = (emitted![0][0] as DynamicRow[])[0]
      expect(newRow._id).toBeTruthy()
      expect(newRow.name).toBe('')
    })

    it('只读模式下 addRow 不 emit', async () => {
      const wrapper = mountTable({
        columns: [{ key: 'name', label: '名称' }],
        rows: [],
        readonly: true,
      })
      // Footer doesn't exist in readonly
      expect(wrapper.find('.wp-dynamic-table__footer').exists()).toBe(false)
    })
  })

  describe('合计行计算逻辑', () => {
    it('金额列自动汇总', () => {
      const wrapper = mountTable({
        columns: [
          { key: 'name', label: '名称' },
          { key: 'amt', label: '金额', isAmount: true },
        ],
        rows: [
          { _id: 'r1', name: 'A', amt: 100 },
          { _id: 'r2', name: 'B', amt: 200 },
          { _id: 'r3', name: 'C', amt: 300 },
        ],
        readonly: true,
      })
      // Access computed totalsRow via vm
      const vm = wrapper.vm as any
      // mergedColumns accessible, totalsRow computed
      expect(vm.totalsRow.amt).toBe(600)
    })

    it('null 值不影响汇总', () => {
      const wrapper = mountTable({
        columns: [{ key: 'amt', label: '金额', isAmount: true }],
        rows: [
          { _id: 'r1', amt: 100 },
          { _id: 'r2', amt: null },
          { _id: 'r3', amt: 200 },
        ],
      })
      const vm = wrapper.vm as any
      expect(vm.totalsRow.amt).toBe(300)
    })

    it('非金额列合计为空字符串', () => {
      const wrapper = mountTable({
        columns: [
          { key: 'name', label: '名称' },
          { key: 'amt', label: '金额', isAmount: true },
        ],
        rows: [{ _id: 'r1', name: 'A', amt: 100 }],
      })
      const vm = wrapper.vm as any
      expect(vm.totalsRow.name).toBe('')
    })

    it('全部为 null 时合计为 null', () => {
      const wrapper = mountTable({
        columns: [{ key: 'amt', label: '金额', isAmount: true }],
        rows: [
          { _id: 'r1', amt: null },
          { _id: 'r2', amt: null },
        ],
      })
      const vm = wrapper.vm as any
      expect(vm.totalsRow.amt).toBeNull()
    })
  })

  describe('账龄动态列', () => {
    it('agingBands 追加为额外列（金额列）', () => {
      const agingBands: AgingBand[] = [
        { key: 'aging_0_1', label: '1年以内' },
        { key: 'aging_1_2', label: '1-2年' },
      ]
      const wrapper = mountTable({
        columns: [{ key: 'name', label: '客户' }],
        rows: [{ _id: 'r1', name: 'A', aging_0_1: 5000, aging_1_2: 2000 }],
        agingBands,
      })
      const vm = wrapper.vm as any
      // mergedColumns should have 3 columns (1 base + 2 aging)
      expect(vm.mergedColumns).toHaveLength(3)
      expect(vm.mergedColumns[1].key).toBe('aging_0_1')
      expect(vm.mergedColumns[1].label).toBe('1年以内')
      expect(vm.mergedColumns[1].isAmount).toBe(true)
      expect(vm.mergedColumns[2].key).toBe('aging_1_2')
    })

    it('无 agingBands 时列数不变', () => {
      const wrapper = mountTable({
        columns: baseColumns,
        rows: baseRows,
      })
      const vm = wrapper.vm as any
      expect(vm.mergedColumns).toHaveLength(baseColumns.length)
    })

    it('账龄列参与合计计算', () => {
      const agingBands: AgingBand[] = [
        { key: 'aging_a', label: '段A' },
      ]
      const wrapper = mountTable({
        columns: [{ key: 'name', label: '客户' }],
        rows: [
          { _id: 'r1', name: 'A', aging_a: 100 },
          { _id: 'r2', name: 'B', aging_a: 200 },
        ],
        agingBands,
      })
      const vm = wrapper.vm as any
      expect(vm.totalsRow.aging_a).toBe(300)
    })
  })

  describe('DisplayPrefs 集成', () => {
    it('formatAmount 调用 displayPrefs.fmtAmount', () => {
      const wrapper = mountTable({
        columns: [{ key: 'amt', label: '金额', isAmount: true }],
        rows: [{ _id: 'r1', amt: 99.99 }],
      })
      const vm = wrapper.vm as any
      const result = vm.formatAmount(12345)
      expect(mockFmtAmount).toHaveBeenCalledWith(12345)
      expect(result).toBe('12,345.00')
    })

    it('getAmountClass 调用 displayPrefs.amountClass', () => {
      const wrapper = mountTable({
        columns: [{ key: 'amt', label: '金额', isAmount: true }],
        rows: [{ _id: 'r1', amt: -100 }],
      })
      const vm = wrapper.vm as any
      const cls = vm.getAmountClass(-100)
      expect(mockAmountClass).toHaveBeenCalledWith(-100)
      expect(cls).toBe('gt-amount--negative')
    })
  })

  describe('removeRow', () => {
    it('调用 removeRow 后 emit 少一行的数组', () => {
      const wrapper = mountTable({
        columns: [{ key: 'name', label: '名称' }],
        rows: [{ _id: 'r1', name: 'A' }, { _id: 'r2', name: 'B' }, { _id: 'r3', name: 'C' }],
        readonly: false,
      })
      const vm = wrapper.vm as any
      vm.removeRow(1) // 删第二行
      const emitted = wrapper.emitted('update:rows')
      expect(emitted).toBeTruthy()
      const result = emitted![0][0] as DynamicRow[]
      expect(result).toHaveLength(2)
      expect(result[0]._id).toBe('r1')
      expect(result[1]._id).toBe('r3')
    })
  })

  describe('onCellChange', () => {
    it('调用 onCellChange 后 emit 更新后的行数据', () => {
      const wrapper = mountTable({
        columns: [{ key: 'name', label: '名称' }],
        rows: [{ _id: 'r1', name: 'old' }],
        readonly: false,
      })
      const vm = wrapper.vm as any
      vm.onCellChange(0, 'name', 'new')
      const emitted = wrapper.emitted('update:rows')
      expect(emitted).toBeTruthy()
      const result = emitted![0][0] as DynamicRow[]
      expect(result[0].name).toBe('new')
    })
  })
})
