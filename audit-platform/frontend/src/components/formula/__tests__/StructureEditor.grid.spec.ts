/**
 * 表样编辑器的表格交互（spec excel-style-table-editing 5.5）。
 *
 * 原状：单击即把光标放进格里（contenteditable），方向键 / Enter / Tab 由页面自己在 document 上导航，
 * 失焦才记修改。现在 Excel / 单击编辑方式下接内核：单击只选中（公式栏跟着当前格），双击 / F2 / 直接输入才编辑，
 * 提交记一条待保存修改；经典方式保持原来的一点就编辑。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const HTML = `<style>.gt-excel-table td { padding: 4px; }</style>
<table class="gt-excel-table">
<tr class="gt-col-header-row"><td class="gt-col-header"></td><td class="gt-col-header">A</td><td class="gt-col-header">B</td></tr>
<tr><td class="gt-row-header">1</td><td data-cell="0:0" data-addr="A1" contenteditable="true">项目<span class="gt-cell-coord">A1</span></td><td data-cell="0:1" data-addr="B1" contenteditable="true">期末<span class="gt-cell-coord">B1</span></td></tr>
<tr><td class="gt-row-header">2</td><td data-cell="1:0" data-addr="A2" contenteditable="true">货币资金<span class="gt-cell-coord">A2</span></td><td data-cell="1:1" data-addr="B2" data-formula="=B3" contenteditable="true">100<span class="gt-cell-coord">B2</span></td></tr>
</table>`

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({ default: { get: (...a: any[]) => mockGet(...a) }, api: { get: (...a: any[]) => mockGet(...a), post: vi.fn() } }))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return { ...actual, ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() } }
})
vi.mock('@/services/commonApi', () => ({
  getExcelHtmlPreview: vi.fn().mockResolvedValue({ html: '', total_rows: 0, sheet_names: [] }),
  saveExcelHtmlEdits: vi.fn().mockResolvedValue({ version: 1 }),
  getModuleHtml: vi.fn(async () => ({ html: HTML })),
  acquireEditLock: vi.fn().mockResolvedValue(undefined),
  releaseEditLock: vi.fn().mockResolvedValue(undefined),
  refreshEditLock: vi.fn().mockResolvedValue(undefined),
  listFileVersions: vi.fn().mockResolvedValue([]),
  rollbackFileVersion: vi.fn().mockResolvedValue(undefined),
  executeFormulas: vi.fn().mockResolvedValue({ executed: 0, total_formulas: 0, errors: [] }),
}))
vi.mock('../FormulaBar.vue', () => ({ default: { template: '<div class="mock-formula-bar" />' } }))
vi.mock('../CellSelector.vue', () => ({ default: { template: '<div class="mock-cell-selector" />' } }))

import StructureEditor from '@/components/formula/StructureEditor.vue'

const STUBS = {
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-button-group': { template: '<div><slot /></div>' },
  'el-divider': true, 'el-checkbox': true, 'el-input': true, 'el-input-number': true, 'el-select': true, 'el-option': true,
  'el-form': true, 'el-form-item': true, 'el-dialog': true, 'el-tabs': true, 'el-tab-pane': true,
  'el-table': true, 'el-table-column': true, 'el-pagination': true,
}

async function settle() {
  for (let i = 0; i < 4; i++) { await flushPromises(); await nextTick() }
}

async function mountSE() {
  const w = mount(StructureEditor, {
    props: { projectId: 'p1', module: 'disclosure_note', moduleParams: { note_section: '五、6', year: 2024 }, year: 2024 },
    global: { stubs: STUBS },
    attachTo: document.body,
  })
  await settle()
  const s = (w.vm as any).$.setupState
  const td = (cell: string) => w.element.querySelector(`td[data-cell="${cell}"]`) as HTMLTableCellElement
  const span = (cell: string) => td(cell).querySelector('.gt-ce-value') as HTMLElement
  const sink = () => w.element.querySelector('.gt-grid-sink') as HTMLTextAreaElement
  return { w, s, td, span, sink }
}
const down = (el: Element) => el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }))
const keydown = (el: Element, key: string) => el.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  mockGet.mockReset()
  mockGet.mockResolvedValue([])
  document.body.innerHTML = ''
})

describe('StructureEditor 表格交互', () => {
  it('Excel 方式：单击只选中（公式栏跟着当前格），双击编辑，Enter 提交记一条待保存修改并下移', async () => {
    const { w, s, td, span, sink } = await mountSE()
    expect(td('1:1').hasAttribute('contenteditable')).toBe(false)
    expect(sink()).not.toBeNull()
    down(td('1:1'))
    td('1:1').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    await settle()
    expect(span('1:1').hasAttribute('contenteditable')).toBe(false)
    expect(td('1:1').classList.contains('gt-selected')).toBe(false) // 选中框由内核画，不再另加旧高亮
    expect(s.selectedCell).toBe('1:1')
    expect(s.currentCellInfo).toMatchObject({ cell: '1:1', address: 'B2', value: '100', formula: '=B3' })
    // 页面自带的 Esc「取消选中」不再生效（选区归内核，公式栏不能和选中框对不上）
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(s.selectedCell).toBe('1:1')
    keydown(sink(), 'ArrowUp') // 方向键归内核：公式栏跟着走
    await settle()
    expect(s.currentCellInfo).toMatchObject({ cell: '0:1', value: '期末' })
    td('0:1').dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }))
    await settle()
    expect(span('0:1').getAttribute('contenteditable')).toBe('plaintext-only')
    span('0:1').textContent = '期末余额'
    keydown(span('0:1'), 'Enter')
    await settle()
    expect(s.pendingEdits).toEqual([{ action: 'edit', cell: '0:1', value: '期末余额' }])
    expect(s.currentCellInfo).toMatchObject({ cell: '1:1' })
    // Ctrl+Z：内核撤销（格子回原值，再记一条还原修改）；撤销栈空了也不去弹「待保存操作」
    const ctrlZ = () => sink().dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true, cancelable: true }))
    ctrlZ()
    await settle()
    expect(span('0:1').textContent).toBe('期末')
    expect(s.pendingEdits).toEqual([{ action: 'edit', cell: '0:1', value: '期末余额' }, { action: 'edit', cell: '0:1', value: '期末' }])
    ctrlZ()
    await settle()
    expect(s.pendingEdits).toHaveLength(2)
    w.unmount()
  })

  it('经典方式：保持原来的一点就编辑（td 可编辑、无编辑器 span）；切回 Excel 再接上', async () => {
    useDisplayPrefsStore().setGridEditMode('classic')
    const { w, s, td } = await mountSE()
    expect(td('1:0').getAttribute('contenteditable')).toBe('true')
    expect(td('1:0').querySelector('.gt-ce-value')).toBeNull()
    td('1:0').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(s.selectedCell).toBe('1:0')
    expect(td('1:0').classList.contains('gt-selected')).toBe(true)
    useDisplayPrefsStore().setGridEditMode('excel')
    await settle()
    expect(td('1:0').hasAttribute('contenteditable')).toBe(false)
    expect(td('1:0').querySelector('.gt-ce-value')!.textContent).toBe('货币资金')
    w.unmount()
  })
})
