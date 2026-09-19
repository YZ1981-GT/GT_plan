/**
 * 分层抽样层内单独评价 — 守卫
 *
 * spec: sampling-evaluation-and-governance-closure
 * Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.8, 11.2, 11.3
 * Properties: Property 15, Property 16, Property 17
 */
import Decimal from 'decimal.js'
import fc from 'fast-check'
import { describe, expect, it } from 'vitest'

import {
  projectMisstatement,
  projectMisstatementByStrata,
  type SampledVoucher,
  type StratumConfig,
} from '../composables/useSamplingAlgorithms'

const sample = (over: Partial<SampledVoucher> = {}): SampledVoucher => ({
  voucherNo: 'V-1',
  voucherDate: '2025-06-01',
  summary: null,
  debitAmount: '1000.00',
  creditAmount: null,
  accountCode: '1122',
  accountName: null,
  counterpartAccount: null,
  voucherType: null,
  accountingPeriod: 6,
  checkResult: 'Y',
  abnormal: false,
  remark: '',
  selected: true,
  phase: 'final',
  editTrail: [],
  ...over,
})

const STRATA: StratumConfig[] = [
  { lowerBound: '0', upperBound: '10000', sampleSize: 10 },
  { lowerBound: '10000.01', upperBound: '100000', sampleSize: 5 },
  { lowerBound: '100000.01', upperBound: '99999999', sampleSize: 3 },
]

// ─── Property 15：层内加总不丢金额 ───────────────────────────────────────────

describe('Property 15：层内加总不丢金额', () => {
  it('各层样本金额之和 == 全部样本金额之和', () => {
    const samples = [
      sample({ voucherNo: 'A', debitAmount: '500.00' }),
      sample({ voucherNo: 'B', debitAmount: '50000.00' }),
      sample({ voucherNo: 'C', debitAmount: '500000.00' }),
      sample({ voucherNo: 'D', debitAmount: '9000.00' }),
    ]
    const r = projectMisstatementByStrata(samples, STRATA, '10000000.00')
    const sumDetail = r.strataDetail.reduce(
      (acc, s) => acc.plus(new Decimal(s.sampleAmount)),
      new Decimal(0),
    )
    expect(sumDetail.toFixed(2)).toBe('559500.00')
  })

  it('各层样本笔数之和 == 全部样本笔数', () => {
    const samples = Array.from({ length: 7 }, (_, i) =>
      sample({ voucherNo: `V-${i}`, debitAmount: String((i + 1) * 3000) }),
    )
    const r = projectMisstatementByStrata(samples, STRATA, '1000000.00')
    const total = r.strataDetail.reduce((n, s) => n + s.sampleCount, 0)
    expect(total).toBe(7)
  })

  it('projected == 各层外推额之和且恒 >= 0', () => {
    const samples = [
      sample({ voucherNo: 'A', debitAmount: '5000.00', actualMisstatement: '500.00' }),
      sample({ voucherNo: 'B', debitAmount: '50000.00', actualMisstatement: '1000.00' }),
    ]
    const r = projectMisstatementByStrata(samples, STRATA, '1000000.00')
    const sum = r.strataDetail.reduce(
      (acc, s) => acc.plus(new Decimal(s.projected)),
      new Decimal(0),
    )
    expect(new Decimal(r.projected).toFixed(2)).toBe(sum.toFixed(2))
    expect(parseFloat(r.projected)).toBeGreaterThanOrEqual(0)
  })

  it('样本错报全为 0 → projected 为 0.00', () => {
    const r = projectMisstatementByStrata(
      [sample({ debitAmount: '5000.00' })],
      STRATA,
      '1000000.00',
    )
    expect(r.projected).toBe('0.00')
  })
})

// ─── Property 15b：未归层桶 ──────────────────────────────────────────────────

