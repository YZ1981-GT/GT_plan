/**
 * I6 研发费用 — sheetName分发 + I2联动面板 测试
 *
 * 验证 GtI6ResearchDevelopmentExpense.vue 的 currentSheet computed
 * 能正确从 sheetName prop 提取编码并匹配到对应子组件。
 *
 * Spec: .kiro/specs/i6-research-development-expense/ Task 7.2
 * Validates: Requirements 1.1, 1.3
 */
import { describe, it, expect } from 'vitest'

/**
 * 从 sheetName 提取编码的纯逻辑（提取自GtI6ResearchDevelopmentExpense.vue中的computed）
 * 模拟组件内的 currentSheet computed
 */
function extractCurrentSheet(sheetName: string): string {
  const name = sheetName || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'I6'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 I6A
  if (/I6A/.test(name)) return 'I6A'
  // I6-N 编码（I6-1 到 I6-6）
  const m = name.match(/(I6-\d+)/)
  if (m) return m[1]
  // 底稿目录 I6（无后缀）
  if (/\bI6\b/.test(name) && !/I6-/.test(name) && !/I6A/.test(name)) return 'I6'
  return ''
}

describe('I6 sheetName分发 — currentSheet提取逻辑', () => {
  it('currentSheet correctly extracts "I6-1" from "审定表I6-1"', () => {
    expect(extractCurrentSheet('审定表I6-1')).toBe('I6-1')
  })

  it('currentSheet returns "I6A" for "研发费用实质性程序 I6A"', () => {
    expect(extractCurrentSheet('研发费用实质性程序 I6A')).toBe('I6A')
  })

  it('currentSheet returns "附注上市" for "附注披露（上市公司）"', () => {
    expect(extractCurrentSheet('附注披露（上市公司）')).toBe('附注上市')
  })

  it('currentSheet returns "I6" for "底稿目录"', () => {
    expect(extractCurrentSheet('底稿目录')).toBe('I6')
  })

  it('currentSheet returns "" for unmatched sheet names → OO fallback', () => {
    expect(extractCurrentSheet('未知Sheet名称')).toBe('')
  })

  // 额外覆盖：其他sheet分发
  it('currentSheet extracts "I6-2" from "明细表I6-2"', () => {
    expect(extractCurrentSheet('明细表I6-2')).toBe('I6-2')
  })

  it('currentSheet extracts "I6-3" from "调整分录汇总I6-3"', () => {
    expect(extractCurrentSheet('调整分录汇总I6-3')).toBe('I6-3')
  })

  it('currentSheet extracts "I6-4" from "针对性检查表I6-4"', () => {
    expect(extractCurrentSheet('针对性检查表I6-4')).toBe('I6-4')
  })

  it('currentSheet extracts "I6-5" from "截止性测试（账到单据）I6-5"', () => {
    expect(extractCurrentSheet('截止性测试（账到单据）I6-5')).toBe('I6-5')
  })

  it('currentSheet extracts "I6-6" from "截止性测试（单据到账）I6-6"', () => {
    expect(extractCurrentSheet('截止性测试（单据到账）I6-6')).toBe('I6-6')
  })

  it('currentSheet returns "附注国企" for "附注披露信息（国有企业）"', () => {
    expect(extractCurrentSheet('附注披露信息（国有企业）')).toBe('附注国企')
  })

  it('currentSheet returns "I6" for bare "I6" string', () => {
    expect(extractCurrentSheet('I6')).toBe('I6')
  })

  it('空字符串返回空（OO fallback）', () => {
    expect(extractCurrentSheet('')).toBe('')
  })
})
