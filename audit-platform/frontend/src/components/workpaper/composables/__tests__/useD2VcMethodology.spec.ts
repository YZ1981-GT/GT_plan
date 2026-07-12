/**
 * useD2VcMethodology — Unit + Integration Tests
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 2.1
 *
 * Tests all pure functions exported from useD2VcMethodology.ts:
 * - computeMusSampleSize
 * - computeRandomSampleSize
 * - markSpecificSamples
 * - computeSamplingPopulation
 * - computeSampleSizeDeviation
 * - recommendSamplingMethod
 * - isAbnormalDate
 */
import { describe, it, expect } from 'vitest'
import {
  computeMusSampleSize,
  computeRandomSampleSize,
  markSpecificSamples,
  computeSamplingPopulation,
  computeSampleSizeDeviation,
  recommendSamplingMethod,
  isAbnormalDate,
  type PopulationDesc,
  type SpecificSampleItem,
  type TransactionItem,
  type RiskLevel,
} from '../useD2VcMethodology'

// ─── computeMusSampleSize ────────────────────────────────────────────────────

describe('computeMusSampleSize', () => {
  it('should compute MUS sample size correctly for high risk', () => {
    // T=1000000, RF=3.00, P=5000000
    // interval = 1000000/3.00 = 333333.33
    // sampleSize = ceil(5000000/333333.33) = 15
    const result = computeMusSampleSize(1000000, 3.00, 5000000)
    expect(result).toBe(15)
  })

  it('should compute MUS sample size correctly for medium risk', () => {
    // T=1000000, RF=2.31, P=5000000
    // interval = 1000000/2.31 = 432900.43
    // sampleSize = ceil(5000000/432900.43) = 12
    const result = computeMusSampleSize(1000000, 2.31, 5000000)
    expect(result).toBe(12)
  })

  it('should compute MUS sample size correctly for low risk', () => {
    // T=1000000, RF=1.61, P=5000000
    // interval = 1000000/1.61 = 621118.01
    // sampleSize = ceil(5000000/621118.01) = 9
    const result = computeMusSampleSize(1000000, 1.61, 5000000)
    expect(result).toBe(9)
  })

  it('should return 0 for zero tolerable misstatement', () => {
    expect(computeMusSampleSize(0, 3.00, 5000000)).toBe(0)
  })

  it('should return 0 for zero reliability factor', () => {
    expect(computeMusSampleSize(1000000, 0, 5000000)).toBe(0)
  })

  it('should return 0 for zero population amount', () => {
    expect(computeMusSampleSize(1000000, 3.00, 0)).toBe(0)
  })

  it('should return 0 for negative inputs', () => {
    expect(computeMusSampleSize(-100, 3.00, 5000000)).toBe(0)
    expect(computeMusSampleSize(1000000, -1, 5000000)).toBe(0)
    expect(computeMusSampleSize(1000000, 3.00, -5000000)).toBe(0)
  })
})

// ─── computeRandomSampleSize ─────────────────────────────────────────────────

describe('computeRandomSampleSize', () => {
  it('should return correct size for high confidence / large population', () => {
    // 95% confidence, 10000+ population → 384 (capped to Infinity threshold)
    const result = computeRandomSampleSize(50000, 0.95)
    expect(result).toBe(384)
  })

  it('should return correct size for medium confidence / medium population', () => {
    // 90% confidence, 500 population → 132
    const result = computeRandomSampleSize(500, 0.90)
    expect(result).toBe(132)
  })

  it('should return correct size for low confidence / small population', () => {
    // 80% confidence, 100 population → 43
    const result = computeRandomSampleSize(100, 0.80)
    expect(result).toBe(43)
  })

  it('should not exceed population size', () => {
    // 95% confidence, population=10 → min(44, 10) = 10
    const result = computeRandomSampleSize(10, 0.95)
    expect(result).toBe(10)
  })

  it('should return 0 for zero population', () => {
    expect(computeRandomSampleSize(0, 0.95)).toBe(0)
  })

  it('should return 0 for negative population', () => {
    expect(computeRandomSampleSize(-100, 0.90)).toBe(0)
  })

  it('should be monotonically non-decreasing with confidence level', () => {
    const pop = 1000
    const low = computeRandomSampleSize(pop, 0.80)
    const mid = computeRandomSampleSize(pop, 0.90)
    const high = computeRandomSampleSize(pop, 0.95)
    expect(high).toBeGreaterThanOrEqual(mid)
    expect(mid).toBeGreaterThanOrEqual(low)
  })
})

