/**
 * 试算表唯一取数入口（spec post-push-residual-defect-closure R1）：参数拼装、解包、并发合并、金额口径。
 * mock 只给端点真实字段（行键与后端契约见 backend/tests/test_trial_balance_row_contract.py）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ api: { get: apiGet } }))

import {
  fetchTrialBalanceRows,
  tbErrorText,
  tbIsProfitLoss,
  tbNumber,
  tbOccurrence,
  tbProfitLossUnder,
  tbRowsUnder,
  tbSumUnder,
  type TrialBalanceRow,
} from '../trialBalanceRows'

function row(code: string, extra: Partial<TrialBalanceRow> = {}): TrialBalanceRow {
  return {
    standard_account_code: code,
    account_name: code,
    account_category: null,
    direction: 'debit',
    unadjusted_amount: null,
    rje_adjustment: '0',
    aje_adjustment: '0',
    audited_amount: null,
    opening_balance: null,
    exceeds_materiality: false,
    below_trivial: false,
    updated_at: null,
    wp_adjustment: null,
    wp_publish_base: null,
    wp_published_at: null,
    ...extra,
  }
}

describe('fetchTrialBalanceRows', () => {
  beforeEach(() => {
    apiGet.mockReset()
  })

  it('年度省略不带（后端按项目审计年度取）；前缀去重去空白后逗号拼接；开关按需带', async () => {
    apiGet.mockResolvedValue([])
    await fetchTrialBalanceRows('p1', {
      year: null,
      accountPrefix: [' 1122', '1231', '1122', ''],
      includeMovement: true,
      includePrior: true,
      companyCode: '001',
    })
    expect(apiGet).toHaveBeenCalledWith('/api/projects/p1/trial-balance', {
      params: { account_prefix: '1122,1231', include_movement: true, include_prior: true, company_code: '001' },
      _silent: true,
      _dedupe: false,
    })
    apiGet.mockClear()
    await fetchTrialBalanceRows('p1', { year: 2025, accountPrefix: '6601, 6602', silent: false })
    expect(apiGet).toHaveBeenCalledWith('/api/projects/p1/trial-balance', {
      params: { year: 2025, account_prefix: '6601,6602' },
      _silent: false,
      _dedupe: false,
    })
  })

  it('解包：列表原样；v1 残留形状 {data, warning}；其他形状抛错（不返回空数组冒充 0）', async () => {
    apiGet.mockResolvedValueOnce([row('1122')])
    expect(await fetchTrialBalanceRows('p1')).toEqual({ rows: [row('1122')], warning: null })
    apiGet.mockResolvedValueOnce({ data: [row('6001')], warning: '符号约定待迁移', sign_convention_ready: false })
    expect(await fetchTrialBalanceRows('p1')).toEqual({ rows: [row('6001')], warning: '符号约定待迁移' })
    apiGet.mockResolvedValueOnce({ items: [] })
    await expect(fetchTrialBalanceRows('p1')).rejects.toThrow('试算表响应格式不符')
  })

  it('缺项目直接抛错，不发请求；请求失败原样抛给调用方', async () => {
    await expect(fetchTrialBalanceRows('')).rejects.toThrow('缺少项目')
    expect(apiGet).not.toHaveBeenCalled()
    apiGet.mockRejectedValueOnce(new Error('network'))
    await expect(fetchTrialBalanceRows('p1')).rejects.toThrow('network')
  })

  it('同参数并发只发一次；各调用方拿各自的行副本；完成后再取会重新请求', async () => {
    let resolve!: (v: unknown) => void
    apiGet.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    const a = fetchTrialBalanceRows('p1', { accountPrefix: '1122' })
    const b = fetchTrialBalanceRows('p1', { accountPrefix: '1122' })
    expect(apiGet).toHaveBeenCalledTimes(1)
    resolve([row('1122', { unadjusted_amount: '10' })])
    const [ra, rb] = await Promise.all([a, b])
    ra.rows[0].unadjusted_amount = '999'
    expect(rb.rows[0].unadjusted_amount).toBe('10')
    apiGet.mockResolvedValueOnce([])
    await fetchTrialBalanceRows('p1', { accountPrefix: '1122' })
    expect(apiGet).toHaveBeenCalledTimes(2)
  })
})

describe('金额口径', () => {
  const rows = [
    row('1122', { unadjusted_amount: '100', audited_amount: '110', opening_balance: '80' }),
    row('112201', { unadjusted_amount: '5', audited_amount: null }),
    row('1231-02', { direction: 'credit', unadjusted_amount: '7' }),
    row('6001', { direction: 'credit', unadjusted_amount: '500', audited_amount: '520' }),
    row('600101', { direction: 'credit', unadjusted_amount: '50', audited_amount: '50' }),
    row('6601', { direction: 'debit', unadjusted_amount: '30', audited_amount: '31' }),
    row('2211', { direction: 'credit', unadjusted_amount: '9', period_debit: '40', period_credit: '60' }),
  ]

  it('tbNumber：空 / 非数字 ⇒ null（不当 0）', () => {
    expect([null, undefined, '', 'abc', '1.5', '0', 3].map(tbNumber)).toEqual([null, null, null, null, 1.5, 0, 3])
  })

  it('tbRowsUnder / tbSumUnder：科目及其明细之和；没有行 / 全空 ⇒ null', () => {
    expect(tbRowsUnder(rows, '1122,1231').map((r) => r.standard_account_code)).toEqual(['1122', '112201', '1231-02'])
    expect(tbRowsUnder(rows, '')).toEqual([])
    expect(tbSumUnder(rows, '1122', 'unadjusted_amount')).toBe(105)
    expect(tbSumUnder(rows, '1122', 'audited_amount')).toBe(110)
    expect(tbSumUnder(rows, '1122', 'opening_balance')).toBe(80)
    expect(tbSumUnder(rows, '1999', 'unadjusted_amount')).toBeNull()
    expect(tbSumUnder(rows, '112201', 'audited_amount')).toBeNull()
  })

  it('tbOccurrence：损益类按方向单边拆（不用余额表借贷，含结转时两侧相等）；资产负债类要 includeMovement', () => {
    expect(tbIsProfitLoss(row('6001'))).toBe(true)
    expect(tbIsProfitLoss(row('5001'))).toBe(true)
    expect(tbIsProfitLoss(row('1122'))).toBe(false)
    expect(tbOccurrence(rows[3])).toEqual({ debit: 0, credit: 500 })
    expect(tbOccurrence(rows[3], 'audited')).toEqual({ debit: 0, credit: 520 })
    expect(tbOccurrence(rows[5])).toEqual({ debit: 30, credit: 0 })
    expect(tbOccurrence(rows[6])).toEqual({ debit: 40, credit: 60 })
    expect(tbOccurrence(rows[0])).toBeNull()
    expect(tbOccurrence(row('6602'))).toBeNull()
  })

  it('tbProfitLossUnder：科目族借 / 贷 / 审定之和；没有行 ⇒ found=false、审定 null', () => {
    expect(tbProfitLossUnder(rows, '6001')).toEqual({ found: true, debit: 0, credit: 550, audited: 570 })
    expect(tbProfitLossUnder(rows, '6001', 'audited')).toEqual({ found: true, debit: 0, credit: 570, audited: 570 })
    expect(tbProfitLossUnder(rows, '6601')).toEqual({ found: true, debit: 30, credit: 0, audited: 31 })
    expect(tbProfitLossUnder(rows, '6711')).toEqual({ found: false, debit: 0, credit: 0, audited: null })
  })

  it('tbErrorText：后端原因原样（detail 字符串 / 对象 / message），取不到给兜底文案', () => {
    expect(tbErrorText({ response: { data: { detail: '项目未设置审计年度，请先在项目信息中填写' } } }))
      .toBe('项目未设置审计年度，请先在项目信息中填写')
    expect(tbErrorText({ response: { data: { detail: { message: '无权访问' } } } })).toBe('无权访问')
    expect(tbErrorText({ response: { data: { message: '服务异常' } } })).toBe('服务异常')
    expect(tbErrorText(new Error('Request failed with status code 500'))).toBe('试算表取数失败，请稍后重试')
    expect(tbErrorText(null)).toBe('试算表取数失败，请稍后重试')
  })
})
