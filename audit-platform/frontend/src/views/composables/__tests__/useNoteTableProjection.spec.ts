/**
 * useNoteTableProjection 守卫
 *
 * 该 composable 从 DisclosureEditor.vue（3398 行 god component）抽出时**原本零测试**，
 * 而它的续表合并含三条容易被后人"简化"掉的例外。本文件把它们逐条钉死。
 *
 * 🔴 头号判据是「不得改写源数据」—— 抽取时读代码发现原实现 `merged.push(t)` 推的是
 * 源对象引用、随后直接写 `prev.headers`，即 computed 改写自己的响应式依赖。
 * 实测：首次求值后源 headers 由 ['项目','期末余额'] 变成 ['项目','期末余额','期初余额']，
 * 第二次再多一个 '期初余额'。线上表现 = 有续表的章节改一次单元格，列就重复一次。
 */
import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'
import { useNoteTableProjection } from '../useNoteTableProjection'

function mount(note: any) {
  const currentNote = ref<any>(note)
  const api = useNoteTableProjection({
    currentNote,
    projectSubTablesClient: () => null,
    deriveLegacyTableHeaders: () => null,
  })
  return { currentNote, ...api }
}

const mainTable = () => ({
  name: '按项目分类披露',
  headers: ['项目', '期末余额'],
  rows: [{ label: '现金', values: [100] }],
})
const contTable = () => ({
  name: '按项目分类披露（续：上年年末）',
  headers: ['项目', '期初余额'],
  rows: [{ label: '现金', values: [90] }],
})

describe('useNoteTableProjection — 不得改写源数据（头号不变量）', () => {
  it('求值后源 _tables 逐值不变', () => {
    const src = [mainTable(), contTable()]
    const { currentNoteTables, currentNote } = mount({ table_data: { _tables: src } })
    const before = JSON.parse(JSON.stringify(currentNote.value.table_data._tables))

    void currentNoteTables.value

    expect(currentNote.value.table_data._tables).toEqual(before)
  })

  it('反复求值结果幂等（不重复追加续表列）', async () => {
    const { currentNoteTables, currentNote } = mount({
      table_data: { _tables: [mainTable(), contTable()] },
    })

    const first = [...currentNoteTables.value[0].headers]
    // 触发依赖变化强制重算（模拟编辑单元格等任意响应式刷新）
    currentNote.value = { ...currentNote.value }
    await nextTick()
    const second = [...currentNoteTables.value[0].headers]
    currentNote.value = { ...currentNote.value }
    await nextTick()
    const third = [...currentNoteTables.value[0].headers]

    expect(first).toEqual(['项目', '期末余额', '期初余额'])
    expect(second).toEqual(first)
    expect(third).toEqual(first)
  })

  it('改合并结果不会回写源（副本隔离）', () => {
    const { currentNoteTables, currentNote } = mount({
      table_data: { _tables: [mainTable(), contTable()] },
    })
    currentNoteTables.value[0].rows[0].values[0] = 99999
    expect(currentNote.value.table_data._tables[0].rows[0].values[0]).toBe(100)
  })
})