// ─── markSpecificSamples ─────────────────────────────────────────────────────

describe('markSpecificSamples', () => {
  const transactions: TransactionItem[] = [
    { id: '1', customerName: '客户A', amount: 2000000, isRelatedParty: false, transactionDate: '2024-03-15' },
    { id: '2', customerName: '关联公司B', amount: 100000, isRelatedParty: true, transactionDate: '2024-04-10' },
    { id: '3', customerName: '客户C', amount: 50000, isRelatedParty: false, transactionDate: '2024-12-28' },
    { id: '4', customerName: '客户D', amount: 30000, isRelatedParty: false, transactionDate: '2024-06-15' }, // Saturday
    { id: '5', customerName: '普通客户', amount: 10000, isRelatedParty: false, transactionDate: '2024-03-18' },
  ]

  it('should mark items with amount >= tolerable misstatement', () => {
    const result = markSpecificSamples(transactions, 1000000)
    const item = result.find(r => r.id === '1')
    expect(item).toBeDefined()
    expect(item!.reason).toContain('金额≥可容忍错报')
  })

  it('should mark related party transactions', () => {
    const result = markSpecificSamples(transactions, 5000000)
    const item = result.find(r => r.id === '2')
    expect(item).toBeDefined()
    expect(item!.reason).toContain('关联方交易')
  })

  it('should mark transactions on abnormal dates (period-end cluster)', () => {
    const result = markSpecificSamples(transactions, 5000000)
    const item = result.find(r => r.id === '3')
    expect(item).toBeDefined()
    expect(item!.reason).toContain('异常日期')
  })

  it('should mark transactions on weekends', () => {
    const result = markSpecificSamples(transactions, 5000000)
    const item = result.find(r => r.id === '4')
    expect(item).toBeDefined()
    expect(item!.reason).toContain('异常日期')
  })

  it('should NOT mark normal transactions', () => {
    const result = markSpecificSamples(transactions, 5000000)
    const item = result.find(r => r.id === '5')
    expect(item).toBeUndefined()
  })

  it('should return empty array for empty transactions', () => {
    expect(markSpecificSamples([], 1000000)).toEqual([])
  })

  it('should combine multiple reasons', () => {
    const txs: TransactionItem[] = [
      { id: '99', customerName: '关联方大额', amount: 2000000, isRelatedParty: true, transactionDate: '2024-12-29' },
    ]
    const result = markSpecificSamples(txs, 1000000)
    expect(result).toHaveLength(1)
    expect(result[0].reason).toContain('金额≥可容忍错报')
    expect(result[0].reason).toContain('关联方交易')
    expect(result[0].reason).toContain('异常日期')
  })

  it('should set confirmed to false by default', () => {
    const result = markSpecificSamples(transactions, 1000000)
    for (const item of result) {
      expect(item.confirmed).toBe(false)
    }
  })
})

// ─── isAbnormalDate ──────────────────────────────────────────────────────────

describe('isAbnormalDate', () => {
  it('should detect Saturday as abnormal', () => {
    // 2024-06-15 is Saturday
    expect(isAbnormalDate('2024-06-15')).toBe(true)
  })

  it('should detect Sunday as abnormal', () => {
    // 2024-06-16 is Sunday
    expect(isAbnormalDate('2024-06-16')).toBe(true)
  })

  it('should detect December 25+ as abnormal', () => {
    expect(isAbnormalDate('2024-12-25')).toBe(true)
    expect(isAbnormalDate('2024-12-31')).toBe(true)
  })

  it('should NOT flag normal business days', () => {
    // 2024-03-18 is Monday
    expect(isAbnormalDate('2024-03-18')).toBe(false)
  })

  it('should return false for empty string', () => {
    expect(isAbnormalDate('')).toBe(false)
  })

  it('should return false for invalid date', () => {
    expect(isAbnormalDate('not-a-date')).toBe(false)
  })
})

// ─── computeSamplingPopulation ───────────────────────────────────────────────

