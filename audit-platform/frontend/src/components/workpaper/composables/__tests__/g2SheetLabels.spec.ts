import { describe, it, expect } from 'vitest'
import {
  extractG2SheetCode,
  resolveG2SheetLabel,
  G2_SHEET_LABEL_MAP,
  buildG2FallbackSheets,
  G2_DIRECTORY_ROWS,
} from '../g2SheetLabels'

describe('extractG2SheetCode', () => {
  it('识别底稿目录', () => {
    expect(extractG2SheetCode('底稿目录')).toBe('底稿目录')
    expect(extractG2SheetCode('G2-底稿目录')).toBe('底稿目录')
  })

  it('识别 G2A / G2-1', () => {
    expect(extractG2SheetCode('应收利息实质性程序表G2A')).toBe('G2A')
    expect(extractG2SheetCode('审定表G2-1')).toBe('G2-1')
  })

  it('识别附注披露', () => {
    expect(extractG2SheetCode('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractG2SheetCode('附注披露信息（国企）')).toBe('附注国企')
    expect(extractG2SheetCode('G2-note-listed')).toBe('附注上市')
  })
})

describe('resolveG2SheetLabel', () => {
  it('从 availableSheets 按末尾编码匹配', () => {
    const sheets = [
      { sheet_name: '明细表G2-2' },
      { sheet_name: '审定表G2-1' },
      { sheet_name: '底稿目录' },
    ]
    expect(resolveG2SheetLabel('G2-2', sheets)).toBe('明细表G2-2')
    expect(resolveG2SheetLabel('底稿目录', sheets)).toBe('底稿目录')
  })

  it('无 availableSheets 时用默认映射', () => {
    expect(resolveG2SheetLabel('G2-1')).toBe(G2_SHEET_LABEL_MAP['G2-1'])
  })
})

describe('buildG2FallbackSheets / DIRECTORY_ROWS', () => {
  it('兜底 sheets 不含目录自身', () => {
    const sheets = buildG2FallbackSheets()
    expect(sheets.length).toBeGreaterThan(0)
    expect(sheets.every((s) => !s.sheet_name.includes('底稿目录'))).toBe(true)
  })

  it('目录清单覆盖核心索引', () => {
    const codes = G2_DIRECTORY_ROWS.map((r) => r.indexCode)
    expect(codes).toContain('G2A')
    expect(codes).toContain('G2-1')
    expect(codes).toContain('G2-8')
  })
})
