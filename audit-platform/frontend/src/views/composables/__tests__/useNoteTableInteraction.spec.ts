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
    const activateCell = vi.fn()
    const context = createContext()
    const api = useNoteTableInteraction({
      activeTableData: ref({ headers: ['项目', '期末账面价值'], rows }),
      currentNote: ref({ note_section: '八、22' }),
      editMode: ref(true),
      showNoteFormulaManager: ref(false),
      deCtx: context,
      deComments: { commentCellClass: () => '' },
      activateCell,
      fmtAmount: String,
    })

    api.onDeCellClick(reactive(row), { label: '期末账面价值' }, document.createElement('td'), new MouseEvent('click'))

    expect(context.selectCell).toHaveBeenCalledWith(0, 1, 123, false, false)
    expect(activateCell).toHaveBeenCalledWith(0, 0)
  })

  it('maps the label column from row.label without shifting physical table coordinates', () => {
    const context = createContext()
    const row = { label: '固定资产', values: [123], is_total: false }
    const api = useNoteTableInteraction({
      activeTableData: ref({ headers: ['项目', '期末账面价值'], rows: [row] }),
      currentNote: ref({}),
      editMode: ref(true),
      showNoteFormulaManager: ref(false),
      deCtx: context,
      deComments: { commentCellClass: () => '' },
      activateCell: vi.fn(),
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
      editMode: ref(false),
      showNoteFormulaManager: ref(false),
      deCtx: context,
      deComments: { commentCellClass: () => '' },
      activateCell: vi.fn(),
      fmtAmount: String,
    })
    const event = new MouseEvent('contextmenu')

    api.onDeCellContextMenu(reactive(row), { label: '期末账面价值' }, document.createElement('td'), event)

    expect(context.selectCell).toHaveBeenCalledWith(0, 1, 123, false)
    expect(context.contextMenu.itemName).toBe('固定资产')
    expect(context.openContextMenu).toHaveBeenCalledWith(event, '固定资产')
  })

  it('does not activate a row that is not part of the active projection', () => {
    const activateCell = vi.fn()
    const api = useNoteTableInteraction({
      activeTableData: ref({ headers: ['项目', '期末账面价值'], rows: [{ label: '固定资产', values: [123] }] }),
      currentNote: ref({}),
      editMode: ref(true),
      showNoteFormulaManager: ref(false),
      deCtx: createContext(),
      deComments: { commentCellClass: () => '' },
      activateCell,
      fmtAmount: String,
    })

    api.onDeCellClick({ label: '外部行', values: [7] }, { label: '期末账面价值' }, document.createElement('td'), new MouseEvent('click'))

    expect(activateCell).not.toHaveBeenCalled()
  })
})