describe('Property 15b：未归层样本单独归集且被提示', () => {
  it('金额不落任何层区间 → 进未归层桶并计数', () => {
    const narrow: StratumConfig[] = [{ lowerBound: '0', upperBound: '100', sampleSize: 5 }]
    const samples = [
      sample({ voucherNo: 'A', debitAmount: '50.00' }),
      sample({ voucherNo: 'B', debitAmount: '999999.00', actualMisstatement: '100.00' }),
    ]
    const r = projectMisstatementByStrata(samples, narrow, '1000000.00')
    expect(r.unclassifiedCount).toBe(1)
    const bucket = r.strataDetail.find(s => s.index === -1)
    expect(bucket).toBeDefined()
    expect(bucket!.label).toBe('未归层')
    expect(bucket!.sampleCount).toBe(1)
  })

  it('未归层样本仍参与外推（不得静默丢弃）', () => {
    const narrow: StratumConfig[] = [{ lowerBound: '0', upperBound: '100', sampleSize: 5 }]
    const samples = [sample({ debitAmount: '999999.00', actualMisstatement: '9999.00' })]
    const r = projectMisstatementByStrata(samples, narrow, '1000000.00')
    expect(parseFloat(r.projected)).toBeGreaterThan(0)
  })

  it('无未归层样本时不产生空行', () => {
    const r = projectMisstatementByStrata(
      [sample({ debitAmount: '500.00' })],
      STRATA,
      '1000000.00',
    )
    expect(r.strataDetail.some(s => s.index === -1)).toBe(false)
    expect(r.unclassifiedCount).toBe(0)
  })

  it('相邻层边界值归入低层（不重复计入）', () => {
    const adjacent: StratumConfig[] = [
      { lowerBound: '0', upperBound: '10000', sampleSize: 5 },
      { lowerBound: '10000', upperBound: '20000', sampleSize: 5 },
    ]
    const r = projectMisstatementByStrata(
      [sample({ debitAmount: '10000.00' })],
      adjacent,
      '100000.00',
    )
    const counted = r.strataDetail.reduce((n, s) => n + s.sampleCount, 0)
    expect(counted).toBe(1)
    expect(r.strataDetail.find(s => s.sampleCount === 1)!.index).toBe(0)
  })
})

// ─── Property 16：无样本层不外推但被提示 ─────────────────────────────────────

describe('Property 16：无样本层不外推', () => {
  it('某层有总体无样本 → projected 为 0 且 unsampled 为 true', () => {
    const samples = [sample({ debitAmount: '500.00', actualMisstatement: '50.00' })]
    const r = projectMisstatementByStrata(samples, STRATA, '1000000.00', 0.95, {
      0: '100000.00',
      1: '300000.00',
      2: '600000.00',
    })
    const unsampled = r.strataDetail.filter(s => s.unsampled)
    expect(unsampled.length).toBe(2)
    for (const s of unsampled) {
      expect(s.projected).toBe('0.00')
      expect(s.sampleCount).toBe(0)
    }
    expect(r.unsampledStrataCount).toBe(2)
  })

  it('层明细含四项复核所需数据（R6.4）', () => {
    const r = projectMisstatementByStrata(
      [sample({ debitAmount: '5000.00', actualMisstatement: '100.00' })],
      STRATA,
      '1000000.00',
    )
    const row = r.strataDetail[0]
    for (const key of ['populationAmount', 'sampleAmount', 'sampleError', 'projected']) {
      expect(row).toHaveProperty(key)
      expect(typeof (row as never as Record<string, unknown>)[key]).toBe('string')
    }
  })
})

// ─── Property 17：灰度等价与并列 ─────────────────────────────────────────────

describe('Property 17：灰度等价与新旧并列', () => {
  it('strata 为空数组 → 回退 legacy 且逐位相等', () => {
    const samples = [sample({ debitAmount: '5000.00', actualMisstatement: '500.00' })]
    const r = projectMisstatementByStrata(samples, [], '1000000.00')
    const legacy = projectMisstatement(samples, 'stratified', '0', '1000000.00')
    expect(r.projected).toBe(legacy.projected)
    expect(r.upperLimit).toBe(legacy.upperLimit)
    expect(r.strataDetail).toEqual([])
  })

  it('始终返回 legacy 字段供 UI 并列对照（R6.7）', () => {
    const r = projectMisstatementByStrata(
      [sample({ debitAmount: '5000.00', actualMisstatement: '500.00' })],
      STRATA,
      '1000000.00',
    )
    expect(r.legacy).toBeDefined()
    expect(r.legacy.projected).toMatch(/^\d+\.\d{2}$/)
  })

  it('分层口径与合并口径确有差异（否则本改动无意义）', () => {
    // 高值层抽得密、低值层抽得疏时，合并比率估计会把密集层的错报率摊到全体
    const samples = [
      sample({ voucherNo: 'A', debitAmount: '1000.00', actualMisstatement: '500.00' }),
      sample({ voucherNo: 'B', debitAmount: '500000.00', actualMisstatement: '0.00' }),
    ]
    const r = projectMisstatementByStrata(samples, STRATA, '10000000.00', 0.95, {
      0: '9000000.00',
      1: '500000.00',
      2: '500000.00',
    })
    expect(r.projected).not.toBe(r.legacy.projected)
  })

  it('非 stratified 方法不受影响（既有函数签名未变）', () => {
    const samples = [sample({ debitAmount: '5000.00', actualMisstatement: '500.00' })]
    const before = projectMisstatement(samples, 'random', '0', '1000000.00')
    expect(before.projected).toMatch(/^\d+\.\d{2}$/)
    expect(before).not.toHaveProperty('strataDetail')
  })
})

