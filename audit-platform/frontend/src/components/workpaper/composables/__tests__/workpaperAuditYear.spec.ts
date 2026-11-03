/**
 * workpaperAuditYear 单元测试
 */
import { beforeEach, describe, it, expect, vi } from 'vitest'

// 试算表唯一入口经 apiProxy 取数：mock 端点，行形状 = 端点真实字段
const apiGet = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ api: { get: apiGet } }))

import { resolveAuditYearNumber, pickTbAmount, fetchTbAmountByPrefix } from '../workpaperAuditYear'

describe('resolveAuditYearNumber', () => {
  it('解析有效年度', () => {
    expect(resolveAuditYearNumber(2025)).toBe(2025)
    expect(resolveAuditYearNumber('2024')).toBe(2024)
  })
  it('拒绝非法值并回退后续候选', () => {
    expect(resolveAuditYearNumber(null, undefined, '', 0, 2026)).toBe(2026)
    expect(resolveAuditYearNumber('abc', 1899, 2025)).toBe(2025)
  })
  it('全无效返回 null', () => {
    expect(resolveAuditYearNumber(null, undefined, '')).toBeNull()
  })
})

describe('pickTbAmount', () => {
  it('优先 audited_amount', () => {
    expect(pickTbAmount({ audited_amount: '10', unadjusted_amount: '5' })).toBe(10)
  })
  it('没有审定数取未审数；端点不返回的借 / 贷字段不参与（原先「借贷差兜底」读的是不存在的字段）', () => {
    expect(pickTbAmount({ audited_amount: null, unadjusted_amount: '60' })).toBe(60)
    expect(pickTbAmount({ debit_amount: 100, credit_amount: 40 })).toBe(0)
    expect(pickTbAmount(null)).toBe(0)
  })
})

describe('fetchTbAmountByPrefix', () => {
  beforeEach(() => {
    apiGet.mockReset()
  })

  it('科目及其明细之和（原先只取首条匹配行），按年度与前缀请求', async () => {
    apiGet.mockResolvedValueOnce([
      { standard_account_code: '1511', audited_amount: '100', unadjusted_amount: '90' },
      { standard_account_code: '151101', audited_amount: null, unadjusted_amount: '20' },
      { standard_account_code: '1512', audited_amount: '7', unadjusted_amount: '7' },
    ])
    expect(await fetchTbAmountByPrefix('p1', 2025, '1511')).toBe(120)
    expect(apiGet).toHaveBeenCalledWith(
      '/api/projects/p1/trial-balance',
      expect.objectContaining({ params: { year: 2025, account_prefix: '1511' } }),
    )
  })

  it('无年度不请求；无匹配 / 请求失败返回 null（不当 0）', async () => {
    expect(await fetchTbAmountByPrefix('p1', null, '1511')).toBeNull()
    expect(apiGet).not.toHaveBeenCalled()
    apiGet.mockResolvedValueOnce([{ standard_account_code: '1512', audited_amount: '7' }])
    expect(await fetchTbAmountByPrefix('p1', 2025, '1511')).toBeNull()
    apiGet.mockRejectedValueOnce(new Error('network'))
    expect(await fetchTbAmountByPrefix('p1', 2025, '1511')).toBeNull()
  })
})
