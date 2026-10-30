/**
 * useNoteCellActions — 右键「溯源到底稿/试算表」按存储坐标打开单元格溯源（spec note-chain-followup-optimizations R2）。
 *
 * 选区列号含行名列（0 = 行名）：原先把选区列号直接当数据列传给溯源接口，取到的是右边一列；多表 / 底稿来源的格
 * 也只看第 1 张存储表。现在按写回同一套源坐标（_sourceCellRefs）取表 / 行 / 列。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useNoteCellActions } from '../useNoteCellActions'

vi.mock('element-plus', () => ({ ElMessage: Object.assign(vi.fn(), { warning: vi.fn(), info: vi.fn() }) }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn() } }))
vi.mock('@/composables/usePenetrate', () => ({ usePenetrate: () => ({ toLedger: vi.fn(), toTB: vi.fn() }) }))
vi.mock('@/composables/useNavigationStack', () => ({ useNavigationStack: () => ({ push: vi.fn() }) }))

function setup(table: any, selected: Array<{ row: number; col: number; value?: unknown }>) {
  const deCtx = { closeContextMenu: vi.fn(), selectedCells: ref(selected) }
  const api = useNoteCellActions({
    projectId: ref('p1'), year: ref(2025), currentNote: ref({ id: 'note-1', note_section: '五、1' }),
    activeTableData: computed(() => table), deCtx, router: { push: vi.fn() }, route: { fullPath: '/x' },
  })
  return api
}

const projected = {
  name: '货币资金',
  rows: [{ label: '库存现金', values: [1, 2] }, { label: '合计', values: [3, 4] }],
  _sourceCellRefs: [
    [{ row: { tableIndex: 0, rowIndex: 0, sourceSubTableKey: '货币资金' }, column: { tableIndex: 0, valueIndex: 0, key: 'end_amount', sourceSubTableKey: '货币资金' } },
      { row: { tableIndex: 0, rowIndex: 0, sourceSubTableKey: '货币资金' }, column: { tableIndex: 0, valueIndex: 1, key: 'prior_amount', sourceSubTableKey: '货币资金' } }],
    [{ row: { tableIndex: 0, rowIndex: 4, sourceSubTableKey: '货币资金' }, column: { tableIndex: 0, valueIndex: 0, key: 'end_amount', sourceSubTableKey: '货币资金' } },
      { row: { tableIndex: 0, rowIndex: 4, sourceSubTableKey: '货币资金' }, column: { tableIndex: 0, valueIndex: 1, key: 'prior_amount', sourceSubTableKey: '货币资金' } }],
  ],
}

describe('useNoteCellActions 单元格溯源坐标', () => {
  beforeEach(() => {
    vi.mocked(ElMessage.warning).mockReset()
  })

  it('选区列号含行名列：第 2 个数据列（选区列 2）⇒ 数据列 1；底稿来源带子表、来源行号与列键', () => {
    const api = setup(projected, [{ row: 1, col: 2 }])
    api.onDeCtxOpenCellTrace()
    expect(api.showCellTrace.value).toBe(true)
    expect(api.cellTraceCtx.sourceRef).toEqual({
      tableIndex: 0, row: 4, col: 1, subTableKey: '货币资金', valueKey: 'prior_amount',
    })
    expect([api.cellTraceCtx.rowIdx, api.cellTraceCtx.colIdx]).toEqual([4, 1])
  })

  it('续表合并进来的列：按那一格自己的源表序号溯源', () => {
    const merged = {
      rows: [{ label: '甲', values: [1, 9] }],
      _sourceCellRefs: [[
        { row: { tableIndex: 0, rowIndex: 0 }, column: { tableIndex: 0, valueIndex: 0 } },
        { row: { tableIndex: 2, rowIndex: 0 }, column: { tableIndex: 2, valueIndex: 0 } },
      ]],
    }
    const api = setup(merged, [{ row: 0, col: 2 }])
    api.onDeCtxOpenCellTrace()
    expect(api.cellTraceCtx.sourceRef).toEqual({ tableIndex: 2, row: 0, col: 0 })
    expect(api.cellTraceCtx.tableIndex).toBe(2)
  })

  it('行名列不溯源，提示选数值单元格', () => {
    const api = setup(projected, [{ row: 0, col: 0 }])
    api.onDeCtxOpenCellTrace()
    expect(api.showCellTrace.value).toBe(false)
    expect(ElMessage.warning).toHaveBeenCalledWith('请选中数值单元格（行名列没有取数来源）')
  })

  it('没有源坐标的旧表：按显示行号与数据列', () => {
    const api = setup({ rows: [{ label: '甲', values: [1] }] }, [{ row: 0, col: 1 }])
    api.onDeCtxOpenCellTrace()
    expect(api.cellTraceCtx.sourceRef).toEqual({ tableIndex: 0, row: 0, col: 0 })
  })
})