// ─── PBT ─────────────────────────────────────────────────────────────────────

describe('PBT：分层评价不变式', () => {
  const amount = () =>
    fc.integer({ min: 1, max: 5_000_000 }).map(n => (n / 100).toFixed(2))

  it('各层样本金额之和恒等于全部样本金额之和', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ debitAmount: amount(), actualMisstatement: amount() }),
          { minLength: 1, maxLength: 12 },
        ),
        rows => {
          const samples = rows.map((r, i) =>
            sample({ voucherNo: `V-${i}`, debitAmount: r.debitAmount, actualMisstatement: r.actualMisstatement }),
          )
          const res = projectMisstatementByStrata(samples, STRATA, '10000000.00')
          const expected = samples.reduce(
            (acc, v) => acc.plus(new Decimal(v.debitAmount ?? '0')),
            new Decimal(0),
          )
          const got = res.strataDetail.reduce(
            (acc, s) => acc.plus(new Decimal(s.sampleAmount)),
            new Decimal(0),
          )
          return got.toFixed(2) === expected.toFixed(2)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('projected 恒 >= 0 且 upperLimit 恒 >= projected', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ debitAmount: amount(), actualMisstatement: amount() }),
          { minLength: 1, maxLength: 10 },
        ),
        rows => {
          const samples = rows.map((r, i) =>
            sample({ voucherNo: `V-${i}`, debitAmount: r.debitAmount, actualMisstatement: r.actualMisstatement }),
          )
          const res = projectMisstatementByStrata(samples, STRATA, '10000000.00')
          const p = parseFloat(res.projected)
          return p >= 0 && parseFloat(res.upperLimit) >= p
        },
      ),
      { numRuns: 20 },
    )
  })

  it('未归层桶存在时其样本数 == unclassifiedCount', () => {
    fc.assert(
      fc.property(
        fc.array(amount(), { minLength: 1, maxLength: 10 }),
        amounts => {
          const narrow: StratumConfig[] = [{ lowerBound: '0', upperBound: '100', sampleSize: 5 }]
          const samples = amounts.map((a, i) => sample({ voucherNo: `V-${i}`, debitAmount: a }))
          const res = projectMisstatementByStrata(samples, narrow, '1000000.00')
          const bucket = res.strataDetail.find(s => s.index === -1)
          return (bucket?.sampleCount ?? 0) === res.unclassifiedCount
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── 反向自检 ────────────────────────────────────────────────────────────────

describe('反向自检', () => {
  it('复现旧行为（不分层）会让「分层口径与合并口径有差异」这条断言失效', () => {
    const samples = [
      sample({ voucherNo: 'A', debitAmount: '1000.00', actualMisstatement: '500.00' }),
      sample({ voucherNo: 'B', debitAmount: '500000.00', actualMisstatement: '0.00' }),
    ]
    // 旧口径 == legacy；若实现退回旧口径，projected 会等于 legacy.projected
    const legacy = projectMisstatement(samples, 'stratified', '0', '10000000.00')
    const r = projectMisstatementByStrata(samples, STRATA, '10000000.00', 0.95, {
      0: '9000000.00',
      1: '500000.00',
      2: '500000.00',
    })
    expect(r.projected).not.toBe(legacy.projected)
  })

  it('去掉未归层桶会破坏金额守恒（本守卫能抓到）', () => {
    const narrow: StratumConfig[] = [{ lowerBound: '0', upperBound: '100', sampleSize: 5 }]
    const samples = [
      sample({ voucherNo: 'A', debitAmount: '50.00' }),
      sample({ voucherNo: 'B', debitAmount: '999999.00' }),
    ]
    const r = projectMisstatementByStrata(samples, narrow, '1000000.00')
    const withBucket = r.strataDetail.reduce(
      (acc, s) => acc.plus(new Decimal(s.sampleAmount)),
      new Decimal(0),
    )
    const withoutBucket = r.strataDetail
      .filter(s => s.index !== -1)
      .reduce((acc, s) => acc.plus(new Decimal(s.sampleAmount)), new Decimal(0))
    expect(withBucket.toFixed(2)).toBe('1000049.00')
    expect(withoutBucket.toFixed(2)).not.toBe(withBucket.toFixed(2))
  })
})
