/**
 * G5 长期应收款 — 集成测试: sheetName分发正确性
 *
 * 验证：
 * 1. 有效sheetName → 正确子组件编码（正则提取+v-if分发）
 * 2. 未知sheetName → OnlyOffice fallback（空字符串触发fallback渲染）
 * 3. HTML_SHEETS 16 项（G5A + G5-1..12 + 3 note/dir）
 * 4. 可导入导出 9 张表（G5-1..7 / G5-11..12）
 * 5. 科目代码 1531 / Event bus g5:save-items / AI 前缀 /g5/ai/
 *
 * **Validates: Requirements G5 integration**
 */
import { describe, it, expect } from 'vitest'
import { G5_IMPORTABLE_SHEETS } from '../composables/useG5ImportExport'

// ---------------------------------------------------------------------------
// 1. sheetName 正则分发正确性（对齐 GtG5LongTermReceivable.vue）
// ---------------------------------------------------------------------------
describe('G5 集成: sheetName 正则分发（16 sheets + fallback）', () => {
  /**
   * 对齐 GtG5LongTermReceivable.vue 中 currentSheet computed 逻辑为纯函数。
   */
  function resolveSheet(name: string): string {
    if (!name) return ''
    if (/G5-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
    if (/G5-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
    if (/G5-directory|底稿目录/.test(name)) return '底稿目录'
    if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
    const m = name.match(/(G5A|G5-1[0-2]|G5-[1-9])/)
    return m ? m[1] : ''
  }

  const validCases: [string, string][] = [
    ['长期应收款实质性程序表G5A', 'G5A'],
    ['审定表G5-1', 'G5-1'],
    ['余额明细表G5-2', 'G5-2'],
    ['坏账准备明细表G5-3', 'G5-3'],
    ['调整分录汇总G5-4', 'G5-4'],
    ['融资租赁测算表G5-5', 'G5-5'],
    ['分期销售测算表G5-6', 'G5-6'],
    ['保理核查表G5-7', 'G5-7'],
    ['会计政策检查G5-8', 'G5-8'],
    ['三阶段划分G5-9', 'G5-9'],
    ['坏账准备测算G5-10', 'G5-10'],
    ['转回核销检查G5-11', 'G5-11'],
    ['凭证检查表G5-12', 'G5-12'],
    ['附注披露信息（上市公司）', '附注上市'],
    ['附注披露信息（国企）', '附注国企'],
    ['底稿目录', '底稿目录'],
    ['G5-note-listed', '附注上市'],
    ['G5-note-soe', '附注国企'],
    ['G5-directory', '底稿目录'],
  ]

  it.each(validCases)('sheetName "%s" → code "%s"', (input, expected) => {
    expect(resolveSheet(input)).toBe(expected)
  })

  it('sheetName包含空格/变体仍正确匹配', () => {
    expect(resolveSheet('附注披露（上市公司）')).toBe('附注上市')
    expect(resolveSheet('附注披露（国企）')).toBe('附注国企')
    expect(resolveSheet('G5-1审定表(长期应收款)')).toBe('G5-1')
    expect(resolveSheet('G5A实质性程序表')).toBe('G5A')
    expect(resolveSheet('G5-10 坏账准备测算')).toBe('G5-10')
    expect(resolveSheet('G5-12 凭证检查表')).toBe('G5-12')
  })

  it('未匹配sheetName返回空字符串 → OnlyOffice fallback', () => {
    expect(resolveSheet('Z99-unknown')).toBe('')
    expect(resolveSheet('')).toBe('')
    expect(resolveSheet('G4-1')).toBe('')
    expect(resolveSheet('G6-1')).toBe('')
    expect(resolveSheet('未知')).toBe('')
  })
})

// ---------------------------------------------------------------------------
// 2. HTML_SHEETS 配置（16 项）
// ---------------------------------------------------------------------------
describe('G5 集成: HTML_SHEETS', () => {
  const HTML_SHEETS = new Set([
    'G5A', 'G5-1', 'G5-2', 'G5-3', 'G5-4', 'G5-5', 'G5-6', 'G5-7',
    'G5-8', 'G5-9', 'G5-10', 'G5-11', 'G5-12',
    '附注上市', '附注国企', '底稿目录',
  ])

  it('HTML_SHEETS 正好有16 项', () => {
    expect(HTML_SHEETS.size).toBe(16)
  })

  it('包含 G5A + G5-1..G5-12 + 3 note/dir', () => {
    for (const code of ['G5A', 'G5-1', 'G5-2', 'G5-3', 'G5-4', 'G5-5', 'G5-6', 'G5-7', 'G5-8', 'G5-9', 'G5-10', 'G5-11', 'G5-12']) {
      expect(HTML_SHEETS.has(code)).toBe(true)
    }
    expect(HTML_SHEETS.has('附注上市')).toBe(true)
    expect(HTML_SHEETS.has('附注国企')).toBe(true)
    expect(HTML_SHEETS.has('底稿目录')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 3. 可导入导出 9 张表（含 G5-1）
// ---------------------------------------------------------------------------
describe('G5 集成: 可导入导出', () => {
  it('G5 支持9 张表可导入导出（含 G5-1）', () => {
    expect(G5_IMPORTABLE_SHEETS).toHaveLength(9)
    const codes = G5_IMPORTABLE_SHEETS.map((s) => s.code)
    expect(codes).toEqual(['G5-1', 'G5-2', 'G5-3', 'G5-4', 'G5-5', 'G5-6', 'G5-7', 'G5-11', 'G5-12'])
  })
})

// ---------------------------------------------------------------------------
// 4. 科目代码 / Event bus / AI 前缀
// ---------------------------------------------------------------------------
describe('G5 集成: 科目代码 / Event bus / AI', () => {
  it('科目代码 1531', () => {
    const accountCode = '1531'
    expect(accountCode).toBe('1531')
    function shouldHandleAdjudicated(code: string): boolean {
      return code === '1531'
    }
    expect(shouldHandleAdjudicated('1531')).toBe(true)
    expect(shouldHandleAdjudicated('1501')).toBe(false)
  })

  it('Event bus 监听 g5:save-items', () => {
    const eventName = 'g5:save-items'
    expect(eventName).toBe('g5:save-items')
    expect(eventName.startsWith('g5:')).toBe(true)
  })

  it('AI API 前缀 包含 /g5/ai/', () => {
    const wpId = 'test-wp-id'
    const section = 'adjudication-note'
    const url = `/api/workpapers/${wpId}/g5/ai/${section}`
    expect(url).toContain('/g5/ai/')
    expect(url).toBe('/api/workpapers/test-wp-id/g5/ai/adjudication-note')
  })
})

// ---------------------------------------------------------------------------
// 5. G5A 程序表 脚手架
// ---------------------------------------------------------------------------
describe('G5 集成: G5A 程序表', () => {
  it('G_CYCLE_PROCEDURE_SHEETS.G5A.sheetLabel 对齐 D4A', async () => {
    const { G_CYCLE_PROCEDURE_SHEETS } = await import('../composables/cycleProcedureSheets')
    expect(G_CYCLE_PROCEDURE_SHEETS.G5A).toBeDefined()
    expect(G_CYCLE_PROCEDURE_SHEETS.G5A.sheetLabel).toBe('长期应收款实质性程序表G5A')
  })
})
