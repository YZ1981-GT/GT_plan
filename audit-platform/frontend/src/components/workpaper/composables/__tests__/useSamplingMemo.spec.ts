/**
 * Unit Tests — 抽样计划与结论备忘导出（buildSamplingMemo）
 *
 * Spec: .kiro/specs/voucher-check-sampling-integration/
 * Task: 13（可选）
 *
 * 覆盖 Requirements：
 * - 21.1 备忘内容含抽样方法、抽样参数、样本量推导依据、覆盖率统计、错报推断与 Sampling_Conclusion
 * - 21.2 以当前抽样批次的实际数据生成备忘内容
 */
import { describe, it, expect } from 'vitest'
import {
  buildSamplingMemo,
  SAMPLING_METHOD_LABELS,
  type SamplingMemoInput,
  type SamplingConfig,
  type CoverageStats,
  type MisstatementResult,
  type SamplingConclusion,
} from '../useSamplingAlgorithms'

// ─── Fixtures ────────────────────────────────────────────────────────────────

function makeConfig(overrides: Partial<SamplingConfig> = {}): SamplingConfig {
  return {
    samplingMethod: 'mus',
    accountCodes: ['2203'],
    periodRange: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    directionFilter: 'all',
    voucherTypeFilter: [],
    summaryKeyword: '',
    excludeExtracted: true,
    randomSeed: null,
    confidenceLevel: 0.95,
    tolerableMisstatement: '500000.00',
    expectedMisstatement: '100000.00',
    suggestedSampleSize: 42,
    ...overrides,
  }
}

const coverageStats: CoverageStats = {
  populationCount: 1200,
  populationAmount: '8000000.00',
  sampleCount: 45,
  sampleAmount: '3200000.00',
  countCoverageRate: '3.75',
  amountCoverageRate: '40.00',
}

const misstatementResult: MisstatementResult = {
  projected: '120000.00',
  knownHighValue: '30000.00',
  basicPrecision: '180000.00',
  incrementalAllowance: '20000.00',
  upperLimit: '350000.00',
}

const acceptedConclusion: SamplingConclusion = {
  accepted: true,
  message: '错报上限（350000.00 元）未超过可容忍错报（500000.00 元），总体可接受。',
}

function makeInput(overrides: Partial<SamplingMemoInput> = {}): SamplingMemoInput {
  return {
    config: makeConfig(),
    coverageStats,
    samplingInterval: '190476.19',
    suggestedSampleSize: 42,
    misstatementResult,
    samplingConclusion: acceptedConclusion,
    seedUsed: 20260710,
    sampleCount: 45,
    generatedAt: '2026-07-10T08:00:00.000Z',
    ...overrides,
  }
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('buildSamplingMemo（R21.1 六大段落齐备）', () => {
  it('包含全部六个必需段落标题（方法/参数/样本量依据/覆盖率/错报推断/结论）', () => {
    const memo = buildSamplingMemo(makeInput())
    expect(memo).toContain('## 一、抽样方法')
    expect(memo).toContain('## 二、抽样参数')
    expect(memo).toContain('## 三、样本量推导依据')
    expect(memo).toContain('## 四、覆盖率统计')
    expect(memo).toContain('## 五、错报推断')
    expect(memo).toContain('## 六、抽样结论（Sampling Conclusion）')
  })

  it('抽样方法段落使用中文方法标签', () => {
    const memo = buildSamplingMemo(makeInput())
    expect(memo).toContain(SAMPLING_METHOD_LABELS.mus)
  })
})

describe('buildSamplingMemo（R21.2 使用当前抽样批次实际数据）', () => {
  it('抽样参数反映实际置信度/可容忍错报/预期错报', () => {
    const memo = buildSamplingMemo(makeInput())
    expect(memo).toContain('置信度（信赖水平）：95%')
    expect(memo).toContain('可容忍错报：500000.00 元')
    expect(memo).toContain('预期错报：100000.00 元')
  })

  it('样本量推导依据反映建议样本量、实际样本量与 MUS 抽样间隔', () => {
    const memo = buildSamplingMemo(makeInput())
    expect(memo).toContain('系统建议样本量：42 笔')
    expect(memo).toContain('实际样本量：45 笔')
    expect(memo).toContain('MUS 抽样间隔：190476.19 元')
  })

  it('覆盖率统计反映实际总体/样本笔数金额与覆盖率', () => {
    const memo = buildSamplingMemo(makeInput())
    expect(memo).toContain('总体笔数：1200 笔')
    expect(memo).toContain('总体金额：8000000.00 元')
    expect(memo).toContain('样本笔数：45 笔')
    expect(memo).toContain('笔数覆盖率：3.75%')
    expect(memo).toContain('金额覆盖率：40.00%')
  })

  it('错报推断反映推断错报与错报上限 UML', () => {
    const memo = buildSamplingMemo(makeInput())
    expect(memo).toContain('推断错报：120000.00 元')
    expect(memo).toContain('错报上限（UML）：350000.00 元')
  })

  it('抽样结论反映可接受结论及说明文案', () => {
    const memo = buildSamplingMemo(makeInput())
    expect(memo).toContain('结论：总体可接受')
    expect(memo).toContain(acceptedConclusion.message)
  })

  it('附段落反映随机种子与重抽原因（R22 留痕）', () => {
    const memo = buildSamplingMemo(
      makeInput({ config: makeConfig({ resampleReason: '样本代表性不足' }) }),
    )
    expect(memo).toContain('随机种子：20260710')
    expect(memo).toContain('重抽原因：样本代表性不足')
  })
})

describe('buildSamplingMemo（可选数据缺失时不臆造、以占位符呈现）', () => {
  it('无覆盖率/错报推断/结论时给出占位说明而非崩溃', () => {
    const memo = buildSamplingMemo(
      makeInput({
        coverageStats: null,
        misstatementResult: null,
        samplingConclusion: null,
        samplingInterval: null,
        suggestedSampleSize: null,
        seedUsed: null,
        config: makeConfig({
          tolerableMisstatement: undefined,
          expectedMisstatement: undefined,
          confidenceLevel: undefined,
        }),
      }),
    )
    expect(memo).toContain('暂无覆盖率数据（尚未执行抽样）')
    expect(memo).toContain('暂无错报推断数据（尚未录入样本实际错报）')
    expect(memo).toContain('暂无结论（请先填写可容忍错报并完成错报推断）')
    expect(memo).toContain('置信度（信赖水平）：—')
    expect(memo).toContain('可容忍错报：—')
    expect(memo).toContain('随机种子：—')
    expect(memo).toContain('重抽原因：—')
  })

  it('非 MUS 随机抽样时段落结构完整且方法标签正确', () => {
    const memo = buildSamplingMemo(
      makeInput({ config: makeConfig({ samplingMethod: 'random' }) }),
    )
    expect(memo).toContain(SAMPLING_METHOD_LABELS.random)
    expect(memo).toContain('## 三、样本量推导依据')
  })
})
