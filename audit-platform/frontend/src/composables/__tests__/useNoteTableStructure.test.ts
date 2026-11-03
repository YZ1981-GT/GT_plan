import { describe, it, expect, vi } from 'vitest'
import { structureRowTargets, useNoteTableStructure, type TableData } from '../useNoteTableStructure'

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

    it('多段小计按合计构成各算各的、合计 = 小计 − 减项（spec note-pull-header-formula-closure R5）', () => {
      const table: TableData = {
        headers: ['账龄', '期末余额', '期初余额'],
        rows: [
          { label: '1年以内', values: [100, 10] },
          { label: '1至2年', values: [50, null] },
          { label: '小计', values: [null, null], is_total: true, row_type: 'subtotal' },
          { label: '减：坏账准备', values: [15, 1] },
          { label: '合计', values: [null, null], is_total: true },
        ],
      }
      const struct = useNoteTableStructure({ getActiveTable: () => table, markDirty: () => {} })
      struct.recalcTotals()
      expect(table.rows[2].values).toEqual([150, 10])
      expect(table.rows[4].values).toEqual([135, 9])
    })
  })

  describe('加行 / 删行认结构行', () => {
    const rows = [
      { label: '1年以内', values: [] },
      { label: '1至2年', values: [] },
      { label: '小计', values: [], row_type: 'subtotal' },
      { label: '减：坏账准备', values: [] },
      { label: '合计', values: [], is_total: true },
    ]

    it('加在第一个上方有明细的合计 / 小计行之前；删最后一个明细行（不删减项）', () => {
      expect(structureRowTargets(rows)).toEqual({ insertAt: 2, deleteAt: 1 })
    })

    it('标题式小计表加进第一组；明细不足两行不删；没有合计行加在末尾', () => {
      const titled = [
        { label: '商业承兑汇票小计', row_type: 'subtotal' }, { label: '' },
        { label: '银行承兑汇票小计', row_type: 'subtotal' }, { label: '' }, { label: '合计', is_total: true },
      ]
      expect(structureRowTargets(titled)).toEqual({ insertAt: 2, deleteAt: 3 })
      expect(structureRowTargets([{ label: '库存现金' }, { label: '合计', is_total: true }, { label: '其中：境外' }]))
        .toEqual({ insertAt: 1, deleteAt: -1 })
      expect(structureRowTargets([{ label: '甲' }, { label: '乙' }])).toEqual({ insertAt: 2, deleteAt: 1 })
    })

    it('deleteRow 不删按 row_type 标的小计行', () => {
      const table: TableData = { headers: ['项目', '期末'], rows: rows.map((r) => ({ ...r, values: [null] })) }
      const struct = useNoteTableStructure({ getActiveTable: () => table, markDirty: () => {} })
      struct.deleteRow(2)
      expect(table.rows).toHaveLength(5)
    })

    it('集团下推的固定行不删：➖ 行跳到上一个可删明细行，全是固定行时不删；可选行能删', () => {
      const fixed = (label: string) => ({ label, values: [null], _pushed_row_id: `r-${label}`, _pushed_category: 'required' })
      expect(structureRowTargets([{ label: '自加行' }, fixed('库存现金'), fixed('银行存款'), { label: '合计', is_total: true }]))
        .toEqual({ insertAt: 3, deleteAt: 0 })
      expect(structureRowTargets([fixed('库存现金'), fixed('银行存款'), { label: '合计', is_total: true }]))
        .toEqual({ insertAt: 2, deleteAt: -1 })
      const optional = { label: '其他货币资金', values: [null], _pushed_row_id: 'r-o', _pushed_category: 'optional' }
      expect(structureRowTargets([fixed('库存现金'), optional]).deleteAt).toBe(1)

      const table: TableData = { headers: ['项目', '期末'], rows: [fixed('库存现金'), { label: '自加行', values: [1] }] }
      const struct = useNoteTableStructure({ getActiveTable: () => table, markDirty: () => {} })
      struct.deleteRow(0)
      expect(table.rows.map(r => r.label)).toEqual(['库存现金', '自加行'])
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

    it('恢复模板结构按行名带回集团下推行身份（合并拉数按它精确对应）', () => {
      const { table, struct } = setup()
      Object.assign(table.rows[0], { _pushed_row_id: 'r-cash', _pushed_category: 'optional', _pushed_optional_active: false })
      struct.restoreTemplateStructure({
        headers: ['项目', '期末余额', '期初余额'],
        rows: [{ label: '货币资金', values: [0, 0] }, { label: '合计', values: [0, 0], is_total: true }],
      })
      expect(table.rows[0]).toMatchObject({ _pushed_row_id: 'r-cash', _pushed_category: 'optional', _pushed_optional_active: false })
      expect(table.rows[1]._pushed_row_id).toBeUndefined()
    })

    // 上市 五、5「组合计提项目」表（两级表头：期末余额 / 上年年末余额 下各有「应收账款 | 坏账准备 | 比例」）
    const COMBO_COLUMNS = [
      { key: 'label', label: '账龄', is_label: true },
      { key: 'end_amount', label: '应收账款', group: '期末余额' }, { key: 'end_provision', label: '坏账准备', group: '期末余额' },
      { key: 'prior_amount', label: '应收账款', group: '上年年末余额' }, { key: 'prior_provision', label: '坏账准备', group: '上年年末余额' },
    ]
    const COMBO_GROUPS = [{ group: '期末余额', start: 1, span: 2 }, { group: '上年年末余额', start: 3, span: 2 }]
    const comboTemplate = (): TableData & Record<string, any> => ({
      name: '组合计提项目：应收中央企业客户',
      headers: ['账龄', '应收账款', '坏账准备', '应收账款', '坏账准备'],
      columns: COMBO_COLUMNS, _column_groups: COMBO_GROUPS,
      rows: [{ label: '1年以内', values: [null, null, null, null], row_type: 'data' },
        { label: '1-2年', values: [null, null, null, null], row_type: 'data' },
        { label: '合  计', values: [null, null, null, null], is_total: true, row_type: 'total' }],
    })

    it('多级表头同名列按列身份搬金额：上年年末「应收账款」不会被期末数顶替（只按列名会取第一列）', () => {
      // 当前表：列顺序被调过（上年年末在前）、多了一个自加行与过期的列定义
      const table: TableData & Record<string, any> = {
        name: '组合计提项目：应收中央企业客户',
        headers: ['账龄', '应收账款', '坏账准备', '应收账款', '坏账准备'],
        columns: [COMBO_COLUMNS[0], COMBO_COLUMNS[3], COMBO_COLUMNS[4], COMBO_COLUMNS[1], COMBO_COLUMNS[2]],
        _column_groups: [{ group: '上年年末余额', start: 1, span: 2 }, { group: '期末余额', start: 3, span: 2 }],
        _row_types: ['data', 'data', 'total'],
        rows: [
          // 行名空白与模板不同（「1 年以内」↔「1年以内」）照样对上
          { label: '1 年以内', values: [80, 8, 100, 10], row_type: 'data', _pushed_row_id: 'r1', _pushed_category: 'required',
            _cell_meta: { 0: { semantic: 'prior' }, 2: { semantic: 'end' } }, _cell_modes: { 0: 'manual', 2: 'auto' } },
          { label: '自加行', values: [1, 1, 1, 1] },
          { label: '合计', values: [80, 8, 100, 10], is_total: true },
        ],
      }
      const struct = useNoteTableStructure({ getActiveTable: () => table, markDirty: () => {} })
      struct.restoreTemplateStructure(comboTemplate())
      expect(table.rows.map(r => r.label)).toEqual(['1年以内', '1-2年', '合  计'])
      expect(table.rows[0].values).toEqual([100, 10, 80, 8])
      expect(table.rows[0]).toMatchObject({ row_type: 'data', _pushed_row_id: 'r1', _pushed_category: 'required',
        _cell_meta: { 0: { semantic: 'end' }, 2: { semantic: 'prior' } }, _cell_modes: { 0: 'auto', 2: 'manual' } })
      expect(table.rows[1]).toEqual({ label: '1-2年', values: [null, null, null, null], is_total: false, row_type: 'data' })
      // 合计行行名空白不同照样对上；金额由合计重算
      expect(table.rows[2]).toMatchObject({ is_total: true, row_type: 'total', values: [100, 10, 80, 8] })
      expect(table.columns).toEqual(COMBO_COLUMNS)
      expect(table._column_groups).toEqual(COMBO_GROUPS)
      expect(table._row_types).toEqual(['data', 'data', 'total'])
    })

    it('当前表缺分组信息时按列定义 key 对应（不靠列名）', () => {
      const table: TableData & Record<string, any> = {
        headers: ['账龄', '应收账款', '坏账准备', '应收账款', '坏账准备'],
        columns: [{ key: 'label' }, { key: 'prior_amount' }, { key: 'prior_provision' }, { key: 'end_amount' }, { key: 'end_provision' }],
        rows: [{ label: '1年以内', values: [80, 8, 100, 10] }],
      }
      const struct = useNoteTableStructure({ getActiveTable: () => table, markDirty: () => {} })
      struct.restoreTemplateStructure(comboTemplate())
      expect(table.rows[0].values).toEqual([100, 10, 80, 8])
    })

    it('没有列定义的表按「分组 / 列名 / 第几次出现」搬；撤销连列定义一起还原', () => {
      const template = comboTemplate()
      delete template.columns
      // 当前表分组顺序与模板相反（上年年末在前）：只按列名、依次取会把上年年末数搬进期末
      const table: TableData & Record<string, any> = {
        headers: ['账龄', '应收账款', '坏账准备', '应收账款', '坏账准备'],
        _column_groups: [{ group: '上年年末余额', start: 1, span: 2 }, { group: '期末余额', start: 3, span: 2 }],
        columns: [{ key: 'stale' }], rows: [{ label: '1年以内', values: [80, 8, 100, 10] }],
      }
      const struct = useNoteTableStructure({ getActiveTable: () => table, markDirty: () => {} })
      struct.restoreTemplateStructure(template)
      expect(table.rows[0].values).toEqual([100, 10, 80, 8])
      expect(table.columns).toBeUndefined()
      expect(table._row_types).toBeUndefined()
      struct.undo()
      expect(table.columns).toEqual([{ key: 'stale' }])
      expect(table.rows.map(r => r.label)).toEqual(['1年以内'])
    })

    it('当前表没有分组信息也没有列定义：同名列按出现顺序对应（不都取第一列）', () => {
      const template = comboTemplate()
      delete template.columns
      const table: TableData = { headers: ['账龄', '应收账款', '坏账准备', '应收账款', '坏账准备'],
        rows: [{ label: '1年以内', values: [100, 10, 80, 8] }] }
      const struct = useNoteTableStructure({ getActiveTable: () => table, markDirty: () => {} })
      struct.restoreTemplateStructure(template)
      expect(table.rows[0].values).toEqual([100, 10, 80, 8])
    })

    it('弱规则不抢强规则的列：一组分组改了名（期末余额→期末数）、另一组对得上，改名组仍按剩下的同名列对应', () => {
      const template = comboTemplate()
      delete template.columns
      const table: TableData & Record<string, any> = {
        headers: ['账龄', '应收账款', '坏账准备', '应收账款', '坏账准备'],
        _column_groups: [{ group: '上年年末余额', start: 1, span: 2 }, { group: '期末数', start: 3, span: 2 }],
        rows: [{ label: '1年以内', values: [80, 8, 100, 10] }],
      }
      const struct = useNoteTableStructure({ getActiveTable: () => table, markDirty: () => {} })
      struct.restoreTemplateStructure(template)
      expect(table.rows[0].values).toEqual([100, 10, 80, 8])
    })

    it('同名多行（两组下各有「其他」）依次对应，不都取第一行', () => {
      const table: TableData = { headers: ['项目', '期末'], rows: [
        { label: '银行存款', values: [1] }, { label: '其他', values: [5] }, { label: '库存现金', values: [2] }, { label: '其他', values: [7] }] }
      const struct = useNoteTableStructure({ getActiveTable: () => table, markDirty: () => {} })
      struct.restoreTemplateStructure({ headers: ['项目', '期末'], rows: [
        { label: '银行存款', values: [null] }, { label: '其他', values: [null] }, { label: '库存现金', values: [null] }, { label: '其他', values: [null] }] })
      expect(table.rows.map(r => r.values[0])).toEqual([1, 5, 2, 7])
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
