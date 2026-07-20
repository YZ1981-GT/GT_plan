/**
 * G9-6 凭证检查 — 异常判定 / 三态核对 / 默认未测 / 抽样参数
 */
import { describe, it, expect } from 'vitest'
import {
  enrichG9VoucherRow,
  recalcG9VoucherAbnormal,
  parseG9CheckState,
  formatG9CheckState,
  isG9VoucherFullyChecked,
  countG9VoucherUntested,
  parseG9SamplingParams,
  mapSampledToG9VoucherRow,
  computeG9AnomalyRate,
  calcG9SampleAbsAmount,
  calcG9CoverageRates,
  calcG9VoucherCompletion,
  buildG9VoucherSamplingMemo,
  deriveG9AbnormalType,
  filterG9VoucherRowsBySource,
  type G9VoucherRow,
} from '../useG9VoucherCheck'
import { isG9SheetComplete } from '../g9SheetLabels'
import { mapCutoffToG9Voucher } from '../gCycleCutoffFill'
import type { ExtractedVoucher } from '../useCutoffAutoSampling'

function allPass(overrides: Partial<G9VoucherRow> = {}): G9VoucherRow {
  return enrichG9VoucherRow({
    voucherNo: '记-001',
    checkOriginal: true,
    checkAuthorized: true,
    checkAccounting: true,
    checkClassification: true,
    checkFairValue: true,
    checkImpairment: true,
    ...overrides,
  }, 1)
}

describe('parseG9CheckState', () => {
  it('空值与未测 → null', () => {
    expect(parseG9CheckState(null)).toBeNull()
    expect(parseG9CheckState(undefined)).toBeNull()
    expect(parseG9CheckState('')).toBeNull()
    expect(parseG9CheckState('未测')).toBeNull()
  })

  it('是/否映射', () => {
    expect(parseG9CheckState(true)).toBe(true)
    expect(parseG9CheckState('是')).toBe(true)
    expect(parseG9CheckState(false)).toBe(false)
    expect(parseG9CheckState('否')).toBe(false)
  })
})

describe('enrichG9VoucherRow 默认未测', () => {
  it('新建行核对项默认为 null', () => {
    const row = enrichG9VoucherRow({ voucherNo: '记-1' }, 1)
    expect(row.checkOriginal).toBeNull()
    expect(row.checkImpairment).toBeNull()
    expect(row.isAbnormal).toBe(false)
    expect(row.forceAbnormal).toBe(false)
    expect(isG9VoucherFullyChecked(row)).toBe(false)
  })

  it('旧数据显式 true 保持通过', () => {
    const row = allPass()
    expect(row.isAbnormal).toBe(false)
    expect(isG9VoucherFullyChecked(row)).toBe(true)
  })
})

describe('recalcG9VoucherAbnormal 无粘滞', () => {
  it('未测不计入异常', () => {
    const row = enrichG9VoucherRow({ voucherNo: 'x' }, 1)
    expect(row.isAbnormal).toBe(false)
  })

  it('任一不通过 → 异常', () => {
    const row = allPass({ checkFairValue: false })
    expect(row.isAbnormal).toBe(true)
    expect(deriveG9AbnormalType(row)).toBe('quantitative')
  })

  it('分类不通过 → 定性异常', () => {
    const row = allPass({ checkClassification: false })
    expect(row.isAbnormal).toBe(true)
    expect(deriveG9AbnormalType(row)).toBe('qualitative')
  })

  it('核对全部改回通过后异常自动清除（无 force）', () => {
    let row = allPass({ checkAccounting: false })
    expect(row.isAbnormal).toBe(true)
    row = recalcG9VoucherAbnormal({
      ...row,
      checkAccounting: true,
      forceAbnormal: false,
    })
    expect(row.isAbnormal).toBe(false)
  })

  it('forceAbnormal 在核对通过后仍保持异常，取消 force 后清除', () => {
    let row = allPass({ forceAbnormal: true })
    expect(row.isAbnormal).toBe(true)
    row = recalcG9VoucherAbnormal({ ...row, forceAbnormal: false })
    expect(row.isAbnormal).toBe(false)
  })
})

