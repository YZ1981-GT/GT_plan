import { describe, expect, it } from 'vitest'
import { resolveNoteStructureEditState } from '../noteStructureEditing'

describe('resolveNoteStructureEditState', () => {
  it('允许编辑一对一普通 _tables 源表', () => {
    const source = { name: '普通表', headers: ['项目', '金额'], rows: [] }
    const result = resolveNoteStructureEditState({ _tables: [source] }, {
      ...source,
      _sourceTableIndexes: [0],
    })

    expect(result.table).toBe(source)
    expect(result.reason).toBeNull()
  })

  it('允许编辑 legacy 单表原件', () => {
    const source = { headers: ['项目', '金额'], rows: [] }
    const result = resolveNoteStructureEditState(source, {
      ...source,
      _sourceTableIndexes: [0],
    })

    expect(result.table).toBe(source)
  })

  it('拒绝跨源续表合并结果', () => {
    const result = resolveNoteStructureEditState({ _tables: [{}, {}] }, {
      _sourceTableIndexes: [0, 1],
    })

    expect(result.table).toBeNull()
    expect(result.reason).toContain('合并续表')
  })

  it('拒绝 workpaper 业务键子表投影', () => {
    const result = resolveNoteStructureEditState({
      _source: 'workpaper',
      sub_table_data: { detail: [] },
    }, {
      _source_sub_table_key: 'detail',
      _sourceTableIndexes: [0],
    })

    expect(result.table).toBeNull()
    expect(result.reason).toContain('业务键子表')
  })

  it('拒绝缺少稳定源索引的投影', () => {
    const result = resolveNoteStructureEditState({}, { headers: [], rows: [] })
    expect(result.table).toBeNull()
    expect(result.reason).toContain('缺少稳定的源结构')
  })
})
