/**
 * `pullSamplesForWorkpaper` 三级筛选单测 —— spec
 * `voucher-sampling-account-scope-and-attach-closure` Requirement 3（阶段 5，任务 5.6）。
 *
 * 覆盖四情形：
 *   ① 命中底稿科目前缀           → 正常回填
 *   ② 命中挂凭意图 rec.account_code → 回填 + remark 标注待核对
 *   ③ 两者皆空但凭证有分录        → 判挂错底稿，**不产样本**，进 misattached
 *   ─ 凭证无分录（穿透失败）       → 占位样本（技术失败，与 ③ 区分）
 *
 * 🔴 改造前的缺陷：`if (picked.length === 0) picked = lines` —— ③ 情形会把整张凭证
 * 所有科目的分录静默灌进底稿。本文件的 ③ 用例正是为钉死它。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

import http from '@/utils/http'
import { pullSamplesForWorkpaper } from '../useAttachedVouchers'

const PID = 'p-1'
const WP = 'wp-1'
const YEAR = 2025

/** 构造 sampled_vouchers 行 */
function rec(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'sv-1',
    voucher_no: '0075',
    voucher_date: '2025-01-03',
    account_code: '1002',
    sampling_record_id: null,
    working_paper_id: WP,
    batch_id: null,
    source: 'manual',
    note: null,
    sampled_at: '2025-01-03T00:00:00Z',
    ...over,
  }
}

/** 构造凭证分录行 */
function line(code: string, over: Partial<Record<string, unknown>> = {}) {
  return {
    id: `l-${code}`,
    voucher_date: '2025-01-03',
    voucher_no: '0075',
    account_code: code,
    account_name: `科目${code}`,
    debit_amount: '100',
    credit_amount: null,
    summary: '测试摘要',
    ...over,
  }
}

/**
 * 装配 http mock：第 1 次 get = sampled-vouchers 列表；后续 get = 凭证分录。
 * `lines` 为 null 表示该次请求抛错（模拟穿透失败）。
 */
function mockHttp(records: unknown[], linesPerVoucher: unknown[] | null) {
  const get = http.get as unknown as ReturnType<typeof vi.fn>
  get.mockReset()
  get.mockImplementation((url: string) => {
    if (url.includes('sampled-vouchers')) {
      return Promise.resolve({ data: { items: records } })
    }
    if (linesPerVoucher === null) return Promise.reject(new Error('穿透失败'))
    return Promise.resolve({ data: linesPerVoucher })
  })
  return get
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('① 命中底稿科目前缀（正常路径）', () => {
  it('只回填命中前缀的分录，不带歧义标注', async () => {
    mockHttp([rec()], [line('1002'), line('6602'), line('2202')])
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1001', '1002', '1012'])
    expect(r.samples).toHaveLength(1)
    expect(r.samples[0].accountCode).toBe('1002')
    expect(r.samples[0].remark).toBe('序时账手工挂入')
    expect(r.misattached).toEqual([])
  })

  it('命中多条则全部回填', async () => {
    mockHttp([rec()], [line('1002'), line('1002.001'), line('6602')])
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    expect(r.samples).toHaveLength(2)
    expect(r.misattached).toEqual([])
  })

  it('accountPrefixes 为空数组 ⇒ 取全部分录（不按科目筛）', async () => {
    mockHttp([rec()], [line('1002'), line('6602')])
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, [])
    expect(r.samples).toHaveLength(2)
    expect(r.misattached).toEqual([])
  })
})

describe('② 命中挂凭意图（R3.3）', () => {
  it('底稿前缀不命中但挂凭科目命中 ⇒ 回填该分录并标注待核对', async () => {
    // 用户在 1122 应收账款那行挂的凭证，却挂到了货币资金底稿
    mockHttp([rec({ account_code: '1122' })], [line('1122'), line('6001')])
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1001', '1002', '1012'])
    expect(r.samples).toHaveLength(1)
    expect(r.samples[0].accountCode).toBe('1122')
    expect(r.samples[0].remark).toContain('1122')
    expect(r.samples[0].remark).toContain('未命中本底稿科目范围')
    expect(r.samples[0].remark).toContain('请核对')
    // 🔴 ② 级命中不算挂错底稿
    expect(r.misattached).toEqual([])
  })

  it('日期歧义与科目歧义可叠加，两条说明都在 remark 里', async () => {
    mockHttp(
      [rec({ account_code: '1122', voucher_date: null })],
      [line('1122', { voucher_date: '2025-03-31' })],
    )
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    expect(r.samples).toHaveLength(1)
    expect(r.samples[0].remark).toContain('未记凭证日期')
    expect(r.samples[0].remark).toContain('未命中本底稿科目范围')
  })
})

