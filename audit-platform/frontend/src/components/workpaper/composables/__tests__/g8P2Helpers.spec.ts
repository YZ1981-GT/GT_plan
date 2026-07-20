/**
 * matchG8InvesteeKey / collectG8SheetConclusions
 */
import { describe, it, expect } from 'vitest'
import { matchG8InvesteeKey, matchG8Investee } from '../g8CrossHelpers'
import {
  collectG8SheetConclusions,
  summarizeG8Conclusions,
  inferG8ConclusionOption,
} from '../g8Conclusion'

describe('matchG8InvesteeKey', () => {
  it('剥离公司后缀与空白', () => {
    expect(matchG8InvesteeKey('XX科技有限公司')).toBe(matchG8InvesteeKey('XX科技'))
    expect(matchG8InvesteeKey('甲 乙 股份有限公司')).toBe(matchG8InvesteeKey('甲乙'))
  })

  it('matchG8Investee 互相包含', () => {
    expect(matchG8Investee('XX科技', 'XX科技有限公司')).toBe(true)
    expect(matchG8Investee('甲公司', '乙公司')).toBe(false)
  })
})

describe('collectG8SheetConclusions', () => {
  it('汇总并取最差口径 C', () => {
    const m = new Map<string, any>([
      ['G8-1-audit-conclusion', { remark: 'A、未见异常' }],
      ['G8-3-audit-conclusion', { remark: 'C、范围受限' }],
      ['G8-3-audit-conclusion-option', { conclusion: 'C' }],
    ])
    const items = collectG8SheetConclusions(m)
    expect(items.find((i) => i.code === 'G8-1')?.option).toBe('A')
    expect(items.find((i) => i.code === 'G8-3')?.option).toBe('C')
    expect(summarizeG8Conclusions(items).worst).toBe('C')
  })

  it('infer 兼容纯文本', () => {
    expect(inferG8ConclusionOption('B、除调整外未见异常')).toBe('B')
  })
})
