import { describe, expect, it } from 'vitest'
import {
  inferG10AdjudicationRowKey,
  isG10AccountCode,
  resolveG10LiabilitySuffix,
} from '../g10AccountMatch'

describe('g10AccountMatch', () => {
  it('isG10AccountCode 识别 2101/2102', () => {
    expect(isG10AccountCode('2101')).toBe(true)
    expect(isG10AccountCode('210201')).toBe(true)
    expect(isG10AccountCode('1504')).toBe(false)
  })

  it('负债类型映射回写 suffix', () => {
    expect(resolveG10LiabilitySuffix({ liabilityType: '衍生金融负债' })).toBe('derivative_liability')
    expect(resolveG10LiabilitySuffix({ liabilityType: '交易性债券' })).toBe('trading_bond')
  })

  it('摘要关键词推断回写行', () => {
    expect(inferG10AdjudicationRowKey({ summary: '调整衍生工具公允价值' })).toBe('book_derivative_liability')
    expect(inferG10AdjudicationRowKey({ adjudicationRowKey: 'book_other' })).toBe('book_other')
  })
})
