/**
 * g10TbResolve — 行形状 = 试算表端点真实字段（services/trialBalanceRows.ts）：
 * 负债类余额取期末未审数（正数口径），端点没有借 / 贷 / 期末余额字段
 */
import { describe, it, expect } from 'vitest'
import { resolveG10TbRow, g10TbRowBalance, resolveG10TbBalanceFromList } from '../g10TbResolve'

describe('g10TbResolve', () => {
  it('按标准码 2101 解析', () => {
    const hit = resolveG10TbRow([
      { standard_account_code: '1001', unadjusted_amount: '1' },
      { standard_account_code: '2101', unadjusted_amount: '500' },
    ])
    expect(hit?.standard_account_code).toBe('2101')
    expect(g10TbRowBalance(hit)).toBe(500)
  })

  it('不再按「贷 − 借」兜底：未审数为空 ⇒ 0', () => {
    expect(g10TbRowBalance({ standard_account_code: '2101', unadjusted_amount: null })).toBe(0)
    expect(g10TbRowBalance(null)).toBe(0)
  })

  it('resolveG10TbBalanceFromList 按别名解析', () => {
    expect(resolveG10TbBalanceFromList([
      { standard_account_code: '2101', unadjusted_amount: '1200' },
    ])).toBe(1200)
    expect(resolveG10TbBalanceFromList([
      { standard_account_code: '1001', unadjusted_amount: '1' },
    ])).toBeNull()
  })
})
