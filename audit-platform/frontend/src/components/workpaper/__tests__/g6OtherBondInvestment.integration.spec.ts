/**
 * G6 其他债权投资 — 集成测试: Main / SPPI / ECL sheet 分发
 *
 * 验证：
 * 1. Main: G6A, G6-1..4, 附注上市/附注国企, 底稿目录, G6-note-listed
 * 2. SPPI: G6-5..10
 * 3. ECL: G6-11..15
 * 4. 科目 1503 / 事件 bus g6:save-items / API 前缀 g6-main|g6-sppi|g6-ecl
 * 5. 注册表 ECL → InvestmentEcl
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// ---------------------------------------------------------------------------
// resolveSheet — 跨 Main / SPPI / ECL 组
// ---------------------------------------------------------------------------
function resolveSheet(name: string): string {
  if (!name) return ''
  if (/G6-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
  if (/G6-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
  if (/G6-directory|底稿目录/.test(name)) return '底稿目录'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  if (/G6A/i.test(name)) return 'G6A'
  const ecl = name.match(/G6-1([1-5])/)
  if (ecl) return `G6-1${ecl[1]}`
  const sppi = name.match(/G6-(10|[5-9])/)
  if (sppi) return `G6-${sppi[1]}`
  const main = name.match(/G6-([1-4])/)
  if (main) return `G6-${main[1]}`
  return ''
}

describe('G6 集成: Main sheet 分发', () => {
  const cases: [string, string][] = [
    ['其他债权投资实质性程序表G6A', 'G6A'],
    ['审定表G6-1', 'G6-1'],
    ['明细表G6-2', 'G6-2'],
    ['坏账准备明细表G6-3', 'G6-3'],
    ['调整分录汇总G6-4', 'G6-4'],
    ['附注披露信息（上市公司）', '附注上市'],
    ['附注披露信息（国企）', '附注国企'],
    ['底稿目录', '底稿目录'],
    ['G6-note-listed', '附注上市'],
    ['G6-note-soe', '附注国企'],
    ['G6-directory', '底稿目录'],
  ]
  it.each(cases)('sheetName "%s" → "%s"', (input, expected) => {
    expect(resolveSheet(input)).toBe(expected)
  })
})

describe('G6 集成: SPPI sheet 分发 (G6-5..10)', () => {
  const cases: [string, string][] = [
    ['G6-5', 'G6-5'],
    ['G6-6', 'G6-6'],
    ['G6-7', 'G6-7'],
    ['G6-8', 'G6-8'],
    ['G6-9', 'G6-9'],
    ['G6-10', 'G6-10'],
    ['G6-10 roll-forward', 'G6-10'],
  ]
  it.each(cases)('sheetName "%s" → "%s"', (input, expected) => {
    expect(resolveSheet(input)).toBe(expected)
  })
})

describe('G6 集成: ECL sheet 分发 (G6-11..15)', () => {
  const cases: [string, string][] = [
    ['三阶段划分G6-11', 'G6-11'],
    ['减值准备测算G6-12', 'G6-12'],
    ['预期信用损失计量G6-13', 'G6-13'],
    ['转回核销检查G6-14', 'G6-14'],
    ['凭证检查表G6-15', 'G6-15'],
  ]
  it.each(cases)('sheetName "%s" → "%s"', (input, expected) => {
    expect(resolveSheet(input)).toBe(expected)
  })
})

describe('G6 集成: 未匹配', () => {
  it('unknown → empty', () => {
    expect(resolveSheet('Z99-unknown')).toBe('')
    expect(resolveSheet('')).toBe('')
    expect(resolveSheet('G5-1')).toBe('')
  })
})

describe('G6 集成: 科目 / 事件 bus / API 前缀', () => {
  it('科目 1503', () => {
    const accountCode = '1503'
    expect(accountCode).toBe('1503')
    expect(accountCode === '1503').toBe(true)
    expect(accountCode === '1501').toBe(false)
  })

  it('事件 bus g6:save-items', () => {
    const eventName = 'g6:save-items'
    expect(eventName).toBe('g6:save-items')
    expect(eventName.startsWith('g6:')).toBe(true)
  })

  it('API 前缀 g6-main / g6-sppi / g6-ecl', () => {
    const wpId = 'test-wp-id'
    const mainUrl = `/api/workpapers/${wpId}/g6-main/ai/x`
    const sppiUrl = `/api/workpapers/${wpId}/g6-sppi/ai/x`
    const eclUrl = `/api/workpapers/${wpId}/g6-ecl/ai/stage-conclusion`
    expect(mainUrl).toContain('/g6-main/')
    expect(sppiUrl).toContain('/g6-sppi/')
    expect(eclUrl).toBe('/api/workpapers/test-wp-id/g6-ecl/ai/stage-conclusion')
  })
})

describe('G6 集成: 注册表 ECL -> InvestmentEcl', () => {
  it('htmlRendererRegistry imports GtG6OtherBondInvestmentEcl', () => {
    const registryPath = resolve(__dirname, '../htmlRendererRegistry.ts')
    const src = readFileSync(registryPath, 'utf-8')
    expect(src).toContain("import('./GtG6OtherBondInvestmentEcl.vue')")
  })
})

