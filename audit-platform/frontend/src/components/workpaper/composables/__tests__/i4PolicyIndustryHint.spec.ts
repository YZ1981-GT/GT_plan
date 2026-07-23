/**
 * i4PolicyIndustryHint — 行业推荐单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  hintIndustryFromText,
  hintIndustryFromExpenseMix,
  recommendPeerIndustry,
} from '../i4PolicyIndustryHint'

describe('hintIndustryFromText', () => {
  it('命中零售关键词', () => {
    const h = hintIndustryFromText('某某连锁超市有限公司')
    expect(h?.id).toBe('retail')
    expect(h?.confidence).toBe('high')
  })

  it('命中物业关键词', () => {
    expect(hintIndustryFromText('保利地产')?.id).toBe('property')
  })

  it('无关键词返回 null', () => {
    expect(hintIndustryFromText('普通咨询公司')).toBeNull()
  })
})

describe('hintIndustryFromExpenseMix', () => {
  it('装修占比高推荐零售', () => {
    const h = hintIndustryFromExpenseMix([
      { expenseType: '装修费', originalAmount: 80 },
      { expenseType: '开办费', originalAmount: 20 },
    ])
    expect(h?.id).toBe('retail')
  })

  it('开办费占比高推荐制造', () => {
    const h = hintIndustryFromExpenseMix([
      { expenseType: '开办费', originalAmount: 50 },
      { expenseType: '其他', originalAmount: 50 },
    ])
    expect(h?.id).toBe('manufacturing')
  })
})

describe('recommendPeerIndustry', () => {
  it('优先项目上下文客户名', () => {
    const h = recommendPeerIndustry({
      projectContext: { client_name: '永辉超市股份有限公司' },
      detailRows: [{ expenseType: '开办费', originalAmount: 100 }],
    })
    expect(h.id).toBe('retail')
  })

  it('无上下文时回退费用结构', () => {
    const h = recommendPeerIndustry({
      projectContext: {},
      detailRows: [
        { expenseType: '装修费', originalAmount: 70 },
        { expenseType: '租赁改良', originalAmount: 30 },
      ],
    })
    expect(h.id).toBe('retail')
  })

  it('全空时默认制造业 low', () => {
    const h = recommendPeerIndustry({})
    expect(h.id).toBe('manufacturing')
    expect(h.confidence).toBe('low')
  })
})
