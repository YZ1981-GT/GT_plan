/**
 * spec excel-style-table-editing 5.1 / R10.2：useCellSelection 改为表格内核的门面。
 * 表格按 Excel 方式工作时选区以内核为准（不出现两套选中框）；经典方式走原实现。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { useCellSelection } from '@/composables/useCellSelection'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { kernelForElement, markGridInstalled } from '../GridKernel'
import { gridTableMixin } from '../plugin'
import { click, gridComponents, key, settleFrames, sink, unmountAll } from './gridHarness'

type Ctx = ReturnType<typeof useCellSelection>

const TABLE = (refName: string, rows: string, cls = '') => `
  <el-table ref="${refName}" :data="${rows}" :cell-class-name="${cls || 'ctxA.cellClassName'}">
    <el-table-column label="科目" prop="name" />
    <el-table-column label="金额"><template #default="{ row }"><gt-amount-cell :value="row.amt" /></template></el-table-column>
    <el-table-column label="说明"><template #default="{ row }">{{ row.note }}</template></el-table-column>
  </el-table>`

const live: VueWrapper[] = []

async function mountHost(opts: { bindB?: boolean; follow?: boolean } = {}) {
  let exposed!: { ctxA: Ctx; ctxB: Ctx; ctxFree: Ctx }
  const Host = defineComponent({
    components: { ...gridComponents, GtAmountCell },
    template: `<div>
      <div class="a">${TABLE('tA', 'rowsA')}</div>
      <div class="b">${TABLE('tB', 'rowsB', 'ctxB.cellClassName')}</div>
    </div>`,
    setup() {
      const tA = ref<unknown>(null)
      const tB = ref<unknown>(null)
      const ctxA = useCellSelection()
      const ctxB = useCellSelection()
      const ctxFree = useCellSelection()
      ctxA.setupTableDrag(tA as never, () => null)
      if (opts.bindB !== false) ctxB.setupTableDrag(tB as never, () => null)
      if (opts.follow) ctxA.followTables(() => [tB.value])
      exposed = { ctxA, ctxB, ctxFree }
      return {
        tA, tB, ctxA, ctxB, ctxFree,
        rowsA: [{ name: '货币资金', amt: 1234567.5, note: '甲' }, { name: '应收账款', amt: 20000, note: '乙' }],
        rowsB: [{ name: '存货', amt: 300, note: '丙' }],
      }
    },
  })
  const w = mount(Host, { attachTo: document.body, global: { mixins: [gridTableMixin] } })
  live.push(w)
  await settleFrames()
  const tdA = (r: number, c: number) => (w.element.querySelectorAll('.a tbody tr.el-table__row')[r] as HTMLTableRowElement).cells[c]
  const tdB = (r: number, c: number) => (w.element.querySelectorAll('.b tbody tr.el-table__row')[r] as HTMLTableRowElement).cells[c]
  return { w, ...exposed, tdA, tdB }
}

beforeEach(() => markGridInstalled(true))
afterEach(() => {
  while (live.length) live.pop()!.unmount()
  unmountAll()
  markGridInstalled(false)
})

describe('表格内核接管（Excel 方式）', () => {
  it('选区读内核：坐标为可见行 / 叶子列，金额取 data-gt-value 原值（不受「万元」显示影响）', async () => {
    useDisplayPrefsStore().setUnit('wan')
    const { w, ctxA, tdA } = await mountHost()
    click(tdA(0, 1))
    key(sink(w), 'ArrowDown', { shiftKey: true })
    await settleFrames()
    expect(tdA(0, 1).textContent?.trim()).toBe('123.46')
    expect(ctxA.selectedCells.value).toEqual([
      { row: 0, col: 1, value: 1234567.5 },
      { row: 1, col: 1, value: 20000 },
    ])
    expect(ctxA.sumSelectedValues()).toBe(1254567.5)
    expect(ctxA.selectionStats()).toMatchObject({ count: 2, numCount: 2, sum: 1254567.5 })
    expect(ctxA.isCellSelected(1, 1)).toBe(true)
    expect(ctxA.isCellSelected(0, 0)).toBe(false)
  })

  it('不出第二套选中框：cellClassName 返回空、页面 cell-click 里的 selectCell 不改内核选区', async () => {
    const { w, ctxA, tdA } = await mountHost()
    click(tdA(1, 2))
    await settleFrames()
    ctxA.selectCell(0, 0, '货币资金', false)
    ctxA.selectCell(0, 1, 1, true)
    ctxA.selectCell(1, 1, 2, false, true)
    ctxA.startDrag(0, 0, null)
    ctxA.updateDrag(1, 1)
    await settleFrames()
    expect(ctxA.selectedCells.value).toEqual([{ row: 1, col: 2, value: '乙' }])
    expect(ctxA.cellClassName({ rowIndex: 1, columnIndex: 2 })).toBe('')
    expect(w.element.querySelectorAll('.gt-ucell--selected').length).toBe(0)
    expect(tdA(1, 2).hasAttribute('data-gt-active')).toBe(true)
  })

  it('每个实例只跟自己登记的表；followTables 追加跟随；未登记的实例跟本组件里的任一表', async () => {
    const { ctxA, ctxB, ctxFree, tdA, tdB } = await mountHost()
    click(tdB(0, 0))
    await settleFrames()
    expect(ctxB.selectedCells.value).toEqual([{ row: 0, col: 0, value: '存货' }])
    expect(ctxA.selectedCells.value).toEqual([])
    expect(ctxFree.selectedCells.value).toEqual([{ row: 0, col: 0, value: '存货' }])
    click(tdA(0, 0))
    await settleFrames()
    expect(ctxA.selectedCells.value).toEqual([{ row: 0, col: 0, value: '货币资金' }])
    expect(ctxB.selectedCells.value).toEqual([{ row: 0, col: 0, value: '存货' }])

    const second = await mountHost({ follow: true })
    click(second.tdB(0, 1))
    await settleFrames()
    expect(second.ctxA.selectedCells.value).toEqual([{ row: 0, col: 1, value: 300 }])
  })

  it('selectRange / selectRow / selectAll / clearSelection 落到内核；复制走内核（显示文字）', async () => {
    const writeText = vi.fn(async () => undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const { w, ctxA, tdA } = await mountHost()
    click(tdA(0, 0))
    await settleFrames()
    ctxA.selectRange(0, 0, 1, 1)
    await settleFrames()
    expect(ctxA.selectedCells.value.map((c) => [c.row, c.col])).toEqual([[0, 0], [0, 1], [1, 0], [1, 1]])
    ctxA.copySelectedValues()
    await settleFrames()
    expect(writeText).toHaveBeenCalledWith('货币资金\t1,234,567.50\r\n应收账款\t20,000.00')
    ctxA.selectRow(1, 99)
    await settleFrames()
    expect(ctxA.selectedCells.value.map((c) => c.col)).toEqual([0, 1, 2])
    ctxA.selectAll(0, 0)
    await settleFrames()
    expect(ctxA.selectionCount()).toBe(6)
    ctxA.clearSelection()
    await settleFrames()
    expect(ctxA.selectedCells.value).toEqual([])
    expect(kernelForElement(tdA(0, 0))!.active).toBeNull()
    expect(w.element.querySelector('[data-gt-sel]')).toBeNull()
  })

  it('右键：内核先把点到的格并入选区，菜单打开时显示最新格数', async () => {
    const { w, ctxA, tdA } = await mountHost()
    click(tdA(0, 1))
    key(sink(w), 'ArrowDown', { shiftKey: true })
    tdA(1, 1).dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true }))
    ctxA.openContextMenu(new MouseEvent('contextmenu', { clientX: 10, clientY: 20 }), '应收账款')
    await new Promise((r) => setTimeout(r, 5))
    expect(ctxA.contextMenu.visible).toBe(true)
    expect(ctxA.selectedCells.value.length).toBe(2)
  })
})

describe('经典方式（回退开关）', () => {
  it('切到经典方式即走原实现：selectCell 生效、cellClassName 画选区；切回 Excel 方式选区清空重来', async () => {
    const prefs = useDisplayPrefsStore()
    const { ctxA } = await mountHost()
    prefs.gridEditMode = 'classic'
    await nextTick()
    ctxA.selectCell(0, 1, 123, false)
    expect(ctxA.selectedCells.value).toEqual([{ row: 0, col: 1, value: 123 }])
    expect(ctxA.cellClassName({ rowIndex: 0, columnIndex: 1 })).toBe('gt-ucell--selected gt-ucell--single-selected')
    ctxA.selectCell(1, 1, 7, false, true)
    expect(ctxA.selectedCells.value.map((c) => c.row)).toEqual([0, 1])
    prefs.gridEditMode = 'excel'
    await nextTick()
    expect(ctxA.selectedCells.value).toEqual([])
    expect(ctxA.cellClassName({ rowIndex: 0, columnIndex: 1 })).toBe('')
    prefs.gridEditMode = 'classic'
    await nextTick()
    expect(ctxA.selectedCells.value).toEqual([]) // 经典方式的旧选区不残留
  })

  it('没装表格插件（单测 / 旧环境）时同样走原实现', async () => {
    markGridInstalled(false)
    const { ctxA } = await mountHost()
    ctxA.selectCell(1, 0, '应收账款', false)
    expect(ctxA.selectedCells.value).toEqual([{ row: 1, col: 0, value: '应收账款' }])
    expect(ctxA.isCellSelected(1, 0)).toBe(true)
  })
})

describe('门面辅助', () => {
  it('kernelForElement 认格所在表格', async () => {
    const { tdA, tdB } = await mountHost()
    expect(kernelForElement(tdA(0, 0))).toBeTruthy()
    expect(kernelForElement(tdA(0, 0))).not.toBe(kernelForElement(tdB(0, 0)))
    expect(kernelForElement(document.body)).toBeNull()
  })
})
