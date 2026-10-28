/**
 * spec excel-style-table-editing 5.2：GtEditableTable 去掉自带懒编辑 / 键盘，内置编辑器改用适配组件。
 * - 原先 `:is="'el-input-number'"` 字符串在应用里解析不到（没有全局注册 Element 组件），内置编辑器从未渲染成输入框；
 * - 校验（validator）原先只挂在懒编辑的 blur 上，直接编辑模式从不校验 —— 现在提交（change）时校验。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount, shallowMount, type VueWrapper } from '@vue/test-utils'
import { ElButton, ElOption, ElTable, ElTableColumn, ElTooltip, ElButtonGroup } from 'element-plus/es'
import GtEditableTable from '@/components/common/GtEditableTable.vue'
import GtFormTable from '@/components/common/GtFormTable.vue'
import GtTableExtended from '@/components/common/GtTableExtended.vue'
import { useKeyboardNav } from '@/composables/useKeyboardNav'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { markGridInstalled } from '../GridKernel'
import { gridTableMixin } from '../plugin'
import { key, mousedown, settle, settleFrames, typeInSink } from './gridHarness'

const live: VueWrapper[] = []
afterEach(() => {
  while (live.length) live.pop()!.unmount()
  document.body.innerHTML = ''
  markGridInstalled(false)
})

const columns = [
  { prop: 'name', label: '项目', editType: 'input' as const },
  { prop: 'amt', label: '金额', editType: 'number' as const, validator: { max: 1000, message: '金额不能大于 1000' } },
  { prop: 'kind', label: '类型', editType: 'select' as const, editOptions: [{ label: '收入', value: 'in' }, { label: '支出', value: 'out' }] },
]

async function mountTable() {
  markGridInstalled(true)
  const rows = [{ name: '甲', amt: 10, kind: 'in' }, { name: '乙', amt: 20, kind: 'out' }]
  const w = mount(GtEditableTable, {
    attachTo: document.body,
    props: { modelValue: rows, columns, editable: true, showToolbar: true, showFooter: false },
    global: { mixins: [gridTableMixin], components: { ElTable, ElTableColumn, ElOption, ElButton, ElTooltip, ElButtonGroup } },
  })
  live.push(w)
  const vm = w.vm as unknown as { editMode: { enterEdit: () => void; isDirty: { value: boolean } } }
  vm.editMode.enterEdit()
  await settleFrames()
  // 组件根是 <Teleport>（全屏时搬到 body），wrapper.element 不是元素：从容器取
  const root = () => document.querySelector('.gt-editable-table') as HTMLElement
  const td = (r: number, c: number) => (root().querySelectorAll('tbody tr.el-table__row')[r] as HTMLTableRowElement).cells[c]
  const sinkEl = () => root().querySelector('.gt-grid-sink') as HTMLTextAreaElement
  const editorInput = () => root().querySelector('td[data-gt-editing] input') as HTMLInputElement
  return { w, rows, vm, root, td, sinkEl, editorInput }
}

describe('GtEditableTable 内置编辑器（Excel 方式）', () => {
  it('平时只显示文字（下拉显示选项名称），F2 才挂真的输入框；回车提交写回、标脏', async () => {
    const { rows, vm, root, td, sinkEl, editorInput } = await mountTable()
    expect(root().querySelectorAll('tbody input').length).toBe(0)
    expect(td(0, 1).textContent?.trim()).toBe('10.00')
    expect(td(0, 2).textContent?.trim()).toBe('收入')
    mousedown(td(0, 1))
    key(sinkEl(), 'F2')
    await settle()
    const input = editorInput()
    expect(input?.tagName).toBe('INPUT') // 原先字符串组件名解析不到，渲染成 <el-input-number> 空元素
    input.value = '88'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    key(input, 'Enter')
    await settle()
    expect(rows[0].amt).toBe(88)
    expect(vm.editMode.isDirty.value).toBe(true)
    expect(td(1, 1).hasAttribute('data-gt-active')).toBe(true)
  })

  it('打字中途 Esc 取消：值还原、不标脏（不再弹「有未保存的修改」）', async () => {
    const { rows, vm, td, sinkEl, editorInput } = await mountTable()
    mousedown(td(0, 1))
    key(sinkEl(), 'F2')
    await settle()
    const input = editorInput()
    input.value = '77'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    key(input, 'Escape')
    await settle()
    expect(rows[0].amt).toBe(10)
    expect(vm.editMode.isDirty.value).toBe(false)
  })

  it('提交时按 validator 校验（超上限夹到上限并提示）', async () => {
    const { rows, td, sinkEl } = await mountTable()
    mousedown(td(1, 1))
    typeInSink(sinkEl(), '5000')
    await settle()
    key(document.activeElement as Element, 'Enter')
    await settleFrames()
    expect(rows[1].amt).toBe(1000)
    expect(document.body.textContent).toContain('金额不能大于 1000')
  })

  it('经典方式：输入框常驻（与改造前一致）', async () => {
    const { root } = await mountTable()
    useDisplayPrefsStore().gridEditMode = 'classic'
    await settleFrames()
    expect(root().querySelectorAll('tbody input').length).toBeGreaterThanOrEqual(4)
  })
})

describe('GtFormTable / GtTableExtended 布尔默认值', () => {
  it('不传时与 GtEditableTable 默认一致（原先未传的布尔 prop 以 false 传下去，盖掉工具栏 / 底栏 / 排序）', () => {
    for (const Comp of [GtFormTable, GtTableExtended]) {
      // 两个组件的 props 类型不同，循环里按无类型挂载（只断言内层 GtEditableTable 收到的默认值）
      const w = shallowMount(Comp as any, { props: { modelValue: [], columns: [] } })
      const inner = w.findComponent({ name: 'GtEditableTable' })
      expect(inner.props('showToolbar')).toBe(true)
      expect(inner.props('showFooter')).toBe(true)
      expect(inner.props('defaultSortable')).toBe(true)
      expect(inner.props('showSummary')).toBe(false)
      w.unmount()
    }
  })
})

describe('useKeyboardNav 让位给表格内核', () => {
  it('enabled 返回 false 时不处理按键', async () => {
    const selectCell = vi.fn()
    let on = false
    const el = document.createElement('div')
    document.body.appendChild(el)
    const nav = useKeyboardNav({
      containerRef: { value: el } as never, enabled: () => on,
      rowCount: () => 3, colCount: () => 3, getSelection: () => [0, 0], selectCell,
    })
    const down = () => {
      const ev = new KeyboardEvent('keydown', { key: 'ArrowDown', cancelable: true })
      Object.defineProperty(ev, 'target', { value: el })
      return ev
    }
    nav.handleKeyDown(down())
    expect(selectCell).not.toHaveBeenCalled()
    on = true
    nav.handleKeyDown(down())
    expect(selectCell).toHaveBeenCalledWith(1, 0)
    await nextTick()
  })
})
