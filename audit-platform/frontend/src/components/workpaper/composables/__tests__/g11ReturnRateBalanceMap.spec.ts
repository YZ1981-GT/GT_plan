import { describe, it, expect } from 'vitest'
import {
  aggregateTbOpenClose,
  buildBalancePatchFromTb,
  pickTbClosing,
  pickTbOpening,
  findBalanceSourceForRowKey,
  G11_RETURN_RATE_BALANCE_SOURCES,
} from '../g11ReturnRateBalanceMap'

describe('g11ReturnRateBalanceMap', () => {
  it('持有期间行有科目映射，处置行无映射', () => {
    expect(findBalanceSourceForRowKey('equity_method')?.codes).toContain('1511')
    expect(findBalanceSourceForRowKey('trading_hold')?.codes).toContain('1101')
    expect(findBalanceSourceForRowKey('oth_debt_hold_interest')?.codes[0]).toBe('1506')
    expect(findBalanceSourceForRowKey('oei_dividend')?.codes[0]).toBe('1507')
    expect(findBalanceSourceForRowKey('dispose_lt_equity')).toBeUndefined()
    expect(findBalanceSourceForRowKey('control_fv_gain')).toBeUndefined()
    expect(G11_RETURN_RATE_BALANCE_SOURCES.length).toBe(6)
  })

  it('1507/1506 优先；旧 1503 按名称消歧', () => {
    const rows = [
      { standard_account_code: '1506', account_name: '其他债权投资', opening_balance: 100, audited_amount: 200 },
      { standard_account_code: '1507', account_name: '其他权益工具投资', opening_balance: 50, audited_amount: 80 },
      { standard_account_code: '1503', account_name: '其他债权投资-旧码', opening_balance: 10, audited_amount: 20 },
      { standard_account_code: '1503', account_name: '其他权益工具投资-旧码', opening_balance: 5, audited_amount: 8 },
    ]
    const debtSrc = findBalanceSourceForRowKey('oth_debt_hold_interest')!
    const oeiSrc = findBalanceSourceForRowKey('oei_dividend')!
    expect(aggregateTbOpenClose(rows, debtSrc)).toEqual({
      opening: 110, closing: 220, matchedCodes: ['1506', '1503'],
    })
    expect(aggregateTbOpenClose(rows, oeiSrc)).toEqual({
      opening: 55, closing: 88, matchedCodes: ['1507', '1503'],
    })
  })

  it('子科目期初/期末合计', () => {
    const src = findBalanceSourceForRowKey('equity_method')!
    const rows = [
      { standard_account_code: '1511', account_name: '长期股权投资', opening_balance: 1000, audited_amount: 1200 },
      { standard_account_code: '151101', account_name: '长期股权投资-成本', opening_balance: 100, audited_amount: 100 },
    ]
    const agg = aggregateTbOpenClose(rows, src)!
    expect(agg.opening).toBe(1100)
    expect(agg.closing).toBe(1300)
  })

  it('pickTbOpening/Closing 字段优先级', () => {
    expect(pickTbOpening({ opening_balance: '12.5' })).toBe(12.5)
    expect(pickTbClosing({ closing_balance: 9, audited_amount: 1 })).toBe(9)
    expect(pickTbClosing({ audited_amount: 8 })).toBe(8)
    expect(pickTbClosing({ debit_amount: 10, credit_amount: 3 })).toBe(7)
  })

  it('buildBalancePatchFromTb：有上期 TB', () => {
    const cur = [
      { standard_account_code: '1101', account_name: '交易性金融资产', opening_balance: 200, audited_amount: 300 },
    ]
    const prior = [
      { standard_account_code: '1101', account_name: '交易性金融资产', opening_balance: 150, audited_amount: 200 },
    ]
    const patch = buildBalancePatchFromTb('trading_hold', cur, prior)!
    expect(patch.currentOpening).toBe(200)
    expect(patch.currentClosing).toBe(300)
    expect(patch.priorOpening).toBe(150)
    expect(patch.priorClosing).toBe(200)
    expect(patch.usedPriorContinuity).toBe(false)
  })

  it('buildBalancePatchFromTb：无上期 TB 用连续性假设', () => {
    const cur = [
      { standard_account_code: '1511', account_name: '长期股权投资', opening_balance: 500, audited_amount: 600 },
    ]
    const patch = buildBalancePatchFromTb('equity_method', cur, null)!
    expect(patch.currentOpening).toBe(500)
    expect(patch.priorClosing).toBe(500)
    expect(patch.priorOpening).toBe(0)
    expect(patch.usedPriorContinuity).toBe(true)
  })

  it('处置行返回 null', () => {
    expect(buildBalancePatchFromTb('trading_dispose', [], null)).toBeNull()
  })
})
