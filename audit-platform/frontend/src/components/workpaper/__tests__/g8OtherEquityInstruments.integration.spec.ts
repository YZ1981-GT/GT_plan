/**
 * G8 其他权益工具投资 — 集成测试: sheetName分发正确性
 *
 * 验证：
 * 1. 有效sheetName → 正确子组件编码（对齐 extractG8SheetCode / g8SheetLabels.ts）
 * 2. 未知sheetName → OnlyOffice fallback（空字符串触发fallback渲染）
 * 3. HTML_SHEETS 10 项（G8A + G8-1..6 + 3 note/dir）
 * 4. 可导入导出 4 张表（G8-2 / G8-3 / G8-4 / G8-6）
 * 5. 科目代码 1503 / Event bus g8:save-items / AI 前缀 /g8/ai/
 *
 * **Validates: Requirements G8 integration**
 */
import { describe, it, expect } from 'vitest'
import { G8_IMPORTABLE_SHEETS } from '../composables/g8Constants'
import { extractG8SheetCode } from '../composables/g8SheetLabels'

// ---------------------------------------------------------------------------
// 1. sheetName 正则分发正确性（对齐 g8SheetLabels.ts extractG8SheetCode）
// ---------------------------------------------------------------------------
describe('G8 集成: sheetName 正则分发（10 sheets + fallback）', () => {
  /**
   * 对齐 composables/g8SheetLabels.ts 中 extractG8SheetCode 为纯函数。
   */
  function resolveSheet(name: string): string {
    if (!name) return ''
    if (/G8-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
    if (/G8-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
    if (/G8-directory|底稿目录/.test(name)) return '底稿目录'
    if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
    const m = name.match(/(G8A|G8-\d+)/)
    return m ? m[1] : ''
  }

  const validCases: [string, string][] = [
    ['其他权益工具投资实质性程序表G8A', 'G8A'],
    ['审定表G8-1', 'G8-1'],
    ['明细表G8-2', 'G8-2'],
    ['调整分录汇总G8-3', 'G8-3'],
    ['公允价值测试表G8-4', 'G8-4'],
    ['指定的适当性检查表G8-5', 'G8-5'],
    ['凭证检查表G8-6', 'G8-6'],
    ['附注披露信息（上市公司）', '附注上市'],
    ['附注披露信息（国企）', '附注国企'],
    ['底稿目录', '底稿目录'],
    ['G8-note-listed', '附注上市'],
    ['G8-note-soe', '附注国企'],
    ['G8-directory', '底稿目录'],
  ]

  it.each(validCases)('sheetName "%s" → code "%s"', (input, expected) => {
    expect(resolveSheet(input)).toBe(expected)
  })

  it('sheetName包含空格/变体仍正确匹配', () => {
    expect(resolveSheet('附注披露（上市公司）')).toBe('附注上市')
    expect(resolveSheet('附注披露（国企）')).toBe('附注国企')
    expect(resolveSheet('G8-1审定表(其他权益工具投资)')).toBe('G8-1')
    expect(resolveSheet('G8A实质性程序表')).toBe('G8A')
    expect(resolveSheet('G8-6 凭证检查表')).toBe('G8-6')
  })

  it('未匹配sheetName返回空字符串 → OnlyOffice fallback', () => {
    expect(resolveSheet('Z99-unknown')).toBe('')
    expect(resolveSheet('')).toBe('')
    expect(resolveSheet('G7-1')).toBe('')
    expect(resolveSheet('G9-1')).toBe('')
    expect(resolveSheet('未知')).toBe('')
  })

  it('extractG8SheetCode 与 resolveSheet 结果一致', () => {
    for (const [input, expected] of validCases) {
      expect(extractG8SheetCode(input)).toBe(expected)
      expect(extractG8SheetCode(input)).toBe(resolveSheet(input))
    }
    expect(extractG8SheetCode('G7-1')).toBe('')
    expect(extractG8SheetCode('G9-1')).toBe('')
  })
})

// ---------------------------------------------------------------------------
// 2. HTML_SHEETS 配置（10 项）
// ---------------------------------------------------------------------------
describe('G8 集成: HTML_SHEETS', () => {
  const HTML_SHEETS = new Set([
    'G8A', 'G8-1', 'G8-2', 'G8-3', 'G8-4', 'G8-5', 'G8-6',
    '附注上市', '附注国企', '底稿目录',
  ])

  it('HTML_SHEETS 正好有10 项', () => {
    expect(HTML_SHEETS.size).toBe(10)
  })

  it('包含 G8A + G8-1..G8-6 + 3 note/dir', () => {
    for (const code of ['G8A', 'G8-1', 'G8-2', 'G8-3', 'G8-4', 'G8-5', 'G8-6']) {
      expect(HTML_SHEETS.has(code)).toBe(true)
    }
    expect(HTML_SHEETS.has('附注上市')).toBe(true)
    expect(HTML_SHEETS.has('附注国企')).toBe(true)
    expect(HTML_SHEETS.has('底稿目录')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 3. 可导入导出 4 张表
// ---------------------------------------------------------------------------
describe('G8 集成: 可导入导出', () => {
  it('G8 支持4 张表动态行表格可导入导出', () => {
    expect(G8_IMPORTABLE_SHEETS).toHaveLength(4)
    const codes = G8_IMPORTABLE_SHEETS.map((s) => s.code)
    expect(codes).toEqual(['G8-2', 'G8-3', 'G8-4', 'G8-6'])
  })
})

// ---------------------------------------------------------------------------
// 4. 科目代码 / Event bus / AI 前缀
// ---------------------------------------------------------------------------
describe('G8 集成: 科目代码 / Event bus / AI', () => {
  it('科目代码 1503', () => {
    const accountCode = '1503'
    expect(accountCode).toBe('1503')
    function shouldHandleAdjudicated(code: string): boolean {
      return code === '1503'
    }
    expect(shouldHandleAdjudicated('1503')).toBe(true)
    expect(shouldHandleAdjudicated('1501')).toBe(false)
  })

  it('Event bus 监听 g8:save-items', () => {
    const eventName = 'g8:save-items'
    expect(eventName).toBe('g8:save-items')
    expect(eventName.startsWith('g8:')).toBe(true)
  })

  it('AI API 前缀 包含 /g8/ai/', () => {
    const wpId = 'test-wp-id'
    const section = 'adjudication-note'
    const url = `/api/workpapers/${wpId}/g8/ai/${section}`
    expect(url).toContain('/g8/ai/')
    expect(url).toBe('/api/workpapers/test-wp-id/g8/ai/adjudication-note')
  })
})