describe('useNoteTableProjection — 续表合并的三条例外', () => {
  it('例外①：续表自带 _column_groups ⇒ 不合并，作为独立表', () => {
    const cont = { ...contTable(), _column_groups: [{ group: 'X', start: 0, span: 2 }] }
    const { currentNoteTables } = mount({ table_data: { _tables: [mainTable(), cont] } })
    expect(currentNoteTables.value).toHaveLength(2)
    expect(currentNoteTables.value[0].headers).toEqual(['项目', '期末余额'])
  })

  it('例外①b：续表自带非空 columns ⇒ 不合并', () => {
    const cont = { ...contTable(), columns: [{ label: '项目' }, { label: '期初余额' }] }
    const { currentNoteTables } = mount({ table_data: { _tables: [mainTable(), cont] } })
    expect(currentNoteTables.value).toHaveLength(2)
  })

  it('例外②：找不到同名主表 ⇒ 独立保留，绝不并到上一张（防串表）', () => {
    const orphan = { ...contTable(), name: '完全不相干的表（续：上年年末）' }
    const { currentNoteTables } = mount({ table_data: { _tables: [mainTable(), orphan] } })
    expect(currentNoteTables.value).toHaveLength(2)
    // 主表未被污染
    expect(currentNoteTables.value[0].headers).toEqual(['项目', '期末余额'])
  })

  it('例外③：续表首列与主表首列同名 ⇒ 跳过该重复列', () => {
    const { currentNoteTables } = mount({
      table_data: { _tables: [mainTable(), contTable()] },
    })
    // 续表 headers 是 ['项目','期初余额']，'项目' 与主表首列同名被跳过
    expect(currentNoteTables.value[0].headers).toEqual(['项目', '期末余额', '期初余额'])
  })

  it('例外③c：续表 source refs 与值列同步，且主表短行补 null', () => {
    const main = {
      ...mainTable(),
      _sourceColumnRefs: [{ tableIndex: 0, valueIndex: 0, sourceSubTableKey: '主表', key: 'ending' }],
      _sourceCellRefs: [[{
        row: { tableIndex: 0, rowIndex: 0, sourceSubTableKey: '主表' },
        column: { tableIndex: 0, valueIndex: 0, sourceSubTableKey: '主表', key: 'ending' },
      }]],
      _sourceLabelRefs: [{ tableIndex: 0, rowIndex: 0, sourceSubTableKey: '主表' }],
      _sourceRowRefs: [[{ tableIndex: 0, rowIndex: 0, sourceSubTableKey: '主表' }]],
    }
    const continuation = {
      ...contTable(),
      _sourceColumnRefs: [{ tableIndex: 1, valueIndex: 0, sourceSubTableKey: '续表', key: 'opening' }],
      _sourceCellRefs: [[{
        row: { tableIndex: 1, rowIndex: 0, sourceSubTableKey: '续表' },
        column: { tableIndex: 1, valueIndex: 0, sourceSubTableKey: '续表', key: 'opening' },
      }]],
      _sourceLabelRefs: [{ tableIndex: 1, rowIndex: 0, sourceSubTableKey: '续表' }],
      _sourceRowRefs: [[{ tableIndex: 1, rowIndex: 0, sourceSubTableKey: '续表' }]],
    }
    const { currentNoteTables } = mount({ table_data: { _tables: [main, continuation] } })
    const table = currentNoteTables.value[0]

    expect(table.rows[0].values).toEqual([100, 90])
    expect(table._sourceColumnRefs.map((ref: any) => ref?.key)).toEqual(['ending', 'opening'])
    expect(table._sourceCellRefs[0].map((ref: any) => ref?.column?.key)).toEqual(['ending', 'opening'])

    const mainShort = { ...main, rows: [] }
    const { currentNoteTables: shortTables } = mount({ table_data: { _tables: [mainShort, continuation] } })
    expect(shortTables.value[0].rows[0].values).toEqual([null, 90])
    expect(shortTables.value[0]._sourceCellRefs[0][0]).toBeNull()
    expect(shortTables.value[0]._sourceCellRefs[0][1]?.column?.key).toBe('opening')
  })
})


describe('useNoteTableProjection — 三层兜底顺序即优先级', () => {
  it('优先 _tables', () => {
    const currentNote = ref<any>({
      table_data: { _tables: [mainTable()], rows: [{ label: '旧格式', values: [1] }] },
    })
    const { currentNoteTables } = useNoteTableProjection({
      currentNote,
      projectSubTablesClient: () => [{ name: '客户端投影', headers: ['x'], rows: [] }],
      deriveLegacyTableHeaders: () => null,
    })
    expect(currentNoteTables.value[0].name).toBe('按项目分类披露')
  })

  it('无 _tables 时用客户端投影，优先于旧格式 rows', () => {
    const currentNote = ref<any>({
      table_data: {
        _source: 'workpaper',
        sub_table_data: { client: [{ label: '客户端', amount: 2 }] },
        rows: [{ label: '旧格式', values: [1] }],
      },
    })
    const { currentNoteTables } = useNoteTableProjection({
      currentNote,
      projectSubTablesClient: () => [{ name: '客户端投影', headers: ['x'], rows: [] }],
      deriveLegacyTableHeaders: () => null,
    })
    expect(currentNoteTables.value[0].name).toBe('客户端投影')
  })

  it('两者都无时退回旧格式单表，表头走 deriveLegacyTableHeaders', () => {
    const currentNote = ref<any>({
      section_title: '货币资金',
      table_data: { rows: [{ label: '现金', values: [1] }] },
    })
    const { currentNoteTables } = useNoteTableProjection({
      currentNote,
      projectSubTablesClient: () => null,
      deriveLegacyTableHeaders: () => ['项目', '金额'],
    })
    expect(currentNoteTables.value).toHaveLength(1)
    expect(currentNoteTables.value[0].name).toBe('货币资金')
    expect(currentNoteTables.value[0].headers).toEqual(['项目', '金额'])
  })

  it('无 table_data ⇒ 空数组（不抛错）', () => {
    const { currentNoteTables } = mount({})
    expect(currentNoteTables.value).toEqual([])
  })
})