describe('formatG9CheckState / countG9VoucherUntested', () => {
  it('格式化三态', () => {
    expect(formatG9CheckState(true)).toBe('✓')
    expect(formatG9CheckState(false)).toBe('✗')
    expect(formatG9CheckState(null)).toBe('未测')
  })

  it('统计未测笔数', () => {
    const rows = [
      enrichG9VoucherRow({ voucherNo: 'a' }, 1),
      allPass(),
    ]
    expect(countG9VoucherUntested(rows)).toBe(1)
  })
})

describe('抽样参数与覆盖率', () => {
  it('parseG9SamplingParams 健壮', () => {
    expect(parseG9SamplingParams(null).targetSampleSize).toBe(0)
    expect(parseG9SamplingParams('{"targetSampleSize":10}').targetSampleSize).toBe(10)
  })

  it('样本发生额取 max(借,贷)', () => {
    expect(calcG9SampleAbsAmount([
      { debitAmount: 100, creditAmount: 0 },
      { debitAmount: 0, creditAmount: 50 },
    ])).toBe(150)
  })

  it('覆盖率与完成度', () => {
    const rows = [allPass({ debitAmount: 1000, source: '抽凭' })]
    const coverage = calcG9CoverageRates(rows, {
      targetSampleSize: 5,
      currentSampleSize: 1,
      populationCount: 10,
      populationAmount: 10000,
    })
    expect(coverage.countPct).toBe(10)
    expect(coverage.amountPct).toBe(10)

    const completion = calcG9VoucherCompletion({
      params: {
        ...parseG9SamplingParams(null),
        samplingMethod: 'MUS',
        targetSampleSize: 1,
        currentSampleSize: 1,
      },
      rows,
      conclusion: '未见异常',
    })
    expect(completion.pct).toBe(100)
  })

  it('抽样备忘含科目 1504', () => {
    const md = buildG9VoucherSamplingMemo({
      params: parseG9SamplingParams('{"samplingMethod":"随机"}'),
      rows: [allPass()],
      conclusion: 'ok',
      coverage: { countPct: 100, amountPct: 0, sampleAbsAmount: 0 },
    })
    expect(md).toContain('1504')
    expect(md).toContain('G9-6')
  })
})

describe('抽凭/截止映射', () => {
  it('mapSampledToG9VoucherRow 默认未测', () => {
    const row = mapSampledToG9VoucherRow({ voucherNo: 'v1', amount: 100 }, 1)
    expect(row.source).toBe('抽凭')
    expect(row.checkOriginal).toBeNull()
    expect(row.debitAmount).toBe(100)
  })

  it('截止跨期 forceAbnormal 且核对未测', () => {
    const v: ExtractedVoucher = {
      voucherNo: '记-99',
      voucherDate: '2025-01-05',
      summary: '跨期',
      debitAmount: '100',
      creditAmount: '0',
      accountCode: '1504',
      accountName: '其他非流动金融资产',
      counterpartAccount: null,
      voucherType: null,
      cutoffStatus: '可能跨期',
      remark: '跨期疑点',
      selected: true,
    }
    const row = enrichG9VoucherRow(mapCutoffToG9Voucher(v, 1), 1)
    expect(row.source).toBe('截止')
    expect(row.forceAbnormal).toBe(true)
    expect(row.isAbnormal).toBe(true)
    expect(row.checkOriginal).toBeNull()
  })
})

describe('来源分池 / sheet 完成', () => {
  it('filter by source', () => {
    const rows = [
      allPass({ source: '抽凭' }),
      allPass({ source: '截止' }),
      allPass({ source: '' }),
    ]
    expect(filterG9VoucherRowsBySource(rows, '抽凭')).toHaveLength(1)
    expect(filterG9VoucherRowsBySource(rows, '手工')).toHaveLength(1)
  })

  it('异常率', () => {
    expect(computeG9AnomalyRate([allPass(), allPass({ checkImpairment: false })])).toBe(50)
  })

  it('isG9SheetComplete G9-6', () => {
    const m = new Map()
    expect(isG9SheetComplete('G9-6', m)).toBe(false)
    m.set('G9-voucher-rows', { remark: JSON.stringify([allPass()]) })
    expect(isG9SheetComplete('G9-6', m)).toBe(true)
  })
})
