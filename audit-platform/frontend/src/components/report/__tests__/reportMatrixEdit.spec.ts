/**
 * spec excel-style-table-editing 5.4：报表权益变动表 / 资产减值准备表格内编辑（替换原先的双击弹输入框）。
 *
 * - 金额格平时只显示文字，可编辑格双击才挂输入框，提交发 cell-edit（列键与 `/reports/cell` 一致）；
 * - 权益表：`cy:` / `py:` + 前端列键，三级表头（其他权益工具 > 优先股）下的格同样可改；分类行、合计行不可改；
 * - 减值表：本期增减各列用导出模板 `{{imp:CODE:列键}}` 的列键，值取 source_accounts[列键]（原先恒显示 0）；
 *   两个「合计」按本组求和、不可改，年初 / 期末只读；
 * - 提交后到下次取数前先显示刚填的值，重新取数（rows 换新）后以服务器为准。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { VueWrapper } from '@vue/test-utils'
import { equitySpanMethod } from '@/views/composables/useReportColumns'
import { activeInput, cell, click, dblclick, key, mountGrid, settle, unmountAll } from '@/components/grid/__tests__/gridHarness'
import ReportEquityTable from '../ReportEquityTable.vue'
import ReportImpairmentTable from '../ReportImpairmentTable.vue'

afterEach(() => unmountAll())

const INC = [
  { key: 'provision', label: '本期计提额' },
  { key: 'merge_increase', label: '合并增加额' },
  { key: 'other_increase', label: '其他原因增加额' },
  { key: 'subtotal_increase', label: '合计', sum: true },
]
const DEC = [
  { key: 'reversal', label: '转回额' },
  { key: 'write_off', label: '转销额' },
  { key: 'merge_decrease', label: '合并减少额' },
  { key: 'other_decrease', label: '其他原因减少额' },
  { key: 'subtotal_decrease', label: '合计', sum: true },
]

function impRows() {
  return [
    { row_code: 'IMP-001', row_name: '坏账准备', prior_period_amount: '100', current_period_amount: '130', source_accounts: { provision: 40, reversal: 10 }, indent_level: 1, is_total_row: false },
    { row_code: 'IMP-099', row_name: '合计', prior_period_amount: '100', current_period_amount: '130', source_accounts: ['1231'], indent_level: 0, is_total_row: true },
  ]
}

async function impairment(editable = true) {
  const onEdit = vi.fn()
  const w = await mountGrid(
    `<report-impairment-table :rows="rows" :imp-inc-cols="inc" :imp-dec-cols="dec" :table-max-height="600"
       :cell-class-name="noop" font-size="14px" :imp-row-class-name="noop" :editable="editable" @cell-edit="onEdit" />`,
    () => ({ rows: impRows(), inc: INC, dec: DEC, editable }),
    { noop: () => '', onEdit } as never,
    { ReportImpairmentTable },
  )
  return { w, onEdit, vm: w.vm as unknown as { rows: ReturnType<typeof impRows> } }
}

const text = (w: VueWrapper, r: number, c: number) => cell(w, r, c).textContent?.trim()
const editing = (w: VueWrapper) => w.element.querySelector('td[data-gt-editing]')

async function typeAndEnter(w: VueWrapper, r: number, c: number, value: string) {
  click(cell(w, r, c))
  dblclick(cell(w, r, c))
  await settle()
  const input = activeInput(w)
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  key(input, 'Enter')
  await settle()
}

describe('资产减值准备表', () => {
  // 叶子列：0 项目 / 1 年初 / 2~5 增加（计提、合并、其他、合计）/ 6~10 减少（转回、转销、合并、其他、合计）/ 11 期末
  it('值取 source_accounts[列键]，合计按本组求和，年初 / 期末取金额；平时不挂输入框', async () => {
    const { w } = await impairment()
    expect(text(w, 0, 1)).toBe('100.00')
    expect(text(w, 0, 2)).toBe('40.00')
    expect(text(w, 0, 5)).toBe('40.00')
    expect(text(w, 0, 6)).toBe('10.00')
    expect(text(w, 0, 10)).toBe('10.00')
    expect(text(w, 0, 11)).toBe('130.00')
    expect(w.element.querySelectorAll('table.el-table__body input').length).toBe(0)
  })

  it('没填的格显示「-」，双击编辑时输入框为空（不显示一个 0 让人接着打成 099）', async () => {
    const { w } = await impairment()
    expect(text(w, 0, 4)).toBe('-')
    click(cell(w, 0, 4))
    dblclick(cell(w, 0, 4))
    await settle()
    expect(activeInput(w).value).toBe('')
  })

  it('双击本期增减格编辑，回车提交：发 cell-edit（导出列键）、先显示新值、合计跟着变', async () => {
    const { w, onEdit, vm } = await impairment()
    await typeAndEnter(w, 0, 3, '25')
    expect(onEdit).toHaveBeenCalledTimes(1)
    expect(onEdit).toHaveBeenCalledWith(vm.rows[0], 'merge_increase', 25)
    expect(text(w, 0, 3)).toBe('25.00')
    expect(text(w, 0, 5)).toBe('65.00')
    expect(editing(w)).toBeNull()
  })

  it('合计列、年初 / 期末、合计行不可编辑；未开编辑（未审模式）整表只读', async () => {
    const { w, onEdit } = await impairment()
    for (const [r, c] of [[0, 5], [0, 10], [0, 1], [0, 11], [1, 2]]) {
      click(cell(w, r, c))
      dblclick(cell(w, r, c))
      await settle()
      expect(editing(w), `第 ${r} 行第 ${c} 列`).toBeNull()
    }
    expect(onEdit).not.toHaveBeenCalled()
    unmountAll()
    const ro = await impairment(false)
    click(cell(ro.w, 0, 2))
    dblclick(cell(ro.w, 0, 2))
    await settle()
    expect(editing(ro.w)).toBeNull()
  })

  it('重新取数（rows 换新）后以服务器的值为准', async () => {
    const { w, vm } = await impairment()
    await typeAndEnter(w, 0, 2, '50')
    expect(text(w, 0, 2)).toBe('50.00')
    const next = impRows()
    next[0].source_accounts = { provision: 41, reversal: 10 }
    vm.rows = next
    await settle()
    expect(text(w, 0, 2)).toBe('41.00')
  })
})

function eqRows() {
  return [
    { row_code: 'EQ-000', row_name: '一、本年年初余额', indent_level: 0, is_total_row: false },
    { row_code: 'EQ-005', row_name: '综合收益总额', indent_level: 1, is_total_row: false,
      source_accounts: { eq_matrix: { current_year: { other_equity_preferred: 7 }, prior_year: { paid_in_capital: 3 } } } },
    { row_code: 'EQ-099', row_name: '四、本年年末余额', indent_level: 0, is_total_row: true },
    { row_code: 'EQ-040', row_name: '小计', indent_level: 1, is_total_row: true },
  ]
}

async function equity(editable = true) {
  const onEdit = vi.fn()
  const eqCellVal = (row: any, k: string, yk = 'current_year') => row.source_accounts?.eq_matrix?.[yk]?.[k] ?? 0
  const w = await mountGrid(
    `<report-equity-table :rows="rows" :eq-columns="[]" :eq-total-cols="12" :table-max-height="600" :cell-class-name="noop"
       font-size="14px" :equity-span-method="span" :eq-row-class-name="noop" :eq-cell-val="val" :is-consolidated="false"
       :editable="editable" @cell-edit="onEdit" />`,
    () => ({ rows: eqRows(), editable }),
    { noop: () => '', onEdit, span: (p: any) => equitySpanMethod(p, 12), val: eqCellVal } as never,
    { ReportEquityTable },
  )
  return { w, onEdit, vm: w.vm as unknown as { rows: ReturnType<typeof eqRows> } }
}

describe('所有者权益变动表', () => {
  // 叶子列：0 项目 / 1~12 本年（实收资本、优先股、永续债、其他、资本公积…、合计）/ 13~24 上年
  it('三级表头下的格（本年 > 其他权益工具 > 优先股）双击编辑，提交发 cy: 列键', async () => {
    const { w, onEdit, vm } = await equity()
    expect(text(w, 1, 2)).toBe('7.00')
    await typeAndEnter(w, 1, 2, '9')
    expect(onEdit).toHaveBeenCalledWith(vm.rows[1], 'cy:other_equity_preferred', 9, 'current_year')
    expect(text(w, 1, 2)).toBe('9.00')
  })

  it('上年列提交发 py: 列键；清空发 null', async () => {
    const { w, onEdit, vm } = await equity()
    expect(text(w, 1, 13)).toBe('3.00')
    await typeAndEnter(w, 1, 13, '')
    expect(onEdit).toHaveBeenCalledWith(vm.rows[1], 'py:paid_in_capital', null, 'prior_year')
  })

  it('分类行合并成整行标题、合计行（含缩进的小计）不可编辑；未开编辑整表只读', async () => {
    const { w, onEdit } = await equity()
    expect(cell(w, 0, 0).colSpan).toBe(25)
    for (const r of [2, 3]) {
      click(cell(w, r, 1))
      dblclick(cell(w, r, 1))
      await settle()
      expect(editing(w), `第 ${r} 行`).toBeNull()
    }
    expect(onEdit).not.toHaveBeenCalled()
    unmountAll()
    const ro = await equity(false)
    click(cell(ro.w, 1, 1))
    dblclick(cell(ro.w, 1, 1))
    await settle()
    expect(editing(ro.w)).toBeNull()
  })
})
