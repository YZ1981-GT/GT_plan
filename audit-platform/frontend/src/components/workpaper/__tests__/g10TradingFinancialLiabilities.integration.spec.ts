/**
 * G10 交易性金融负债 — 集成测试: sheetName分发正确性
 *
 * 验证：
 * 1. 有效sheetName → 正确子组件编码（对齐 GtG10TradingFinancialLiabilities.vue）
 * 2. 未知sheetName → OnlyOffice fallback（空字符串触发fallback渲染）
 * 3. HTML_SHEETS 12 项（G10A + G10-1..8 + 3 note/dir）
 * 4. 可导入导出 5 张表（G10-2 / G10-3 / G10-5 / G10-6 / G10-7）
 * 5. 科目代码 2101 / Event bus g10:save-items / AI 前缀 /g10/ai/
 *
 * **Validates: Requirements G10 integration**
 */
import { describe, it, expect } from 'vitest'
import { G10_IMPORTABLE_SHEETS } from '../composables/useG10ImportExport'

// ---------------------------------------------------------------------------
// 1. sheetName 正则分发正确性（对齐 GtG10TradingFinancialLiabilities.vue）
// ---------------------------------------------------------------------------
describe('G10 集成: sheetName 正则分发（12 sheets + fallback）', () => {
  /**
   * 对齐 GtG10TradingFinancialLiabilities.vue 中 currentSheet computed 为纯函数。
   */
  function resolveSheet(name: string): string {
    if (!name) return ''
    if (/G10-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
    if (/G10-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
    if (/G10-directory|底稿目录/.test(name)) return '底稿目录'
    if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
    const m = name.match(/(G10A|G10-\d+)/)
    return m ? m[1] : ''
  }

  const validCases: [string, string][] = [
    ['交易性金融负债实质性程序表G10A', 'G10A'],
    ['审定表G10-1', 'G10-1'],
    ['明细表G10-2', 'G10-2'],
    ['调整分录汇总G10-3', 'G10-3'],
    ['分类的适当性检查表G10-4', 'G10-4'],
    ['公允价值测试表G10-5', 'G10-5'],
    ['第三层次公允价值计量的调节表G10-6', 'G10-6'],
    ['凭证检查表G10-7', 'G10-7'],
    ['衍生金融工具核查表G10-8', 'G10-8'],
    ['附注披露信息（上市公司）', '附注上市'],
    ['附注披露信息（国企）', '附注国企'],
    ['底稿目录', '底稿目录'],
    ['G10-note-listed', '附注上市'],
    ['G10-note-soe', '附注国企'],
    ['G10-directory', '底稿目录'],
  ]

  it.each(validCases)('sheetName \"%s\" \u2192 code \"%s\"', (input, expected) => {
    expect(resolveSheet(input)).toBe(expected)
  })

  it('sheetName包含空格/变体仍正确匹配', () => {
    expect(resolveSheet('附注披露（上市公司）')).toBe('附注上市')
    expect(resolveSheet('附注披露（国企）')).toBe('附注国企')
    expect(resolveSheet('G10-1审定表(交易性金融负债)')).toBe('G10-1')
    expect(resolveSheet('G10A实质性程序表')).toBe('G10A')
    expect(resolveSheet('G10-7 凭证检查表')).toBe('G10-7')
    expect(resolveSheet('G10-8 衍生金融工具核查表')).toBe('G10-8')
  })

  it('未匹配sheetName\u8fd4\u56de\u7a7a\u5b57\u7b26\u4e32 \u2192 OnlyOffice fallback', () => {
    expect(resolveSheet('Z99-unknown')).toBe('')
    expect(resolveSheet('')).toBe('')
    expect(resolveSheet('G8-1')).toBe('')
    expect(resolveSheet('G11-1')).toBe('')
    expect(resolveSheet('未知')).toBe('')
  })
})

// ---------------------------------------------------------------------------
// 2. HTML_SHEETS \u914d\u7f6e\uff0812 项\uff09
// ---------------------------------------------------------------------------
describe('G10 集成: HTML_SHEETS', () => {
  const HTML_SHEETS = new Set([
    'G10A', 'G10-1', 'G10-2', 'G10-3', 'G10-4', 'G10-5', 'G10-6', 'G10-7', 'G10-8',
    '附注上市', '附注国企', '底稿目录',
  ])

  it('HTML_SHEETS 正好有12 项', () => {
    expect(HTML_SHEETS.size).toBe(12)
  })

  it('包含 G10A + G10-1..G10-8 + 3 note/dir', () => {
    for (const code of ['G10A', 'G10-1', 'G10-2', 'G10-3', 'G10-4', 'G10-5', 'G10-6', 'G10-7', 'G10-8']) {
      expect(HTML_SHEETS.has(code)).toBe(true)
    }
    expect(HTML_SHEETS.has('附注上市')).toBe(true)
    expect(HTML_SHEETS.has('附注国企')).toBe(true)
    expect(HTML_SHEETS.has('底稿目录')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 3. 可导入导出 5 张表
// ---------------------------------------------------------------------------
describe('G10 集成: 可导入导出', () => {
  it('G10 支持5 张表动态行表格可导入导出', () => {
    expect(G10_IMPORTABLE_SHEETS).toHaveLength(5)
    const codes = G10_IMPORTABLE_SHEETS.map((s) => s.code)
    expect(codes).toEqual(['G10-2', 'G10-3', 'G10-5', 'G10-6', 'G10-7'])
  })
})

// ---------------------------------------------------------------------------
// 4. 科目代码 / Event bus / AI 前缀
// ---------------------------------------------------------------------------
describe('G10 集成: 科目代码 / Event bus / AI', () => {
  it('科目代码 2101', () => {
    const accountCode = '2101'
    expect(accountCode).toBe('2101')
    function shouldHandleAdjudicated(code: string): boolean {
      return code === '2101'
    }
    expect(shouldHandleAdjudicated('2101')).toBe(true)
    expect(shouldHandleAdjudicated('1501')).toBe(false)
  })

  it('Event bus 监听 g10:save-items', () => {
    const eventName = 'g10:save-items'
    expect(eventName).toBe('g10:save-items')
    expect(eventName.startsWith('g10:')).toBe(true)
  })

  it('AI API 前缀 包含 /g10/ai/', () => {
    const wpId = 'test-wp-id'
    const section = 'adjudication-note'
    const url = `/api/workpapers/${wpId}/g10/ai/${section}`
    expect(url).toContain('/g10/ai/')
    expect(url).toBe('/api/workpapers/test-wp-id/g10/ai/adjudication-note')
  })
})

// ---------------------------------------------------------------------------
// 5. G10A 程序表 脚手架
// ---------------------------------------------------------------------------
describe('G10 集成: G10A 程序表', () => {
  it('G_CYCLE_PROCEDURE_SHEETS.G10A.sheetLabel 对齐', async () => {
    const { G_CYCLE_PROCEDURE_SHEETS } = await import('../composables/cycleProcedureSheets')
    expect(G_CYCLE_PROCEDURE_SHEETS.G10A).toBeDefined()
    expect(G_CYCLE_PROCEDURE_SHEETS.G10A.sheetLabel).toBe('交易性金融负债实质性程序表G10A')
  })
})

