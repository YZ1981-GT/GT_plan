import { describe, it, expect, vi } from 'vitest'
import { useNoteTableStructure, type TableData } from '../useNoteTableStructure'

// Mock Vue lifecycle hooks since we're testing outside a component
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...(actual as any),
    onMounted: vi.fn((cb: Function) => cb()),
    onBeforeUnmount: vi.fn(),
  }
})

function createTable(): TableData {
  return {
    headers: ['项目', '期末余额', '期初余额'],
    rows: [
      { label: '货币资金', values: [100, 200], is_total: false },
      { label: '应收账款', values: [300, 400], is_total: false },
      { label: '合计', values: [400, 600], is_total: true },
    ],
  }
}

describe('useNoteTableStructure', () => {
  function setup() {
    const table = createTable()
    const dirtyCount = { value: 0 }
    const struct = useNoteTableStructure({
      getActiveTable: () => table,
      markDirty: () => { dirtyCount.value++ },
    })
    return { table, struct, dirtyCount }
  }

  describe('Row Operations', () => {
    it('addRow inserts a new empty row at the given index', () => {
      const { table, struct } = setup()
      struct.addRow(1)
      expect(table.rows.length).toBe(4)
      expect(table.rows[1].label).toBe('')
      expect(table.rows[1].values).toEqual([null, null])
      expect(table.rows[1].is_total).toBe(false)
    })

    it('deleteRow removes the row at the given index', () => {
      const { table, struct } = setup()
      struct.deleteRow(0)
      expect(table.rows.length).toBe(2)
      expect(table.rows[0].label).toBe('应收账款')
    })

    it('deleteRow does not remove total rows', () => {
      const { table, struct } = setup()
      struct.deleteRow(2) // total row
      expect(table.rows.length).toBe(3) // unchanged
      expect(table.rows[2].is_total).toBe(true)
    })
  })

  describe('Column Operations', () => {
    it('addColumn inserts a new column', () => {
      const { table, struct } = setup()
      struct.addColumn(2, '本期变动')
      expect(table.headers).toEqual(['项目', '期末余额', '期初余额', '本期变动'])
      expect(table.rows[0].values).toEqual([100, 200, null])
    })

    it('deleteColumn removes the column', () => {
      const { table, struct } = setup()
      struct.deleteColumn(1) // delete '期初余额'
      expect(table.headers).toEqual(['项目', '期末余额'])
      expect(table.rows[0].values).toEqual([100])
    })

    it('renameColumn changes the column header', () => {
      const { table, struct } = setup()
      struct.renameColumn(0, '审定数')
      expect(table.headers[1]).toBe('审定数')
    })

    it('moveColumn swaps columns', () => {
      const { table, struct } = setup()
      struct.moveColumn(0, 'right') // move '期末余额' right
      expect(table.headers).toEqual(['项目', '期初余额', '期末余额'])
      expect(table.rows[0].values).toEqual([200, 100])
    })
  })

  describe('Undo/Redo', () => {
    it('undo reverses the last operation', () => {
      const { table, struct } = setup()
      struct.addRow(0)
      expect(table.rows.length).toBe(4)
      struct.undo()
      expect(table.rows.length).toBe(3)
    })

    it('redo re-applies the undone operation', () => {
      const { table, struct } = setup()
      struct.addRow(0)
      struct.undo()
      struct.redo()
      expect(table.rows.length).toBe(4)
    })

    it('canUndo/canRedo reflect stack state', () => {
      const { struct } = setup()
      expect(struct.canUndo.value).toBe(false)
      expect(struct.canRedo.value).toBe(false)
      struct.addRow(0)
      expect(struct.canUndo.value).toBe(true)
      struct.undo()
      expect(struct.canRedo.value).toBe(true)
    })

    it('new action clears redo stack', () => {
      const { struct } = setup()
      struct.addRow(0)
      struct.undo()
      expect(struct.canRedo.value).toBe(true)
      struct.addRow(0) // new action
      expect(struct.canRedo.value).toBe(false)
    })
  })

  describe('Auto-recalculate Totals', () => {
    it('recalcTotals sums non-total rows', () => {
      const { table, struct } = setup()
      table.rows[0].values = [150, 250]
      table.rows[1].values = [350, 450]
      struct.recalcTotals()
      expect(table.rows[2].values).toEqual([500, 700])
    })

    it('addRow triggers recalcTotals', () => {
      const { table, struct } = setup()
      struct.addRow(2) // add before total
      // Total should still be sum of non-total rows
      expect(table.rows[3].values).toEqual([400, 600])
    })
  })

  describe('Restore Template Structure', () => {
    it('restores headers and rows from template', () => {
      const { table, struct } = setup()
      // Modify the table
      struct.addColumn(2, '新列')
      struct.addRow(0)

      // Restore from template
      const template: TableData = {
        headers: ['项目', '期末余额', '期初余额'],
        rows: [
          { label: '货币资金', values: [0, 0], is_total: false },
          { label: '应收账款', values: [0, 0], is_total: false },
          { label: '合计', values: [0, 0], is_total: true },
        ],
      }
      struct.restoreTemplateStructure(template)
      expect(table.headers).toEqual(['项目', '期末余额', '期初余额'])
      expect(table.rows.length).toBe(3)
      // Data should be preserved for matching columns
      expect(table.rows[0].values[0]).toBe(100) // 期末余额 preserved
      expect(table.rows[0].values[1]).toBe(200) // 期初余额 preserved
    })

    it('restore can be undone', () => {
      const { table, struct } = setup()
      const originalHeaders = [...table.headers]
      struct.addColumn(2, '新列')
      struct.restoreTemplateStructure({
        headers: ['项目', '期末余额'],
        rows: [{ label: '合计', values: [0], is_total: true }],
      })
      struct.undo()
      // Should be back to state with '新列'
      expect(table.headers).toEqual(['项目', '期末余额', '期初余额', '新列'])
    })
  })

  describe('markDirty', () => {
    it('calls markDirty on each operation', () => {
      const { struct, dirtyCount } = setup()
      struct.addRow(0)
      expect(dirtyCount.value).toBe(1)
      struct.deleteRow(0)
      expect(dirtyCount.value).toBe(2)
    })
  })

  describe('clearHistory', () => {
    it('clears undo and redo stacks', () => {
      const { struct } = setup()
      struct.addRow(0)
      struct.undo()
      expect(struct.canUndo.value).toBe(false)
      expect(struct.canRedo.value).toBe(true)
      struct.clearHistory()
      expect(struct.canUndo.value).toBe(false)
      expect(struct.canRedo.value).toBe(false)
    })
  })
})
