/**
 * useSamplingAlgorithms — 单元测试
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 15.1
 *
 * 测试范围：
 * - computeCoverage：边界值（population=0 → 0%，sample=population → 100%）
 * - checkCAS1314Compliance：各阈值边界触发验证
 * - validateSamplingConfig：各方法缺必填 → errors 非空
 * - computeVersionDiff：空集/完全相同/完全不同
 */
import { describe, it, expect } from 'vitest'

import {
  computeCoverage,
  checkCAS1314Compliance,
  type ComplianceCheckInput,
  validateSamplingConfig,
  computeVersionDiff,
  type SamplingConfig,
  type CoverageStats,
} from '../composables/useSamplingAlgorithms'
import {
  DEFAULT_COVERAGE_THRESHOLD,
  THRESHOLD_SOURCE_LABELS,
} from '../composables/samplingCoverageThreshold'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeBaseConfig(overrides?: Partial<SamplingConfig>): SamplingConfig {
  return {
    samplingMethod: 'random',
    sampleSize: 30,
    accountCodes: ['1122'],
    periodRange: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    directionFilter: 'all',
    voucherTypeFilter: [],
    summaryKeyword: '',
    excludeExtracted: true,
    randomSeed: null,
    ...overrides,
  }
}

function makeStats(overrides?: Partial<CoverageStats>): CoverageStats {
  return {
    populationCount: 100,
    populationAmount: '1000000.00',
    sampleCount: 30,
    sampleAmount: '300000.00',
    countCoverageRate: '30.00',
    amountCoverageRate: '30.00',
    ...overrides,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. computeCoverage
// ═══════════════════════════════════════════════════════════════════════════════

describe('computeCoverage', () => {
  it('populationCount=0 → countCoverageRate="0.00"', () => {
    const result = computeCoverage(0, '1000.00', 0, '0')
    expect(result.countCoverageRate).toBe('0.00')
  })

  it('populationAmount="0" → amountCoverageRate="0.00"', () => {
    const result = computeCoverage(100, '0', 50, '500.00')
    expect(result.amountCoverageRate).toBe('0.00')
  })

  it('sample=population → countCoverageRate="100.00"', () => {
    const result = computeCoverage(50, '10000.00', 50, '10000.00')
    expect(result.countCoverageRate).toBe('100.00')
    expect(result.amountCoverageRate).toBe('100.00')
  })

  it('正常计算精度2位小数', () => {
    const result = computeCoverage(300, '90000.00', 100, '30000.00')
    expect(result.countCoverageRate).toBe('33.33')
    expect(result.amountCoverageRate).toBe('33.33')
  })

  it('返回对象包含所有原始字段', () => {
    const result = computeCoverage(200, '50000.00', 60, '15000.00')
    expect(result.populationCount).toBe(200)
    expect(result.populationAmount).toBe('50000.00')
    expect(result.sampleCount).toBe(60)
    expect(result.sampleAmount).toBe('15000.00')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. checkCAS1314Compliance
// ═══════════════════════════════════════════════════════════════════════════════

describe('checkCAS1314Compliance', () => {
  /**
   * 入参构造器：默认给一组「不触发任何告警」的基线，各用例只覆盖关心的字段。
   *
   * 签名于 sampling-evaluation-and-governance-closure R2 由位置参数改为 options 对象 ——
   * 原签名 `(stats, method, sampleCount, totalCount)` 的后两个参数在调用点被传成
   * 「勾选数 / 抽出总数」，与规则语义不符（详见 ComplianceCheckInput 的文档注释）。
   */
  const makeInput = (over: Partial<ComplianceCheckInput> = {}): ComplianceCheckInput => ({
    stats: makeStats({ amountCoverageRate: '80.00' }),
    method: 'random',
    methodSampleCount: 30,
    totalSampleCount: 100,
    suggestedSampleSize: null,
    coverageThreshold: DEFAULT_COVERAGE_THRESHOLD,
    coverageThresholdLabel: THRESHOLD_SOURCE_LABELS.platform_default,
    ...over,
  })

  it('金额覆盖率低于阈值 → coverage_low warning', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({ stats: makeStats({ amountCoverageRate: '59.99' }) }),
    )
    expect(warnings.some(w => w.type === 'coverage_low')).toBe(true)
  })

  it('金额覆盖率 = 阈值 → 不触发 coverage_low（边界含等号侧不告警）', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({ stats: makeStats({ amountCoverageRate: '60.00' }) }),
    )
    expect(warnings.some(w => w.type === 'coverage_low')).toBe(false)
  })

  it('金额覆盖率高于阈值 → 不触发 coverage_low', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({ stats: makeStats({ amountCoverageRate: '75.00' }) }),
    )
    expect(warnings.some(w => w.type === 'coverage_low')).toBe(false)
  })

  it('阈值可配：传 0.8 时 75% 覆盖率转为告警（改造前 60% 写死在函数体内）', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({
        stats: makeStats({ amountCoverageRate: '75.00' }),
        coverageThreshold: 0.8,
        coverageThresholdLabel: THRESHOLD_SOURCE_LABELS.project,
      }),
    )
    expect(warnings.some(w => w.type === 'coverage_low')).toBe(true)
  })

  it('覆盖率告警文案明示阈值取值与来源（R2.8）', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({
        stats: makeStats({ amountCoverageRate: '10.00' }),
        coverageThresholdLabel: THRESHOLD_SOURCE_LABELS.platform_default,
      }),
    )
    const msg = warnings.find(w => w.type === 'coverage_low')!.message
    expect(msg).toContain('60%')
    expect(msg).toContain(THRESHOLD_SOURCE_LABELS.platform_default)
  })

  it('specific_item 占比 > 50% → specific_item_high suggestion', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({ method: 'specific_item', methodSampleCount: 51, totalSampleCount: 100 }),
    )
    expect(warnings.some(w => w.type === 'specific_item_high')).toBe(true)
    expect(warnings.find(w => w.type === 'specific_item_high')!.level).toBe('suggestion')
  })

  it('specific_item 占比 = 50% → 不触发', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({ method: 'specific_item', methodSampleCount: 50, totalSampleCount: 100 }),
    )
    expect(warnings.some(w => w.type === 'specific_item_high')).toBe(false)
  })

  it('specific_item 分母等于分子（底稿无其它方法样本）→ 判据不可用，不告警', () => {
    // 改造前此处传的是「勾选数 / 抽出总数」，审计师全选时比值恒为 1 → 必然告警（纯噪声）
    const warnings = checkCAS1314Compliance(
      makeInput({ method: 'specific_item', methodSampleCount: 40, totalSampleCount: 40 }),
    )
    expect(warnings.some(w => w.type === 'specific_item_high')).toBe(false)
  })

  it('非 specific_item 方法 → 不检查占比', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({ method: 'random', methodSampleCount: 80, totalSampleCount: 100 }),
    )
    expect(warnings.some(w => w.type === 'specific_item_high')).toBe(false)
  })

  it('MUS 实际样本量 < 系统建议样本量 → mus_insufficient warning', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({ method: 'mus', totalSampleCount: 5, suggestedSampleSize: 10 }),
    )
    expect(warnings.some(w => w.type === 'mus_insufficient')).toBe(true)
  })

  it('MUS 实际样本量 >= 系统建议样本量 → 不触发', () => {
    const warnings = checkCAS1314Compliance(
      makeInput({ method: 'mus', totalSampleCount: 10, suggestedSampleSize: 10 }),
    )
    expect(warnings.some(w => w.type === 'mus_insufficient')).toBe(false)
  })

  it('MUS 建议样本量为 null（参数不足推不出）→ 不告警：判据不可用 ≠ 不合规', () => {
    // 改造前判据是「勾选数 < 抽出总数」= 有没有全选，与样本量充分性无关：
    // 不全选必告警且文案说"低于期望样本量"，全选则永远不告警。
    const warnings = checkCAS1314Compliance(
      makeInput({ method: 'mus', totalSampleCount: 1, suggestedSampleSize: null }),
    )
    expect(warnings.some(w => w.type === 'mus_insufficient')).toBe(false)
  })

  it('MUS 判据与勾选无关：同一实际样本量下结果一致', () => {
    const base = { method: 'mus' as const, totalSampleCount: 10, suggestedSampleSize: 10 }
    const a = checkCAS1314Compliance(makeInput({ ...base, methodSampleCount: 1 }))
    const b = checkCAS1314Compliance(makeInput({ ...base, methodSampleCount: 10 }))
    expect(a.map(w => w.type)).toEqual(b.map(w => w.type))
  })

  it('无警告时返回空数组', () => {
    expect(checkCAS1314Compliance(makeInput())).toHaveLength(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. validateSamplingConfig
// ═══════════════════════════════════════════════════════════════════════════════

describe('validateSamplingConfig', () => {
  it('通用校验：accountCodes 为空 → errors.accountCodes', () => {
    const config = makeBaseConfig({ accountCodes: [] })
    const errors = validateSamplingConfig(config)
    expect(errors.accountCodes).toBeDefined()
  })

  describe('random 方法', () => {
    it('sampleSize 未设置 → errors.sampleSize', () => {
      const config = makeBaseConfig({ samplingMethod: 'random', sampleSize: 0 })
      const errors = validateSamplingConfig(config)
      expect(errors.sampleSize).toBeDefined()
    })

    it('sampleSize > 0 → 无 sampleSize 错误', () => {
      const config = makeBaseConfig({ samplingMethod: 'random', sampleSize: 10 })
      const errors = validateSamplingConfig(config)
      expect(errors.sampleSize).toBeUndefined()
    })
  })

  describe('stratified 方法', () => {
    it('strata 为空数组 → errors.strata', () => {
      const config = makeBaseConfig({ samplingMethod: 'stratified', strata: [] })
      const errors = validateSamplingConfig(config)
      expect(errors.strata).toBeDefined()
    })

    it('strata 未定义 → errors.strata', () => {
      const config = makeBaseConfig({ samplingMethod: 'stratified', strata: undefined })
      const errors = validateSamplingConfig(config)
      expect(errors.strata).toBeDefined()
    })

    it('lowerBound >= upperBound → 层级边界错误', () => {
      const config = makeBaseConfig({
        samplingMethod: 'stratified',
        strata: [{ lowerBound: '100', upperBound: '50', sampleSize: 5 }],
      })
      const errors = validateSamplingConfig(config)
      expect(errors.strata_0_bounds).toBeDefined()
    })

    it('层级 sampleSize=0 → 层级样本量错误', () => {
      const config = makeBaseConfig({
        samplingMethod: 'stratified',
        strata: [{ lowerBound: '0', upperBound: '100', sampleSize: 0 }],
      })
      const errors = validateSamplingConfig(config)
      expect(errors.strata_0_sampleSize).toBeDefined()
    })
  })

  describe('specific_item 方法', () => {
    it('materialityThreshold 为空 → errors.materialityThreshold', () => {
      const config = makeBaseConfig({ samplingMethod: 'specific_item', materialityThreshold: '' })
      const errors = validateSamplingConfig(config)
      expect(errors.materialityThreshold).toBeDefined()
    })

    it('materialityThreshold = "0" → errors.materialityThreshold', () => {
      const config = makeBaseConfig({ samplingMethod: 'specific_item', materialityThreshold: '0' })
      const errors = validateSamplingConfig(config)
      expect(errors.materialityThreshold).toBeDefined()
    })

    it('materialityThreshold > 0 → 无错误', () => {
      const config = makeBaseConfig({ samplingMethod: 'specific_item', materialityThreshold: '50000' })
      const errors = validateSamplingConfig(config)
      expect(errors.materialityThreshold).toBeUndefined()
    })
  })

  describe('systematic 方法', () => {
    it('startPoint < 1 → errors.startPoint', () => {
      const config = makeBaseConfig({ samplingMethod: 'systematic', startPoint: 0, interval: 5 })
      const errors = validateSamplingConfig(config)
      expect(errors.startPoint).toBeDefined()
    })

    it('interval < 2 → errors.interval', () => {
      const config = makeBaseConfig({ samplingMethod: 'systematic', startPoint: 1, interval: 1 })
      const errors = validateSamplingConfig(config)
      expect(errors.interval).toBeDefined()
    })

    it('startPoint=1, interval=2 → 无错误', () => {
      const config = makeBaseConfig({ samplingMethod: 'systematic', startPoint: 1, interval: 2 })
      const errors = validateSamplingConfig(config)
      expect(errors.startPoint).toBeUndefined()
      expect(errors.interval).toBeUndefined()
    })
  })

  describe('mus 方法', () => {
    it('musSampleSize 未设置 → errors.musSampleSize', () => {
      const config = makeBaseConfig({ samplingMethod: 'mus', musSampleSize: 0 })
      const errors = validateSamplingConfig(config)
      expect(errors.musSampleSize).toBeDefined()
    })

    it('musSampleSize > 0 → 无错误', () => {
      const config = makeBaseConfig({ samplingMethod: 'mus', musSampleSize: 20 })
      const errors = validateSamplingConfig(config)
      expect(errors.musSampleSize).toBeUndefined()
    })
  })

  it('完整有效配置 → 空 errors', () => {
    const config = makeBaseConfig({ samplingMethod: 'random', sampleSize: 30 })
    const errors = validateSamplingConfig(config)
    expect(Object.keys(errors)).toHaveLength(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. computeVersionDiff
// ═══════════════════════════════════════════════════════════════════════════════

describe('computeVersionDiff', () => {
  it('两个空数组 → 全部为空', () => {
    const result = computeVersionDiff([], [])
    expect(result.added).toHaveLength(0)
    expect(result.removed).toHaveLength(0)
    expect(result.retained).toHaveLength(0)
  })

  it('完全相同 → retained=全部, added/removed=空', () => {
    const result = computeVersionDiff(['V-001', 'V-002'], ['V-001', 'V-002'])
    expect(result.retained).toEqual(expect.arrayContaining(['V-001', 'V-002']))
    expect(result.retained).toHaveLength(2)
    expect(result.added).toHaveLength(0)
    expect(result.removed).toHaveLength(0)
  })

  it('完全不同 → added=B, removed=A, retained=空', () => {
    const result = computeVersionDiff(['V-001', 'V-002'], ['V-003', 'V-004'])
    expect(result.removed).toEqual(expect.arrayContaining(['V-001', 'V-002']))
    expect(result.removed).toHaveLength(2)
    expect(result.added).toEqual(expect.arrayContaining(['V-003', 'V-004']))
    expect(result.added).toHaveLength(2)
    expect(result.retained).toHaveLength(0)
  })

  it('A 为空 → added=B 全部', () => {
    const result = computeVersionDiff([], ['V-001', 'V-002'])
    expect(result.added).toHaveLength(2)
    expect(result.removed).toHaveLength(0)
    expect(result.retained).toHaveLength(0)
  })

  it('B 为空 → removed=A 全部', () => {
    const result = computeVersionDiff(['V-001', 'V-002'], [])
    expect(result.removed).toHaveLength(2)
    expect(result.added).toHaveLength(0)
    expect(result.retained).toHaveLength(0)
  })

  it('部分重叠正确分区', () => {
    const result = computeVersionDiff(['V-001', 'V-002', 'V-003'], ['V-002', 'V-003', 'V-004'])
    expect(result.retained).toEqual(expect.arrayContaining(['V-002', 'V-003']))
    expect(result.retained).toHaveLength(2)
    expect(result.removed).toEqual(['V-001'])
    expect(result.added).toEqual(['V-004'])
  })

  it('重复元素自动去重（集合语义）', () => {
    const result = computeVersionDiff(['V-001', 'V-001'], ['V-001', 'V-002'])
    expect(result.retained).toHaveLength(1)
    expect(result.retained).toContain('V-001')
    expect(result.added).toHaveLength(1)
    expect(result.added).toContain('V-002')
  })
})
