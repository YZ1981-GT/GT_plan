/**
 * 截止测试抽样 / 挂凭列表的审计年度空值口径（spec post-push-residual-defect-closure R2.1）：
 * - 截止测试：年度为空默认截止日留空（原先拼成 `null-12-31`），年度到达后补上，用户已填的不动；
 * - 挂凭列表：年度为空不发请求、按「没有挂凭」处理（原先照发，带 year=null）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, ref } from 'vue'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/utils/http', () => ({ default: { get, post: vi.fn(), delete: vi.fn() } }))

import { useCutoffAutoSampling } from '../useCutoffAutoSampling'
import { listAttachedVouchers } from '../useAttachedVouchers'

function sampling(year: number | null) {
  const yearRef = ref<number | null>(year)
  const s = useCutoffAutoSampling({
    projectId: ref('p1'),
    year: yearRef,
    workpaperId: ref('wp1'),
    accountCode: '6001',
    cutoffDirection: 'window',
  })
  return { s, yearRef }
}

describe('截止测试抽样：审计年度为空', () => {
  it('默认截止日留空，不拼出 null-12-31', () => {
    expect(sampling(null).s.config.value.cutoffDate).toBe('')
    expect(sampling(2025).s.config.value.cutoffDate).toBe('2025-12-31')
  })

  it('年度后到：补上留空的默认截止日；用户已填的不动', async () => {
    const a = sampling(null)
    a.yearRef.value = 2024
    await nextTick()
    expect(a.s.config.value.cutoffDate).toBe('2024-12-31')

    const b = sampling(null)
    b.s.config.value.cutoffDate = '2024-06-30'
    b.yearRef.value = 2024
    await nextTick()
    expect(b.s.config.value.cutoffDate).toBe('2024-06-30')
  })
})

describe('挂凭列表：审计年度为空', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('不发请求，返回空列表', async () => {
    expect(await listAttachedVouchers('p1', null, 'wp1', true)).toEqual([])
    expect(get).not.toHaveBeenCalled()
  })

  it('有年度：按年度与底稿取', async () => {
    get.mockResolvedValue({ data: { items: [{ id: 'v1', voucher_no: '0001' }] } })
    const rows = await listAttachedVouchers('p1', 2025, 'wp1', true)
    expect(rows.map((r) => r.voucher_no)).toEqual(['0001'])
    expect(get.mock.calls[0][1].params).toEqual({ year: 2025, working_paper_id: 'wp1', manual_only: true })
  })
})