describe('③ 挂错底稿：不产样本、进 misattached（R3.4 / R3.5）', () => {
  /**
   * 🔴 构造 ③ 级必须让**两级都不命中**：
   *   - 底稿前缀不命中（分录里没有本底稿科目），且
   *   - 挂凭意图也不命中（`rec.account_code` 为 null，或它在这张凭证里不存在）
   *
   * 若只让前缀不命中而 `rec.account_code` 恰在分录中，那是 ② 级命中（应产 1 个样本），
   * 不是 ③ 级 —— 本文件首版即因此把 4 个用例写错，实现是对的。
   */

  it('🔴 挂凭记录无 account_code + 前缀不命中 ⇒ 零样本（绝不回退取全部分录）', async () => {
    mockHttp([rec({ account_code: null })], [line('6602'), line('2202'), line('1403')])
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1001', '1002', '1012'])
    expect(
      r.samples,
      '改造前 `if (picked.length===0) picked = lines` 会把 3 条无关科目分录全灌进来',
    ).toHaveLength(0)
    expect(r.misattached).toHaveLength(1)
  })

  it('🔴 挂凭意图记的科目在该凭证中不存在 ⇒ 判挂错（记录漂移场景）', async () => {
    // 用户挂凭时记的是 1122，但按 (no,date) 取回的这张凭证里没有 1122
    // （同号跨日凭证 + 历史记录未存日期时会发生）
    mockHttp([rec({ account_code: '1122' })], [line('6602'), line('2202')])
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    expect(r.samples).toHaveLength(0)
    expect(r.misattached).toHaveLength(1)
  })

  it('misattached 带凭证号、日期与实际科目（去重）', async () => {
    mockHttp(
      [rec({ account_code: null })],
      [line('6602'), line('6602'), line('2202')],
    )
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    const m = r.misattached[0]
    expect(m.voucherNo).toBe('0075')
    expect(m.voucherDate).toBe('2025-01-03')
    expect(m.actualAccounts).toEqual(['6602', '2202'])
    expect(m.recordId).toBe('sv-1')
  })

  it('多张凭证混合：正常的回填、错挂的进清单', async () => {
    const get = http.get as unknown as ReturnType<typeof vi.fn>
    get.mockReset()
    get.mockImplementation((url: string) => {
      if (url.includes('sampled-vouchers')) {
        return Promise.resolve({
          data: {
            items: [
              rec({ id: 'sv-a', voucher_no: 'A1' }),
              rec({ id: 'sv-b', voucher_no: 'B2', account_code: null }),
            ],
          },
        })
      }
      if (url.includes('A1')) return Promise.resolve({ data: [line('1002')] })
      return Promise.resolve({ data: [line('6602'), line('2202')] })
    })
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    expect(r.samples).toHaveLength(1)
    expect(r.samples[0].voucherNo).toBe('A1')
    expect(r.misattached).toHaveLength(1)
    expect(r.misattached[0].voucherNo).toBe('B2')
  })

  it('🔴 对照用例：前缀不命中但挂凭意图命中 ⇒ 属 ② 级，应产样本而非判挂错', async () => {
    // 与上面 ③ 级用例只差 account_code 是否命中 —— 钉死两级的分界
    mockHttp([rec({ account_code: '6602' })], [line('6602'), line('2202')])
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    expect(r.samples).toHaveLength(1)
    expect(r.samples[0].accountCode).toBe('6602')
    expect(r.misattached).toEqual([])
  })
})

describe('穿透失败（技术失败）与业务错挂可区分（R3.6）', () => {
  it('请求抛错 ⇒ 产占位样本（保留凭证号），不进 misattached', async () => {
    mockHttp([rec()], null)
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    expect(r.samples).toHaveLength(1)
    expect(r.samples[0].voucherNo).toBe('0075')
    expect(r.samples[0].summary).toContain('穿透失败')
    expect(r.misattached, '技术失败不应被误判为挂错底稿').toEqual([])
  })

  it('返回空分录数组 ⇒ 同样产占位样本，不进 misattached', async () => {
    mockHttp([rec()], [])
    const r = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    expect(r.samples).toHaveLength(1)
    expect(r.misattached).toEqual([])
  })

  it('🔴 两类问题的产出形态互不相同（否则 UI 无法分别提示）', async () => {
    mockHttp([rec()], null)
    const failCase = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])

    // ③ 级：两级都不命中（account_code 为 null）
    mockHttp([rec({ account_code: null })], [line('6602')])
    const misCase = await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])

    expect(failCase.samples.length, '穿透失败应产占位样本').toBe(1)
    expect(failCase.misattached.length, '穿透失败不是业务错挂').toBe(0)
    expect(misCase.samples.length, '挂错底稿不产样本').toBe(0)
    expect(misCase.misattached.length).toBe(1)
  })
})

describe('只取手工挂凭（manual_only）', () => {
  it('列表请求带 manual_only=true，不把引擎批次冒充手工挂入', async () => {
    const get = mockHttp([rec()], [line('1002')])
    await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    const listCall = get.mock.calls.find((c: unknown[]) => String(c[0]).includes('sampled-vouchers'))
    expect(listCall).toBeTruthy()
    expect((listCall![1] as { params: Record<string, unknown> }).params).toMatchObject({
      year: YEAR,
      working_paper_id: WP,
      manual_only: true,
    })
  })

  it('凭证分录请求带 voucher_date（凭证号不唯一，须消歧）', async () => {
    const get = mockHttp([rec()], [line('1002')])
    await pullSamplesForWorkpaper(PID, YEAR, WP, ['1002'])
    const lineCall = get.mock.calls.find((c: unknown[]) => String(c[0]).includes('/voucher/'))
    expect(lineCall).toBeTruthy()
    expect((lineCall![1] as { params: Record<string, unknown> }).params).toMatchObject({
      year: YEAR,
      voucher_date: '2025-01-03',
    })
  })
})
