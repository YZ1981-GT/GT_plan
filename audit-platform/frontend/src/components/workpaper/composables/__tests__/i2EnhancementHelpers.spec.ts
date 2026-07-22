/**
 * i2EnhancementHelpers — 快速单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  sumI27Outsource,
  listI27ProjectNames,
  resolveDefaultCutoffDate,
} from '../i2EnhancementHelpers'

describe('i2EnhancementHelpers', () => {
  it('sumI27Outsource 优先 increase.outsource', () => {
    expect(sumI27Outsource([
      { increase: { outsource: 10.1 }, outsourceAmount: 1 },
      { ending: { outsource: 20 } },
      { outsourceSubtotal: 5 },
    ])).toBe(35.1)
  })

  it('listI27ProjectNames 去重并过滤空名', () => {
    expect(listI27ProjectNames([
      { projectName: '项目A' },
      { projectName: ' 项目A ' },
      { projectName: '' },
      { projectName: '项目B' },
      {},
    ])).toEqual(['项目A', '项目B'])
  })

  it('resolveDefaultCutoffDate 优先上下文与 year', () => {
    expect(resolveDefaultCutoffDate({
      projectContext: { bs_date: '2024-06-30T00:00:00Z' },
    })).toBe('2024-06-30')

    expect(resolveDefaultCutoffDate({ year: 2023 })).toBe('2023-12-31')

    const map = new Map<string, any>([
      ['I2-cutoff-date', { remark: '2022-12-31' }],
    ])
    expect(resolveDefaultCutoffDate({ allResponses: map })).toBe('2022-12-31')
  })
})