describe('computeSamplingPopulation', () => {
  it('should subtract confirmed specific samples from test population', () => {
    const testPop: PopulationDesc = { amount: 10000000, count: 100, description: '' }
    const specifics: SpecificSampleItem[] = [
      { id: '1', customerName: 'A', amount: 2000000, reason: '大额', confirmed: true },
      { id: '2', customerName: 'B', amount: 1000000, reason: '关联方', confirmed: true },
      { id: '3', customerName: 'C', amount: 500000, reason: '异常', confirmed: false }, // 未确认不扣
    ]
    const result = computeSamplingPopulation(testPop, specifics)
    expect(result.amount).toBe(7000000) // 10000000 - 2000000 - 1000000
    expect(result.count).toBe(98) // 100 - 2 (仅confirmed)
  })

  it('should return test population when no specific samples', () => {
    const testPop: PopulationDesc = { amount: 5000000, count: 50, description: '' }
    const result = computeSamplingPopulation(testPop, [])
    expect(result.amount).toBe(5000000)
    expect(result.count).toBe(50)
  })

  it('should not go below 0', () => {
    const testPop: PopulationDesc = { amount: 100, count: 1, description: '' }
    const specifics: SpecificSampleItem[] = [
      { id: '1', customerName: 'A', amount: 200, reason: '', confirmed: true },
      { id: '2', customerName: 'B', amount: 300, reason: '', confirmed: true },
    ]
    const result = computeSamplingPopulation(testPop, specifics)
    expect(result.amount).toBe(0)
    expect(result.count).toBe(0)
  })

  it('should only subtract confirmed samples', () => {
    const testPop: PopulationDesc = { amount: 5000000, count: 50, description: '' }
    const specifics: SpecificSampleItem[] = [
      { id: '1', customerName: 'A', amount: 1000000, reason: '', confirmed: false },
      { id: '2', customerName: 'B', amount: 1000000, reason: '', confirmed: false },
    ]
    const result = computeSamplingPopulation(testPop, specifics)
    expect(result.amount).toBe(5000000) // 无变化
    expect(result.count).toBe(50)
  })

  it('should include descriptive text', () => {
    const testPop: PopulationDesc = { amount: 5000000, count: 50, description: '' }
    const result = computeSamplingPopulation(testPop, [])
    expect(result.description).toContain('抽样总体')
  })
})

// ─── computeSampleSizeDeviation ──────────────────────────────────────────────

describe('computeSampleSizeDeviation', () => {
  it('should return "below" when user size < recommended', () => {
    expect(computeSampleSizeDeviation(10, 20)).toBe('below')
  })

  it('should return "ok" when user size >= recommended', () => {
    expect(computeSampleSizeDeviation(20, 20)).toBe('ok')
    expect(computeSampleSizeDeviation(30, 20)).toBe('ok')
  })

  it('should return null when recommended is 0', () => {
    expect(computeSampleSizeDeviation(10, 0)).toBe(null)
  })

  it('should return null when user size is 0', () => {
    expect(computeSampleSizeDeviation(0, 20)).toBe(null)
  })

  it('should return null when both are 0', () => {
    expect(computeSampleSizeDeviation(0, 0)).toBe(null)
  })
})

// ─── recommendSamplingMethod ─────────────────────────────────────────────────

describe('recommendSamplingMethod', () => {
  it('should recommend MUS for high risk with positive tolerable misstatement', () => {
    const result = recommendSamplingMethod('高', 1000000)
    expect(result.method).toBe('mus')
    expect(result.reason).toContain('MUS')
    expect(result.reason).toContain('高')
  })

  it('should recommend 特定项目 for high risk with zero tolerable misstatement', () => {
    const result = recommendSamplingMethod('高', 0)
    expect(result.method).toBe('特定项目')
    expect(result.reason).toContain('特定项目')
  })

  it('should recommend 随机抽样 for medium risk', () => {
    const result = recommendSamplingMethod('中', 1000000)
    expect(result.method).toBe('随机抽样')
    expect(result.reason).toContain('90%')
  })

  it('should recommend 随机抽样 for low risk', () => {
    const result = recommendSamplingMethod('低', 1000000)
    expect(result.method).toBe('随机抽样')
    expect(result.reason).toContain('80%')
  })

  it('should always provide a non-empty reason', () => {
    const levels: RiskLevel[] = ['高', '中', '低']
    for (const level of levels) {
      const result = recommendSamplingMethod(level, 500000)
      expect(result.reason.length).toBeGreaterThan(0)
    }
  })
})