describe('useNoteTableProjection — activeTableColumns 的 null 语义', () => {
  it('🔴 无 _column_groups ⇒ 返回 null（表示"走扁平列逻辑"，不是"无列"）', () => {
    const { activeTableColumns } = mount({ table_data: { _tables: [mainTable()] } })
    expect(activeTableColumns.value).toBeNull()
  })

  it('无表头 ⇒ 返回空数组（与 null 语义不同，模板据此分支）', () => {
    const { activeTableColumns } = mount({
      table_data: { _tables: [{ name: 'x', headers: [], rows: [] }] },
    })
    expect(activeTableColumns.value).toEqual([])
  })

  it('有 _column_groups ⇒ 分组列与扁平列按 headers 顺序交织', () => {
    const table = {
      name: 'x',
      headers: ['项目', '期初', '本期增', '期末'],
      rows: [],
      _column_groups: [{ group: '变动', start: 1, span: 2 }],
    }
    const { activeTableColumns } = mount({ table_data: { _tables: [table] } })
    const cols = activeTableColumns.value!
    expect(cols).toHaveLength(3)
    expect(cols[0]).toEqual({ type: 'flat', headerIdx: 0, label: '项目' })
    expect(cols[1]).toEqual({
      type: 'grouped',
      group: '变动',
      children: [{ headerIdx: 1, label: '期初' }, { headerIdx: 2, label: '本期增' }],
    })
    expect(cols[2]).toEqual({ type: 'flat', headerIdx: 3, label: '期末' })
  })
})

describe('useNoteTableProjection — 原始 table_index 到投影 tab 的映射', () => {
  it('续表的多个源下标映射到同一张投影表，独立表映射自身', () => {
    const { currentNoteTables, resolveProjectedTableIndex } = mount({
      table_data: {
        _tables: [
          mainTable(),
          contTable(),
          { name: '另一张', headers: ['项目', '金额'], rows: [] },
        ],
      },
    })

    expect(currentNoteTables.value).toHaveLength(2)
    expect(resolveProjectedTableIndex(0)).toBe(0)
    expect(resolveProjectedTableIndex('1')).toBe(0)
    expect(resolveProjectedTableIndex(2)).toBe(1)
  })

  it('非法、负数、非整数和越界源下标统一回退第 0 张', () => {
    const { resolveProjectedTableIndex } = mount({
      table_data: { _tables: [mainTable(), contTable(), { name: '另一张', headers: ['项目'], rows: [] }] },
    })

    expect(resolveProjectedTableIndex(undefined)).toBe(0)
    expect(resolveProjectedTableIndex('')).toBe(0)
    expect(resolveProjectedTableIndex('abc')).toBe(0)
    expect(resolveProjectedTableIndex(-1)).toBe(0)
    expect(resolveProjectedTableIndex('1.5')).toBe(0)
    expect(resolveProjectedTableIndex(99)).toBe(0)
  })
})

describe('useNoteTableProjection — activeTableTab 切换', () => {
  it('按 tab 下标取表，越界回落到第 0 张', () => {
    const { activeTableTab, activeTableData } = mount({
      table_data: { _tables: [mainTable(), { name: '另一张', headers: ['a'], rows: [] }] },
    })
    expect(activeTableData.value.name).toBe('按项目分类披露')
    activeTableTab.value = '1'
    expect(activeTableData.value.name).toBe('另一张')
    activeTableTab.value = '99'
    expect(activeTableData.value.name).toBe('按项目分类披露')
  })
})
