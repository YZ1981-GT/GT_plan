/**
 * g9TbResolve — 试算表科目别名/名称回退
 */
import { describe, expect, it } from 'vitest'
import { resolveG9TbRow, g9TbRowBalance, g9TbResolvedCode } from '../g9TbResolve'
import { G9_ACCOUNT_CODE } from '../g9Constants'

describe('resolveG9TbRow', () => {
  it('优先精确匹配 1519', () => {
    const hit = resolveG9TbRow([
      { standard_account_code: '1504', account_name: '债权投资', debit_amount: 1 },
      { standard_account_code: '1519', account_name: '其他非流动金融资产', debit_amount: 100, credit_amount: 20 },
    ])
    expect(g9TbResolvedCode(hit)).toBe('1519')
    expect(g9TbRowBalance(hit)).toBe(80)
  })

  it('无 1519 时回退 1504', () => {
    const hit = resolveG9TbRow([
      { standard_account_code: '1504', account_name: '其他非流动金融资产', unadjusted_amount: 55 },
    ])
    expect(g9TbResolvedCode(hit)).toBe('1504')
    expect(g9TbRowBalance(hit)).toBe(55)
  })

  it('无编码匹配时按科目名称', () => {
    const hit = resolveG9TbRow([
      { account_code: '9901', account_name: '其他非流动金融资产-理财', debit_amount: 10, credit_amount: 0 },
    ])
    expect(hit).not.toBeNull()
    expect(g9TbRowBalance(hit)).toBe(10)
  })

  it('完全无匹配返回 null', () => {
    expect(resolveG9TbRow([
      { standard_account_code: '1001', account_name: '库存现金' },
    ])).toBeNull()
    expect(g9TbResolvedCode(null)).toBe(G9_ACCOUNT_CODE)
  })
})
