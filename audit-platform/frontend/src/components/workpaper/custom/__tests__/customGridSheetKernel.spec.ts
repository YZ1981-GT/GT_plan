/**
 * 自定义底稿可编辑网格接表格内核（spec excel-style-table-editing 5.5）。
 *
 * 原状：原生 table + 自建双击编辑（editingRef，el-input 的 @keyup.enter / esc），单击只发 select-cell，
 * 没有方向键 / Tab / 直接输入 / 粘贴 / 撤销。现在：单击选中（方向键移动同样发 select-cell），
 * 双击 / 直接输入编辑，Enter 提交成脏格并防抖写回，Esc 取消；公式格 / 只读不可编辑。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'

const { put, msg } = vi.hoisted(() => ({
  put: vi.fn(),
  msg: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/apiProxy', () => ({ api: { put } }))
vi.mock('element-plus', async (importOriginal) => ({ ...(await importOriginal<Record<string, unknown>>()), ElMessage: msg }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmtAmount: (v: number) => v.toFixed(2), gridEditMode: 'excel' }),
}))

import ElementPlus from 'element-plus'
import GtCustomGridSheet from '../GtCustomGridSheet.vue'
import { activeInput, dblclick, key, mousedown, settle, typeInSink } from '@/components/grid/__tests__/gridHarness'

const GRID = {
  cells: {
    A1: { v: '项目', r: 1, c: 1 }, B1: { v: '金额', r: 1, c: 2 },
    A2: { v: '现金', r: 2, c: 1 }, B2: { v: 100, r: 2, c: 2, style: { numeric: true } },
    A3: { v: '合计', r: 3, c: 1 }, B3: { v: 100, r: 3, c: 2, style: { numeric: true } },
  },
  max_row: 3,
  max_col: 2,
}

const live: VueWrapper[] = []
afterEach(() => {
  while (live.length) live.pop()!.unmount()
  document.body.innerHTML = ''
})
beforeEach(() => {
  put.mockReset()
  put.mockResolvedValue({ updated: 1 })
  Object.values(msg).forEach((f) => f.mockReset())
})

async function grid(props: Record<string, unknown> = {}) {
  const w = mount(GtCustomGridSheet, {
    props: { wpId: 'wp1', sheetName: 'Sheet1', htmlData: GRID, formulaCells: { B3: 'SUM(B2:B2)' }, debounceMs: 0, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  live.push(w)
  await settle()
  const td = (ref: string) => w.element.querySelector(`td[data-cell="${ref}"]`) as HTMLTableCellElement
  const sink = () => w.element.querySelector('.gt-grid-sink') as HTMLTextAreaElement
  return { w, td, sink }
}
const flushTimers = () => new Promise((r) => setTimeout(r, 10))

describe('GtCustomGridSheet 接内核', () => {
  it('平时无输入框；单击选中发 select-cell，方向键移动同样发，同一格不重复发', async () => {
    const { w, td, sink } = await grid()
    expect(w.element.querySelectorAll('input').length).toBe(0)
    expect(td('B2').textContent).toContain('100.00')
    mousedown(td('A2'))
    td('A2').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    key(sink(), 'ArrowRight')
    await settle()
    mousedown(td('B2'))
    await settle()
    expect(w.emitted('select-cell')).toEqual([['A2'], ['B2']])
  })

  it('双击编辑：输入框是原数（不带千分位），Enter 提交成脏格并防抖写回 xlsx 坐标', async () => {
    const { w, td } = await grid({ debounceMs: 60 })
    dblclick(td('B2'))
    await settle()
    const inp = activeInput(w)
    expect(inp.value).toBe('100')
    inp.value = '150'
    inp.dispatchEvent(new Event('input', { bubbles: true }))
    key(inp, 'Enter')
    await settle()
    expect(w.find('.gt-cgs__statusbar').text()).toContain('1 处待保存')
    expect(td('B2').textContent).toContain('150')
    expect(put).not.toHaveBeenCalled()
    await new Promise((r) => setTimeout(r, 100))
    await settle()
    expect(put).toHaveBeenCalledWith('/api/workpapers/wp1/custom-cells', { sheet_name: 'Sheet1', updates: { B2: '150' } })
  })

  it('直接输入开始编辑；Esc 取消不产生脏格；改回原值也不产生脏格', async () => {
    const { w, td, sink } = await grid()
    mousedown(td('A2'))
    await settle()
    typeInSink(sink(), '银')
    await settle()
    expect(activeInput(w).value).toBe('银')
    key(activeInput(w), 'Escape')
    await settle()
    expect(td('A2').textContent).toContain('现金')
    dblclick(td('A2'))
    await settle()
    key(activeInput(w), 'Enter') // 没改
    await settle()
    await flushTimers()
    expect(w.find('.gt-cgs__statusbar').exists()).toBe(false)
    expect(put).not.toHaveBeenCalled()
  })

  it('公式格双击不进编辑并说明原因；只读时任何格都不进编辑', async () => {
    const { w, td } = await grid()
    dblclick(td('B3'))
    await settle()
    expect(w.element.querySelectorAll('input').length).toBe(0)
    expect(msg.info).toHaveBeenCalledWith(expect.stringContaining('由公式计算'))

    const ro = await grid({ readonly: true })
    dblclick(ro.td('B2'))
    await settle()
    expect(ro.w.element.querySelectorAll('input').length).toBe(0)
  })
})
