/**
 * SheetCellRangePicker.year.spec.ts — 底稿选区器的年度由父组件传入（advanced-query-linkage-closure 任务 28；R10.2）
 *
 * 选区确认后按年度取数（查询端点 year 必填）：父组件（高级查询弹窗）没给年度时不预览、提示「请先选择审计年度」，
 * 不按日历年推算（变异 B10-l：去掉年度判断 ⇒ 无年度也发预览请求）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))

import ElementPlus from 'element-plus'
import SheetCellRangePicker from '../SheetCellRangePicker.vue'

let wrapper: VueWrapper<any> | null = null
async function mountPicker(year: number | null | undefined) {
  // 与弹窗里的用法一致：先挂载（关闭），点 sheet 叶子时再打开 ⇒ 打开时加载
  wrapper = mount(SheetCellRangePicker, {
    props: { modelValue: false, wpCode: 'D2', sheetName: '审定表', projectId: 'p1', year },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  }) as unknown as VueWrapper<any>
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  return wrapper
}
const previewCalls = () => apiMocks.get.mock.calls.filter((c) => c[0] === '/api/custom-query/wp-sheet-preview')

beforeEach(() => {
  localStorage.clear()
  apiMocks.get.mockReset().mockResolvedValue({ available: true, cells: {}, rows: 1, cols: 1, all_sheets: ['审定表'], sheet_name: '审定表' })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('SheetCellRangePicker 年度', () => {
  it.each([undefined, null])('父组件没给年度（%s）：不预览，提示「请先选择审计年度」', async (year) => {
    await mountPicker(year)
    expect(previewCalls()).toHaveLength(0)
    expect(document.body.querySelector('.gt-sheet-picker-hint')?.textContent).toContain('请先选择审计年度')
  })

  it('给了年度：照常加载底稿预览', async () => {
    await mountPicker(2025)
    expect(previewCalls()).toHaveLength(1)
    expect(previewCalls()[0][1]).toMatchObject({ params: { project_id: 'p1', wp_code: 'D2', sheet_name: '审定表' } })
  })
})
