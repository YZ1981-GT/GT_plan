/**
 * g8Conclusion — A/B/C 口径
 */
import { describe, it, expect } from 'vitest'
import {
  applyG8ConclusionTemplate,
  inferG8ConclusionOption,
  G8_CONCLUSION_TEMPLATES,
} from '../g8Conclusion'

describe('g8Conclusion', () => {
  it('推断结论文本口径', () => {
    expect(inferG8ConclusionOption('A、未见异常')).toBe('A')
    expect(inferG8ConclusionOption('B、除调整外未见异常')).toBe('B')
    expect(inferG8ConclusionOption('C、范围受限')).toBe('C')
    expect(inferG8ConclusionOption('经复核未见异常')).toBe('')
  })

  it('空正文应用模板', () => {
    expect(applyG8ConclusionTemplate('A', '')).toBe(G8_CONCLUSION_TEMPLATES.A)
  })
})
