import { describe, expect, it } from 'vitest'
import {
  applyG10ConclusionTemplate,
  collectG10SheetConclusions,
  inferG10ConclusionOption,
  summarizeG10Conclusions,
} from '../g10Conclusion'

describe('g10Conclusion', () => {
  it('inferG10ConclusionOption 识别 A/B/C', () => {
    expect(inferG10ConclusionOption('A、未见异常')).toBe('A')
    expect(inferG10ConclusionOption('B、除上述事项外')).toBe('B')
    expect(inferG10ConclusionOption('C、不可确认')).toBe('C')
    expect(inferG10ConclusionOption('')).toBe('')
  })

  it('applyG10ConclusionTemplate 空文本填入模板', () => {
    expect(applyG10ConclusionTemplate('A', '')).toMatch(/^A、/)
  })

  it('collectG10SheetConclusions 汇总各子表', () => {
    const m = new Map<string, any>([
      ['G10-adj-conclusion', { conclusion: 'A、审定无异常' }],
      ['G10-fv-test-conclusion', { conclusion: 'B、除公允差异外' }],
    ])
    const items = collectG10SheetConclusions(m)
    expect(items.find((i) => i.code === 'G10-1')?.option).toBe('A')
    expect(items.find((i) => i.code === 'G10-5')?.option).toBe('B')
    expect(items.find((i) => i.code === 'G10-3')?.filled).toBe(false)
  })

  it('summarizeG10Conclusions C 优先于 B/A', () => {
    const items = collectG10SheetConclusions(new Map([
      ['G10-adj-conclusion', { conclusion: 'A、ok' }],
      ['G10-derivative-conclusion', { conclusion: 'C、不可确认' }],
    ]))
    expect(summarizeG10Conclusions(items).worst).toBe('C')
  })
})
