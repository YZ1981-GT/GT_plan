import { describe, it, expect } from 'vitest'
import { resolveG10TbRow, g10TbRowBalance, resolveG10TbBalanceFromList } from '../g10TbResolve'

describe('g10TbResolve', () => {
  it('按标准码 2101 解析', () => {
    const hit = resolveG10TbRow([
      { account_code: '1001', credit_amount: 1 },
      { standard_account_code: '2101', closing_balance: 500 },
    ])
    expect(hit?.standard_account_code).toBe('2101')
    expect(g10TbRowBalance(hit)).toBe(500)
  })

  it('负债科目贷−借', () => {
    const hit = { credit_amount: 1000, debit_amount: 200 }
    expect(g10TbRowBalance(hit)).toBe(800)
  })

  it('resolveG10TbBalanceFromList 按别名解析', () => {
    expect(resolveG10TbBalanceFromList([
      { account_code: '2101', closing_balance: 1200 },
    ])).toBe(1200)
    expect(resolveG10TbBalanceFromList([
      { account_code: '1001', credit_amount: 1 },
    ])).toBeNull()
  })
})
