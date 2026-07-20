/**
 * f2AccountModel — 科目映射与 AJE 汇总契约
 */
import { describe, it, expect } from 'vitest'
import {
  F2_PRICE_DIFF_ACCOUNT,
  F2_IMPAIRMENT_ACCOUNT,
  F2_ROW_KEY_ACCOUNT,
  F2_ACCOUNT_TO_ROW_KEY,
  F2_INVENTORY_ACCOUNTS,
  sumGrossAjeByRowKey,
  sumImpairmentAjeByRowKey,
} from '../f2AccountModel'

describe('f2AccountModel', () => {
  it('maps 进销差价=1412 and 跌价准备=1471 (CAS / backend)', () => {
    expect(F2_PRICE_DIFF_ACCOUNT).toBe('1412')
    expect(F2_IMPAIRMENT_ACCOUNT).toBe('1471')
    expect(F2_ROW_KEY_ACCOUNT['price-difference']).toBe('1412')
    expect(F2_ROW_KEY_ACCOUNT['impairment-provision']).toBe('1471')
    expect(F2_ROW_KEY_ACCOUNT['finished-goods']).toBe('1406')
    expect(F2_ACCOUNT_TO_ROW_KEY['1406']).toBe('finished-goods')
    expect(F2_ACCOUNT_TO_ROW_KEY['1412']).toBe('price-difference')
    expect(F2_ACCOUNT_TO_ROW_KEY['1471']).toBe('impairment-provision')
  })

  it('adjustment account list uses 1412 for price-diff and 1471 for impairment', () => {
    const byCode = Object.fromEntries(F2_INVENTORY_ACCOUNTS.map((a) => [a.code, a.name]))
    expect(byCode['1412']).toBe('商品进销差价')
    expect(byCode['1471']).toBe('存货跌价准备')
    expect(byCode['1406']).toBe('库存商品')
  })

  it('sumGrossAjeByRowKey aggregates non-impairment AJE including 1412 price-diff', () => {
    const result = sumGrossAjeByRowKey([
      { entryType: 'AJE', accountCode: '1401', debitAmount: 100, creditAmount: 0 },
      { entryType: 'AJE', accountCode: '1412', debitAmount: 0, creditAmount: 30 },
      { entryType: 'AJE', accountCode: '1471', debitAmount: 0, creditAmount: 50 },
      { entryType: 'RJE', accountCode: '1401', debitAmount: 20, creditAmount: 0 },
    ])
    expect(result['raw-materials']).toBe(100)
    expect(result['price-difference']).toBe(-30)
    expect(result['impairment-provision']).toBeUndefined()
  })

  it('sumImpairmentAjeByRowKey only uses 1471 (not legacy 1412)', () => {
    const result = sumImpairmentAjeByRowKey([
      { entryType: 'AJE', accountCode: '1471', debitAmount: 10, creditAmount: 40 },
      { entryType: 'AJE', accountCode: '1412', debitAmount: 0, creditAmount: 99 },
      { entryType: 'RJE', accountCode: '1471', debitAmount: 0, creditAmount: 5 },
    ])
    expect(result['impairment-provision']).toBe(30)
  })
})
