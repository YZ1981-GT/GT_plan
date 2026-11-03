import { describe, expect, it, vi } from 'vitest'
import { reactive, ref } from 'vue'
import { useNoteTableInteraction } from '../useNoteTableInteraction'

function createContext() {
  return {
    cellClassName: () => '',
    closeContextMenu: vi.fn(),
    openContextMenu: vi.fn(),
    selectCell: vi.fn(),
    isCellSelected: () => false,
    copySelectedValues: vi.fn(),
    sumSelectedValues: () => 0,
    contextMenu: { itemName: '' },
    selectedCells: ref([]),
  }
}

describe('useNoteTableInteraction', () => {
  it('locates a table row emitted as a Vue proxy against the raw projected row', () => {
    const row = { label: '固定资产', values: [123], is_total: false }
    const rows = [row]
    const context = createContext()
    const api = useNoteTableInteraction({
      activeTableData: ref({ headers: ['项目', '期末账面价值'], rows }),
      currentNote: ref({ note_section: '八、22' }),
      showNoteFormulaManager: ref(false),
      deCtx: context,
      deComments: { commentCellClass: () => '' },
      fmtAmount: String,
    })

    api.onDeCellClick(reactive(row), { label: '期末账面价值' }, document.createElement('td'), new MouseEvent('click'))

    expect(context.selectCell).toHaveBeenCalledWith(0, 1, 123, false, false)
  })

  it('maps the label column from row.label without shifting physical table coordinates', () => {
    const context = createContext()
    const row = { label: '固定资产', values: [123], is_total: false }
    const api = useNoteTableInteraction({
      activeTableData: ref({ headers: ['项目', '期末账面价值'], rows: [row] }),
      currentNote: ref({}),
      showNoteFormulaManager: ref(false),
      deCtx: context,
      deComments: { commentCellClass: () => '' },
      fmtAmount: String,
    })

    api.onDeCellClick(reactive(row), { label: '项目' }, document.createElement('td'), new MouseEvent('click'))

    expect(context.selectCell).toHaveBeenCalledWith(0, 0, '固定资产', false, false)
    expect(context.contextMenu.itemName).toBe('固定资产')
  })

  it('uses the data-column offset and row label when selecting a context-menu cell', () => {
    const context = createContext()
    const row = { label: '固定资产', values: [123], is_total: false }
    const api = useNoteTableInteraction({
      activeTableData: ref({ headers: ['项目', '期末账面价值'], rows: [row] }),
      currentNote: ref({}),
      showNoteFormulaManager: ref(false),
      deCtx: context,
      deComments: { commentCellClass: () => '' },
      fmtAmount: String,
    })
    const event = new MouseEvent('contextmenu')

    api.onDeCellContextMenu(reactive(row), { label: '期末账面价值' }, document.createElement('td'), event)

    expect(context.selectCell).toHaveBeenCalledWith(0, 1, 123, false)
    expect(context.contextMenu.itemName).toBe('固定资产')
    expect(context.openContextMenu).toHaveBeenCalledWith(event, '固定资产')
  })

  it('同名叶子列按 column-key 定位：点上年年末「应收账款」不会选中期末那一格（浏览器实测）', () => {
    const context = createContext()
    const row = { label: '1年以内', values: [100, 10, 80, 8], is_total: false }
    const api = useNoteTableInteraction({
      activeTableData: ref({ headers: ['账龄', '应收账款', '坏账准备', '应收账款', '坏账准备'], rows: [row] }),
      currentNote: ref({}),
      showNoteFormulaManager: ref(false),
      deCtx: context,
      deComments: { commentCellClass: () => '' },
      fmtAmount: String,
    })

    api.onDeCellClick(reactive(row), { label: '应收账款', columnKey: 'h3' }, document.createElement('td'), new MouseEvent('click'))
    expect(context.selectCell).toHaveBeenCalledWith(0, 3, 80, false, false)

    const event = new MouseEvent('contextmenu')
    api.onDeCellContextMenu(reactive(row), { label: '坏账准备', columnKey: 'h4' }, document.createElement('td'), event)
    expect(context.selectCell).toHaveBeenLastCalledWith(0, 4, 8, false)

    // 越界的 key 不定位（不落到别的列）
    context.selectCell.mockClear()
    api.onDeCellClick(reactive(row), { label: '应收账款', columnKey: 'h9' }, document.createElement('td'), new MouseEvent('click'))
    expect(context.selectCell).not.toHaveBeenCalled()
  })

  it('右键已有选区内另一格：保持选区但菜单标题跟本次点击行', () => {
    const context = createContext()
    context.contextMenu.itemName = '旧项目'
    context.isCellSelected = () => true
    const rows = [
      { label: '固定资产', values: [123] },
      { label: '无形资产', values: [456] },
    ]
    const api = useNoteTableInteraction({
      activeTableData: ref({ headers: ['项目', '期末账面价值'], rows }),
      currentNote: ref({}),
      showNoteFormulaManager: ref(false),
      deCtx: context,
      deComments: { commentCellClass: () => '' },
      fmtAmount: String,
    })
    const event = new MouseEvent('contextmenu')

    api.onDeCellContextMenu(reactive(rows[1]), { label: '期末账面价值' }, document.createElement('td'), event)

    expect(context.selectCell).not.toHaveBeenCalled()
    expect(context.contextMenu.itemName).toBe('无形资产')
    expect(context.openContextMenu).toHaveBeenCalledWith(event, '无形资产')
  })

  it('does not select a row that is not part of the active projection', () => {
    const context = createContext()
    const api = useNoteTableInteraction({
      activeTableData: ref({ headers: ['项目', '期末账面价值'], rows: [{ label: '固定资产', values: [123] }] }),
      currentNote: ref({}),
      showNoteFormulaManager: ref(false),
      deCtx: context,
      deComments: { commentCellClass: () => '' },
      fmtAmount: String,
    })

    api.onDeCellClick({ label: '外部行', values: [7] }, { label: '期末账面价值' }, document.createElement('td'), new MouseEvent('click'))

    expect(context.selectCell).not.toHaveBeenCalled()
  })
})
