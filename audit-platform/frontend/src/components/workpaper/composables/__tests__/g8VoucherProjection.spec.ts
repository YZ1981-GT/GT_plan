import { describe, it, expect } from 'vitest'
import {
  suggestG8ActualMisstatement,
  resolveG8ProjectionMethod,
  computeG8Projection,
  formatG8ProjectionMemoSection,
  mapG8RowsToProjectionSamples,
} from '../g8VoucherProjection'
import { enrichG8VoucherRow, defaultG8SamplingParams } from '../useG8VoucherCheck'

describe('g8VoucherProjection', () => {
  it('suggestG8ActualMisstatement 仅金额/混合异常', () => {
    const quant = enrichG8VoucherRow({
      voucherNo: '1',
      debitAmount: 1000,
      creditAmount: 0,
      check4FairValueCorrect: false,
    }, 1)
    expect(quant.abnormalType).toBe('quantitative')
    expect(suggestG8ActualMisstatement(quant)).toBe(1000)

    const qual = enrichG8VoucherRow({
      voucherNo: '2',
      debitAmount: 500,
      check2Authorization: false,
    }, 2)
    expect(qual.abnormalType).toBe('qualitative')
    expect(suggestG8ActualMisstatement(qual)).toBe(0)
  })

  it('resolveG8ProjectionMethod', () => {
    expect(resolveG8ProjectionMethod('MUS')).toBe('mus')
    expect(resolveG8ProjectionMethod('货币单元')).toBe('mus')
    expect(resolveG8ProjectionMethod('随机')).toBe('random')
    expect(resolveG8ProjectionMethod('')).toBe('random')
  })

  it('无总体/可容忍 → 不可推断', () => {
    const rows = [enrichG8VoucherRow({
      voucherNo: '1', debitAmount: 100, check4FairValueCorrect: false, actualMisstatement: 50,
    }, 1)]
    const v1 = computeG8Projection({
      rows,
      params: { ...defaultG8SamplingParams(), populationAmount: 0, tolerableMisstatement: 1000 },
    })
    expect(v1.canProject).toBe(false)
    expect(v1.reason).toContain('总体金额')

    const v2 = computeG8Projection({
      rows,
      params: { ...defaultG8SamplingParams(), populationAmount: 10000, tolerableMisstatement: 0 },
    })
    expect(v2.canProject).toBe(false)
    expect(v2.reason).toContain('可容忍')
  })

  it('经典比率：UML 与可接受结论', () => {
    const rows = [
      enrichG8VoucherRow({
        voucherNo: 'a',
        debitAmount: 1000,
        check4FairValueCorrect: false,
        actualMisstatement: 100,
      }, 1),
      enrichG8VoucherRow({
        voucherNo: 'b',
        debitAmount: 1000,
        check4FairValueCorrect: false,
        actualMisstatement: 0,
      }, 2),
    ]
    const view = computeG8Projection({
      rows,
      params: {
        ...defaultG8SamplingParams(),
        samplingMethod: 'random',
        populationAmount: 10000,
        tolerableMisstatement: 5000,
        confidenceLevel: 0.95,
      },
    })
    expect(view.canProject).toBe(true)
    expect(view.method).toBe('random')
    expect(view.sampleCount).toBe(2)
    expect(view.withMisstatementCount).toBe(1)
    expect(view.missingMisstatementCount).toBe(1)
    expect(view.result).toBeTruthy()
    // projected = (100/2000)*10000 = 500；UML = projected + incremental
    expect(Number(view.result!.projected)).toBeCloseTo(500, 0)
    expect(Number(view.uml)).toBeGreaterThanOrEqual(500)
    expect(view.conclusion?.accepted).toBe(true)

    const memo = formatG8ProjectionMemoSection(view)
    expect(memo).toContain('错报推断')
    expect(memo).toContain('UML')
  })

  it('mapG8RowsToProjectionSamples useSuggestedWhenEmpty', () => {
    const row = enrichG8VoucherRow({
      voucherNo: 'x',
      debitAmount: 800,
      check4FairValueCorrect: false,
    }, 1)
    const samples = mapG8RowsToProjectionSamples([row], true)
    expect(samples).toHaveLength(1)
    expect(Number(samples[0].actualMisstatement)).toBe(800)
  })

  it('UML 超过可容忍 → 不可接受', () => {
    const rows = [enrichG8VoucherRow({
      voucherNo: 'big',
      debitAmount: 5000,
      check4FairValueCorrect: false,
      actualMisstatement: 5000,
    }, 1)]
    const view = computeG8Projection({
      rows,
      params: {
        ...defaultG8SamplingParams(),
        populationAmount: 10000,
        tolerableMisstatement: 100,
        confidenceLevel: 0.95,
      },
    })
    expect(view.canProject).toBe(true)
    expect(view.conclusion?.accepted).toBe(false)
  })
})
