/**
 * 试算表方向推导 Vitest 测试。
 *
 * Task 7: 试算表展示去补救化
 * - 7.2 getDirection() 优先使用后端权威方向
 * - 7.3 移除普通科目按金额正负作为第一方向来源的逻辑
 * - 7.7 方向来源优先级和用户覆盖持久化
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
 */

import { describe, expect, it } from 'vitest'
import { getDirection, type TrialBalanceRow } from '../useTrialBalanceDirection'

describe('getDirection — 方向来源优先级', () => {
  it('优先使用后端权威方向 (backend field)', () => {
    const row: TrialBalanceRow = {
      account_code: '1001',
      direction: 'debit',
      direction_source: 'split_columns',
    }
    const result = getDirection(row)
    expect(result.direction).toBe('debit')
    expect(result.source).toBe('split_columns')
  })

  it('后端方向为 unknown 时 fallback 到用户覆盖', () => {
    const row: TrialBalanceRow = {
      account_code: '2001',
      direction: 'unknown',
      user_override_direction: 'credit',
    }
    const result = getDirection(row)
    expect(result.direction).toBe('credit')
    expect(result.source).toBe('user_override')
  })

  it('用户覆盖优先于 legacy 推断', () => {
    const row: TrialBalanceRow = {
      account_code: '2001',
      user_override_direction: 'debit',
    }
    const result = getDirection(row, 'liability')
    expect(result.direction).toBe('debit')
    expect(result.source).toBe('user_override')
  })

  it('无后端方向无覆盖时使用 legacy_inferred', () => {
    const row: TrialBalanceRow = {
      account_code: '2001',
      closing_balance: -5000,
    }
    const result = getDirection(row, 'liability')
    expect(result.direction).toBe('credit')
    expect(result.source).toBe('legacy_inferred')
  })

  it('后端方向有值时不看金额正负', () => {
    const row: TrialBalanceRow = {
      account_code: '2221',
      closing_balance: 14203492, // 正数 = 借方
      direction: 'credit',
      direction_source: 'explicit_direction',
    }
    const result = getDirection(row)
    expect(result.direction).toBe('credit')
    expect(result.source).toBe('explicit_direction')
  })
})

describe('getDirection — 去补救化：不按金额正负推断', () => {
  it('普通科目无类别时不按正数推为借方', () => {
    const row: TrialBalanceRow = {
      account_code: '9999', // 非标准前缀
      account_name: '特殊科目',
      closing_balance: 1000,
    }
    const result = getDirection(row)
    // 没有后端方向、无覆盖、无类别 → unknown
    expect(result.direction).toBe('unknown')
    expect(result.source).toBe('unknown')
  })

  it('普通科目无类别时不按负数推为贷方', () => {
    const row: TrialBalanceRow = {
      account_code: '9001',
      account_name: '其他',
      closing_balance: -500,
    }
    const result = getDirection(row)
    expect(result.direction).toBe('unknown')
  })

  it('有科目类别时按类别推断而非金额', () => {
    const row: TrialBalanceRow = {
      account_code: '2001',
      closing_balance: 5000, // 正数（但负债应为贷方）
    }
    const result = getDirection(row, 'liability')
    expect(result.direction).toBe('credit')
    expect(result.source).toBe('legacy_inferred')
  })
})

describe('getDirection — 资产备抵', () => {
  it('累计折旧方向为贷方', () => {
    const row: TrialBalanceRow = {
      account_code: '1602',
      account_name: '累计折旧',
      closing_balance: -200,
    }
    const result = getDirection(row)
    expect(result.direction).toBe('credit')
    expect(result.source).toBe('legacy_inferred')
  })

  it('坏账准备方向为贷方', () => {
    const row: TrialBalanceRow = {
      account_code: '1231',
      account_name: '坏账准备',
    }
    const result = getDirection(row)
    expect(result.direction).toBe('credit')
    expect(result.source).toBe('legacy_inferred')
  })
})

describe('getDirection — 编码前缀 fallback', () => {
  it('1xxx 推断为借方', () => {
    const row: TrialBalanceRow = { account_code: '1001' }
    const result = getDirection(row)
    expect(result.direction).toBe('debit')
    expect(result.source).toBe('legacy_inferred')
  })

  it('2xxx 推断为贷方', () => {
    const row: TrialBalanceRow = { account_code: '2001' }
    const result = getDirection(row)
    expect(result.direction).toBe('credit')
    expect(result.source).toBe('legacy_inferred')
  })

  it('5xxx 推断为借方', () => {
    const row: TrialBalanceRow = { account_code: '5001' }
    const result = getDirection(row)
    expect(result.direction).toBe('debit')
    expect(result.source).toBe('legacy_inferred')
  })
})
