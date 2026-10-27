/**
 * 挂凭按凭证键（spec voucher-identity-writeback-and-audit-phase 任务 6，需求 2.5）
 *
 * - attachVoucher 带凭证字 / 主体 / 阶段（阶段缺省不发，由后端按项目取），静默请求（调用方自己提示原因）；
 * - attachFailureReason：409 多张凭证列候选、404 账套里没有、403 无权限；
 * - 回拉：同日同号两种凭证字的两条挂凭记录各按自己的凭证字穿透，只拿到各自分录，样本带凭证键与分录指纹。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))

import http from '@/utils/http'
import { attachFailureReason, attachVoucher, pullSamplesForWorkpaper } from '../useAttachedVouchers'

const post = http.post as unknown as ReturnType<typeof vi.fn>
const get = http.get as unknown as ReturnType<typeof vi.fn>
const PID = 'p-1'
const WP = 'wp-1'
const key = (t: string) => `["2025","001","2025-01-07","${t}","0003"]`

beforeEach(() => {
  post.mockReset()
  get.mockReset()
})

describe('attachVoucher 请求体', () => {
  it('带凭证字、主体与阶段，静默请求', async () => {
    post.mockResolvedValueOnce({ data: { id: 'sv-1', voucher_no: '0003', status: 'created' } })
    await attachVoucher(PID, { year: 2025, voucherNo: '0003', voucherDate: '2025-01-07', voucherType: 'FY',
      companyCode: '001', phase: 'preliminary', workpaperId: WP })
    const [url, body, opts] = post.mock.calls[0]
    expect(url).toBe(`/api/projects/${PID}/ledger/sample-voucher`)
    expect(body).toMatchObject({ voucher_no: '0003', voucher_date: '2025-01-07', voucher_type: 'FY',
      company_code: '001', phase: 'preliminary', working_paper_id: WP })
    expect((opts as { _silent?: boolean })._silent).toBe(true)
  })

  it('空凭证字照传空串；阶段缺省时不发（后端按项目阶段取）', async () => {
    post.mockResolvedValueOnce({ data: {} })
    await attachVoucher(PID, { year: 2025, voucherNo: '0046', voucherType: '' })
    const body = post.mock.calls[0][1] as Record<string, unknown>
    expect(body.voucher_type).toBe('')
    expect('phase' in body).toBe(false)
  })
})

describe('attachFailureReason', () => {
  it('409 多张凭证：列出候选称呼', () => {
    const err = { response: { status: 409, data: { detail: { error_code: 'VOUCHER_KEY_AMBIGUOUS', message: 'x',
      candidates: [{ voucher_key: key('FY'), voucher_date: '2025-01-07', voucher_type: 'FY', voucher_no: '0003' },
        { voucher_key: key('ZZ'), voucher_date: '2025-01-07', voucher_type: 'ZZ', voucher_no: '0003' }],
      truncated: false } } } }
    expect(attachFailureReason(err)).toBe('对应多张凭证（2025-01-07 FY-0003、2025-01-07 ZZ-0003），请在凭证层选定一张再挂')
  })

  it('404 / 403 / 其他', () => {
    expect(attachFailureReason({ response: { status: 404 } })).toContain('当前账套里没有这张凭证')
    expect(attachFailureReason({ response: { status: 403 } })).toBe('没有本项目的编辑权限')
    expect(attachFailureReason(new Error('网络'))).toBe('挂凭失败，请稍后重试')
  })
})

describe('回拉按凭证键', () => {
  it('同日同号两种凭证字：各按自己的凭证字穿透，只拿到各自分录，样本带凭证键与指纹', async () => {
    const recs = ['FY', 'ZZ'].map((t, i) => ({ id: `sv-${i}`, voucher_no: '0003', voucher_date: '2025-01-07',
      voucher_type: t, company_code: '001', voucher_key: key(t), account_code: '1002', sampling_record_id: null,
      working_paper_id: WP, batch_id: null, source: 'manual', note: null, sampled_at: null }))
    const lines: Record<string, unknown[]> = {
      FY: [{ voucher_no: '0003', voucher_date: '2025-01-07', voucher_type: 'FY', account_code: '1002',
        debit_amount: null, credit_amount: '100.00', voucher_key: key('FY'), line_fp: 'fp-fy-1002' },
      { voucher_no: '0003', voucher_date: '2025-01-07', voucher_type: 'FY', account_code: '2211',
        debit_amount: '100.00', credit_amount: null, voucher_key: key('FY'), line_fp: 'fp-fy-2211' }],
      ZZ: [{ voucher_no: '0003', voucher_date: '2025-01-07', voucher_type: 'ZZ', account_code: '1002',
        debit_amount: '7.00', credit_amount: null, voucher_key: key('ZZ'), line_fp: 'fp-zz-1002' }],
    }
    get.mockImplementation((url: string, cfg: { params: Record<string, unknown> }) => {
      if (url.includes('sampled-vouchers')) return Promise.resolve({ data: { items: recs } })
      return Promise.resolve({ data: lines[String(cfg.params.voucher_type)] })
    })
    const out = await pullSamplesForWorkpaper(PID, 2025, WP, ['1002'])
    const voucherCalls = get.mock.calls.filter((c) => !String(c[0]).includes('sampled-vouchers'))
    expect(voucherCalls.map((c) => (c[1] as { params: Record<string, unknown> }).params.voucher_type)).toEqual(['FY', 'ZZ'])
    expect(out.samples.map((s) => [s.voucherType, s.voucherKey, s.lineFp, s.creditAmount ?? s.debitAmount])).toEqual([
      ['FY', key('FY'), 'fp-fy-1002', '100.00'],
      ['ZZ', key('ZZ'), 'fp-zz-1002', '7.00'],
    ])
  })
})
