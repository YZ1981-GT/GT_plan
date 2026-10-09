/**
 * 报表差额表（任务 12.1 / 需求 5）：同一报表行按直接子节点展开，差额列可穿透。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const { api, exportMultiSheetData, message } = vi.hoisted(() => ({
  api: {
    getConsolReportBreakdown: vi.fn(),
    drillConsolRowEntries: vi.fn(),
  } as Record<string, ReturnType<typeof vi.fn>>,
  exportMultiSheetData: vi.fn(),
  message: { success: vi.fn() },
}))
vi.mock('@/services/consolidationApi', () => Object.fromEntries(
  Object.keys(api).map((key) => [key, (...args: any[]) => api[key](...args)]),
))
vi.mock('@/composables/useExcelIO', () => ({ exportMultiSheetData }))
vi.mock('element-plus', () => ({ ElMessage: message }))

import ConsolReportBreakdownView from '../ConsolReportBreakdownView.vue'
import {
  breakdownCell,
  breakdownCheck,
  breakdownExportAoa,
  breakdownTotal,
} from '../composables/consolReportBreakdown'
import type {
  ConsolBreakdownColumn,
  ConsolReportBreakdownRow,
  ConsolTreeNode,
} from '@/services/consolidationApi'

const COLS: ConsolBreakdownColumn[] = [
  { node_key: 'G:parent', label: '母公司', kind: 'data', role: 'parent', company_code: 'G' },
  { node_key: 'G:consol_elim', label: '合并差额', kind: 'elim', role: 'consol_elim', company_code: 'G' },
  { node_key: 'A:consol', label: 'A（合并）', kind: 'aggregate', role: 'consol', company_code: 'A' },
]
function row(code: string, extra: Partial<ConsolReportBreakdownRow> = {}): ConsolReportBreakdownRow {
  return {
    row_code: code, row_name: `行${code}`, row_number: 1, indent_level: 0,
    is_total_row: false, has_formula: true,
    cells: { 'G:parent': '100.00', 'G:consol_elim': '-20.00', 'A:consol': '30.00' },
    total: '110.00', linear: true, note: null, ...extra,
  }
}

const ROWS = [
  row('BS-000', { row_name: '流动资产：', has_formula: false, total: '0.00' }),
  row('BS-002'),
  row('BS-003', { cells: { 'G:parent': '10.00', 'G:consol_elim': '2.00', 'A:consol': '3.00' }, total: '14.99' }),
  row('BS-004', { cells: { 'G:parent': null, 'G:consol_elim': null, 'A:consol': null }, total: '9.00', linear: false, note: '公式非线性，只给合计，不按子节点分解' }),
  row('BS-005', { cells: { 'G:parent': '5.00', 'G:consol_elim': null, 'A:consol': '4.00' }, total: '9.00', note: '差额列取不到数' }),
]

function treeNode(key: string, kind: ConsolTreeNode['kind'], children: ConsolTreeNode[] = []): ConsolTreeNode {
  const [code, role] = key.split(':') as [string, ConsolTreeNode['role']]
  return {
    project_id: null, company_code: code, company_name: code, parent_company_code: null,
    ultimate_company_code: null, consol_level: 1, children, node_key: key, role, kind,
    display_name: `${code}（${role}）`, relation: null, host_project_id: null,
    flags: [], via: [], mode: null,
  }
}
const TREE = treeNode('G:consol', 'aggregate', [
  treeNode('G:parent', 'data'), treeNode('G:consol_elim', 'elim'),
  treeNode('A:consol', 'aggregate', [treeNode('A:parent', 'data')]),
])

function response(nodeKey = 'G:consol') {
  return {
    year: 2025, applicable_standard: 'soe_consolidated',
    aggregate_nodes: [{ node_key: 'G:consol', label: 'G（合并）', role: 'consol' }, { node_key: 'A:consol', label: 'A（合并）', role: 'consol' }],
    node_key: nodeKey, node_label: nodeKey === 'A:consol' ? 'A（合并）' : 'G（合并）',
    report_type: 'balance_sheet', columns: COLS, rows: ROWS,
  }
}
const Table = defineComponent({
  props: ['data'],
  provide() { return { rows: () => (this as any).data || [] } },
  setup(_, { slots, attrs }) {
    return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, slots.default?.())
  },
})
const Column = defineComponent({
  inject: ['rows'],
  props: ['label', 'className', 'labelClassName'],
  setup(props, { slots }) {
    return function (this: any) {
      return h('section', { 'data-label': props.label, class: props.className }, [
        slots.header?.(),
        ...this.rows().map((r: any) => h('div', slots.default?.({ row: r }))),
      ])
    }
  },
})
const Button = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit, attrs }) {
    return () => h('button', { 'data-testid': (attrs as any)['data-testid'], onClick: () => emit('click') }, slots.default?.())
  },
})
const Amount = defineComponent({
  props: ['value', 'clickable'], emits: ['click'],
  setup(props, { emit }) {
    return () => h('span', { class: 'amt', onClick: () => emit('click') }, String(props.value ?? ''))
  },
})
const Pass = defineComponent({
  setup(_, { slots, attrs }) {
    return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, [slots.default?.(), slots.title?.()])
  },
})
const Dialog = defineComponent({
  props: ['modelValue'],
  setup(props, { slots, attrs }) {
    return () => props.modelValue ? h('div', { 'data-testid': (attrs as any)['data-testid'] }, slots.default?.()) : null
  },
})
const Select = defineComponent({
  emits: ['change'],
  setup(_, { slots, attrs }) {
    return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, slots.default?.())
  },
})
const Option = defineComponent({
  props: ['label', 'value'],
  setup(props) { return () => h('i', { 'data-value': props.value }, props.label) },
})
const STUBS = {
  'el-table': Table, 'el-table-column': Column, 'el-button': Button,
  'el-select': Select, 'el-option': Option, 'el-tooltip': Pass, 'el-alert': Pass,
  'el-empty': true, 'el-dialog': Dialog, GtAmountCell: Amount,
}

function mountView(props: Record<string, unknown> = {}) {
  return mount(ConsolReportBreakdownView, {
    props: { projectId: 'p-g', year: 2025, reportType: 'balance_sheet', tree: TREE, ...props },
    global: { stubs: STUBS, directives: { loading: {} } },
  })
}

describe('consolReportBreakdown 纯逻辑', () => {
  it('标题行留空；线性行按 Decimal 核对；非线性与取不到数分开计数', () => {
    expect(breakdownCell(ROWS[0], 'G:parent')).toBeNull()
    expect(breakdownTotal(ROWS[0])).toBeNull()
    expect(breakdownCell(ROWS[1], 'G:consol_elim')).toBe('-20.00')
    const check = breakdownCheck(ROWS, COLS)
    expect(check).toMatchObject({ checked: 2, nonlinear: 1, blank: 1 })
    expect(check.mismatched).toEqual([{
      row_code: 'BS-003', row_name: '行BS-003', sum: '15', total: '14.99', difference: '0.01',
    }])
  })

  it('导出保留子节点顺序、标明差额列，金额为数字，标题行为空', () => {
    const aoa = breakdownExportAoa(ROWS, COLS)
    expect(aoa[0]).toEqual(['行次', '项目', '母公司', '合并差额（差额）', 'A（合并）', '合计', '说明'])
    expect(aoa[1].slice(2, 6)).toEqual([null, null, null, null])
    expect(aoa[2].slice(2, 6)).toEqual([100, -20, 30, 110])
  })
})
describe('ConsolReportBreakdownView', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    exportMultiSheetData.mockReset()
    message.success.mockReset()
    api.getConsolReportBreakdown.mockImplementation((_pid: string, opts: any) => Promise.resolve(response(opts.nodeKey || 'G:consol')))
    api.drillConsolRowEntries.mockResolvedValue({
      decomposable: true, total: '-20.00', note: null,
      lines: [{ entry_id: 'e', entry_no: 'IA-1', entry_type: 'internal_ar_ap', node_key: 'G:consol_elim', node_label: '合并差额', account_code: '1122', account_name: '应收账款', debit: '0.00', credit: '20.00', contribution: '-20.00' }],
    })
  })

  async function loaded() {
    const wrapper = mountView()
    ;(wrapper.vm as any).load()
    await flushPromises()
    return wrapper
  }

  it('默认根节点；按树列出汇总节点；差额列浅黄标识；显示各子节点与合计', async () => {
    const wrapper = await loaded()
    expect(api.getConsolReportBreakdown).toHaveBeenCalledWith('p-g', {
      reportType: 'balance_sheet', nodeKey: null, year: 2025,
    })
    expect(wrapper.findAll('[data-testid="crb-node"] i').map((n) => n.attributes('data-value'))).toEqual(['G:consol', 'A:consol'])
    expect(wrapper.find('[data-testid="crb-head-G:consol_elim"]').text()).toContain('差额')
    expect(wrapper.find('[data-testid="crb-cell-BS-002-G:consol_elim"]').text()).toBe('-20.00')
    expect(wrapper.find('[data-testid="crb-total-BS-002"]').text()).toBe('110.00')
    expect(wrapper.find('[data-testid="crb-total-BS-000"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="crb-check"]').text()).toContain('1 行各列之和 ≠ 合计')
  })

  it('差额列穿透已审批分录；下级汇总列从表头展开为该节点差额表', async () => {
    const wrapper = await loaded()
    await wrapper.find('[data-testid="crb-cell-BS-002-G:consol_elim"] .amt').trigger('click')
    await flushPromises()
    expect(api.drillConsolRowEntries).toHaveBeenCalledWith('p-g', {
      rowCode: 'BS-002', measure: 'consolidated', nodeKey: 'G:consol_elim', year: 2025,
    })
    expect(wrapper.find('[data-testid="crb-drill-entries"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="crb-drill-total"]').text()).toContain('-20.00')

    await wrapper.find('[data-testid="crb-dive-A:consol"]').trigger('click')
    await flushPromises()
    expect(api.getConsolReportBreakdown).toHaveBeenLastCalledWith('p-g', {
      reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2025,
    })
  })

  it('已打开后切换报表类型自动重读；导出使用当前节点和报表类型', async () => {
    const wrapper = await loaded()
    await wrapper.setProps({ reportType: 'income_statement' })
    await flushPromises()
    expect(api.getConsolReportBreakdown).toHaveBeenLastCalledWith('p-g', {
      reportType: 'income_statement', nodeKey: 'G:consol', year: 2025,
    })
    await wrapper.find('[data-testid="crb-export"]').trigger('click')
    await flushPromises()
    expect(exportMultiSheetData).toHaveBeenCalledWith(expect.objectContaining({
      fileName: expect.stringContaining('利润表'), applyStyles: false, successMessage: false,
    }))
    expect(message.success).toHaveBeenCalledWith('已导出')
  })

  it('未打开过不请求；加载失败显示后端原因', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(api.getConsolReportBreakdown).not.toHaveBeenCalled()
    api.getConsolReportBreakdown.mockRejectedValueOnce({ response: { data: { detail: '不是汇总节点' } } })
    ;(wrapper.vm as any).load()
    await flushPromises()
    expect(wrapper.find('[data-testid="crb-error"]').exists()).toBe(true)
  })
})
