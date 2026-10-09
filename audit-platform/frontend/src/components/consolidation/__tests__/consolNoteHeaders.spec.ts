import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { noteBodyRows, noteHeaderColumns, noteHeaderRows, type NoteHeaderColumn } from '../composables/consolNoteHeaders'

export function realSection(standard: string, id = '五-5-2') {
  const all = JSON.parse(readFileSync(resolve(process.cwd(), `../../backend/data/consol_note_sections_${standard}.json`), 'utf8'))
  return all.find((s: any) => s.section_id === id)
}
const leaves = (cols: NoteHeaderColumn[]): NoteHeaderColumn[] => cols.flatMap((c) => c.children ? leaves(c.children) : [c])

describe('CP04 real header contracts', () => {
  it('SOE retains three levels despite top-level groups and malformed flattened book-value suffix', () => {
    const sec = realSection('soe')
    const cols = noteHeaderColumns(sec)
    expect(cols.map((c) => c.label)).toEqual(['类  别', '期末数', '期初数'])
    expect(cols[1].children?.map((c) => c.label)).toEqual(['账面余额', '坏账准备', '账面价值'])
    expect(leaves(cols).map((c) => c.colIndex)).toEqual(Array.from({ length: 11 }, (_, i) => i))
    expect(leaves(cols)[5]).toEqual({ label: '账面价值', colIndex: 5 })
    expect(leaves(cols).filter((c) => c.label === '金额').map((c) => c.colIndex)).toEqual([1, 3, 6, 8])
  })

  it.each(['五-5-2', '五-5-3'])('listed %s hides only explicitly configured storage rows, keeps blank business rows', (id) => {
    const sec = realSection('listed', id)
    const before = JSON.stringify(sec)
    const cols = noteHeaderColumns(sec)
    const body = noteBodyRows(sec.rows, sec._header_row_indexes)
    expect(leaves(cols).map((c) => c.colIndex)).toEqual([0, 1, 2, 3, 4, 5])
    expect(cols[1].children?.[2]).toEqual({ label: '账面价值', colIndex: 5 })
    expect(body).toEqual(sec.rows.slice(2))
    expect(body.length).toBe(9)
    expect(JSON.stringify(sec)).toBe(before)
  })

  it('never infers header rows from business labels; validates invalid spans', () => {
    const rows = [['类别', '100'], ['金额', '200'], ['', '']]
    expect(noteBodyRows(rows)).toEqual(rows)
    expect(() => noteHeaderColumns({ headers: ['a', 'b'], header_rows: [[{ text: '', colspan: 1, rowspan: 1 }]] })).toThrow('覆盖')
    expect(() => noteHeaderColumns({ headers: ['a'], header_rows: [[{ text: '', colspan: 2, rowspan: 1 }]] })).toThrow('跨度')
    expect(noteHeaderRows({ headers: ['项目', '本期/金额'], _column_groups: [{ group: '本期', start: 1, span: 1 }] })[1][0].text).toBe('金额')
  })
})

describe('CP04 fail-closed projections', () => {
  it.each(['soe', 'listed'])('all %s source sections keep every leaf column and do not mutate', (standard) => {
    const all = JSON.parse(readFileSync(resolve(process.cwd(), `../../backend/data/consol_note_sections_${standard}.json`), 'utf8'))
    for (const sec of all) {
      const before = JSON.stringify(sec)
      expect(leaves(noteHeaderColumns(sec)).map((c) => c.colIndex), sec.section_id).toEqual(sec.headers.map((_: string, c: number) => c))
      const body = noteBodyRows(sec.rows, sec._header_row_indexes)
      expect(body.length + (sec._header_row_indexes?.length || 0)).toBe(sec.rows.length)
      expect(JSON.stringify(sec)).toBe(before)
    }
  })

  it('explicit normalized header wins over malformed legacy multi_header', () => {
    const config = { headers: ['金额'], multi_header: [['旧头']], header_rows: [[{ text: '准确头', colspan: 1, rowspan: 1 }]] }
    expect(noteHeaderColumns(config)).toEqual([{ label: '准确头', colIndex: 0 }])
  })

  it.each([{ indexes: [1] }, { indexes: [-1] }, { indexes: [0.1] }, { indexes: [0, 0] }])('invalid header row indexes $indexes cannot silently hide business rows', ({ indexes }) => {
    expect(() => noteBodyRows([['业务']], indexes)).toThrow('索引')
  })

  it('blank vertically-covered headers still expose every real column', () => {
    expect(leaves(noteHeaderColumns({ headers: ['项目', '', ''], multi_header: [['项目', '期末', ''], ['', '', '']] })).map((c) => c.colIndex)).toEqual([0, 1, 2])
  })
})