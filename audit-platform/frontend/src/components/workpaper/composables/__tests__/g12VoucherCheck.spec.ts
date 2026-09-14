import { describe, it, expect } from 'vitest'
import {
  enrichG12VoucherRow,
  recalcG12VoucherAbnormal,
  buildG12VoucherSamplingMemo,
} from '../useG12VoucherCheck'
import {
  g12VoucherInspectionRatio,
  calcG12SampleAbsAmount,
  parseG12CheckState,
  defaultG12SamplingParams,
} from '../g12VoucherConstants'
import {
  isG12QuantitativeVoucherAbnormal,
  calcG12PopulationHint,
  formatG12SamplingProcessFromMethodology,
  buildG12NetExposureLinkHints,
  applyG12NetExposureLinkHints,
  formatG12FvValuationBasis,
  citeG12FvValuationToVoucher,
  batchCiteG12FvValuation,
} from '../g12VoucherCross'
import type { ChecklistResponse } from '../useF1FormData'

describe('G12 voucher check enrich', () => {
  it('migrates legacy check5FVValuation to check6FVValuation', () => {
    const row = enrichG12VoucherRow({
      rowId: 'r1',
      check5FVValuation: false,
    }, 1)
    expect(row.check6FVValuation).toBe(false)
    expect(row.isAbnormal).toBe(true)
  })

  it('defaults new checks to null (未测)', () => {
    const row = enrichG12VoucherRow({ rowId: 'r2' }, 1)
    expect(row.check1OriginalComplete).toBe(null)
    expect(row.isAbnormal).toBe(false)
  })

  it('forceAbnormal marks abnormal without failed checks', () => {
    const row = recalcG12VoucherAbnormal(enrichG12VoucherRow({
      rowId: 'r3',
      forceAbnormal: true,
    }, 1))
    expect(row.isAbnormal).toBe(true)
  })
})

describe('G12 inspection ratio', () => {
  it('calcG12SampleAbsAmount uses max debit/credit', () => {
    expect(calcG12SampleAbsAmount([
      { debitAmount: 100, creditAmount: 0 },
      { debitAmount: 0, creditAmount: 200 },
    ])).toBe(300)
  })

  it('g12VoucherInspectionRatio returns null when population is zero', () => {
    expect(g12VoucherInspectionRatio(1000, 0)).toBe(null)
    expect(g12VoucherInspectionRatio(300, 1000)).toBe(0.3)
  })
})

describe('G12 quantitative abnormal', () => {
  it('isG12QuantitativeVoucherAbnormal detects FV/hedge accounting failures', () => {
    const row = enrichG12VoucherRow({
      rowId: 'q1',
      creditAmount: 5000,
      check6FVValuation: false,
    }, 1)
    expect(isG12QuantitativeVoucherAbnormal(row)).toBe(true)
  })
})

describe('G12 population hint', () => {
  it('calcG12PopulationHint sums profitLossAmount from hedge detail', () => {
    const map = new Map([
      ['G12-hedge-detail-rows', {
        remark: JSON.stringify([
          { profitLossAmount: 100 },
          { profitLossAmount: -30 },
        ]),
      }],
    ])
    expect(calcG12PopulationHint(map as Map<string, ChecklistResponse>)).toBe(130)
  })
})

describe('parseG12CheckState', () => {
  it('parses tri-state labels', () => {
    expect(parseG12CheckState('通过')).toBe(true)
    expect(parseG12CheckState('不通过')).toBe(false)
    expect(parseG12CheckState('未测')).toBe(null)
  })
})

describe('buildG12VoucherSamplingMemo', () => {
  it('includes inspection ratio in memo', () => {
    const md = buildG12VoucherSamplingMemo({
      params: { ...defaultG12SamplingParams(), populationAmount: 10000, testPopulation: '6103' },
      rows: [enrichG12VoucherRow({ rowId: 'm1', creditAmount: 3000 }, 1)],
      auditNote: '测试说明',
      auditConclusion: '未见异常',
    })
    expect(md).toContain('G12-6')
    expect(md).toContain('检查比例')
    expect(md).toContain('30.0%')
  })
})

describe('MUS methodology → samplingProcess', () => {
  it('formatG12SamplingProcessFromMethodology includes MUS interval', () => {
    const text = formatG12SamplingProcessFromMethodology({
      samplingMethod: 'mus',
      samplingInterval: '597014.93',
      sampleSize: 10,
      suggestedSampleSize: 12,
      tolerableMisstatement: 1000000,
      expectedMisstatement: 0,
      confidenceLevel: 0.95,
      accountCodes: ['6103'],
      randomSeed: 'abc',
    })
    expect(text).toContain('货币单位抽样')
    expect(text).toContain('MUS间隔=597014.93')
    expect(text).toContain('可容忍错报=1000000')
    expect(text).toContain('科目=6103')
  })
})

describe('G12-5 net exposure link by hedgeRelationId', () => {
  it('buildG12NetExposureLinkHints matches complete rows', () => {
    const map = new Map([
      ['G12-net-exposure-rows', {
        remark: JSON.stringify([
          {
            hedgeRelationId: 'HR-001',
            item: '外汇净头寸',
            position1Desc: '销售',
            position2Desc: '采购',
            netPosition: '净支付100',
          },
        ]),
      }],
    ]) as Map<string, ChecklistResponse>
    const rows = [
      enrichG12VoucherRow({ rowId: 'v1', hedgeRelationId: 'HR-001' }, 1),
      enrichG12VoucherRow({ rowId: 'v2', hedgeRelationId: 'HR-999' }, 2),
      enrichG12VoucherRow({ rowId: 'v3' }, 3),
    ]
    const hints = buildG12NetExposureLinkHints(rows, map)
    expect(hints.find((h) => h.voucherRowId === 'v1')?.status).toBe('ok')
    expect(hints.find((h) => h.voucherRowId === 'v2')?.status).toBe('missing')
    expect(hints.find((h) => h.voucherRowId === 'v3')?.status).toBe('no_id')
  })

  it('applyG12NetExposureLinkHints sets check5 only when untested', () => {
    const rows = [
      enrichG12VoucherRow({ rowId: 'v1', hedgeRelationId: 'HR-001' }, 1),
      enrichG12VoucherRow({ rowId: 'v2', hedgeRelationId: 'HR-001', check5HedgeAccounting: false }, 2),
    ]
    const hints = [
      { voucherRowId: 'v1', hedgeRelationId: 'HR-001', status: 'ok' as const, message: 'ok', suggestCheck5: true },
      { voucherRowId: 'v2', hedgeRelationId: 'HR-001', status: 'ok' as const, message: 'ok', suggestCheck5: true },
    ]
    const { updated, rows: next } = applyG12NetExposureLinkHints(rows, hints)
    expect(updated).toBe(1)
    expect(next[0].check5HedgeAccounting).toBe(true)
    expect(next[1].check5HedgeAccounting).toBe(false)
  })
})

describe('G12-4 FV cite to check6', () => {
  it('formatG12FvValuationBasis builds label', () => {
    expect(formatG12FvValuationBasis({
      instrumentName: 'IRS',
      instrumentValuationMethod: '现金流折现',
      instrumentValuationSource: '彭博',
      instrumentFVLevel: 'Level2',
    })).toContain('【G12-4估值】')
  })

  it('citeG12FvValuationToVoucher fills supportingDocDesc and check6', () => {
    const map = new Map([
      ['G12-fv-test-rows', {
        remark: JSON.stringify([{
          hedgeRelationId: 'HR-001',
          instrumentValuationMethod: 'DCF',
          instrumentValuationSource: 'Broker',
          instrumentFVLevel: 'Level2',
        }]),
      }],
    ]) as Map<string, ChecklistResponse>
    const row = enrichG12VoucherRow({ rowId: 'v1', hedgeRelationId: 'HR-001' }, 1)
    const res = citeG12FvValuationToVoucher(row, map)
    expect(res.ok).toBe(true)
    expect(res.patch?.supportingDocDesc).toContain('方法=DCF')
    expect(res.patch?.check6FVValuation).toBe(true)
  })

  it('batchCiteG12FvValuation cites matching rows', () => {
    const map = new Map([
      ['G12-fv-test-rows', {
        remark: JSON.stringify([{
          hedgeRelationId: 'HR-001',
          instrumentValuationMethod: 'DCF',
          instrumentValuationSource: 'Broker',
          instrumentFVLevel: 'Level2',
        }]),
      }],
    ]) as Map<string, ChecklistResponse>
    const rows = [
      enrichG12VoucherRow({ rowId: 'v1', hedgeRelationId: 'HR-001' }, 1),
      enrichG12VoucherRow({ rowId: 'v2', hedgeRelationId: 'HR-X' }, 2),
    ]
    const { cited, skipped, rows: next } = batchCiteG12FvValuation(rows, map)
    expect(cited).toBe(1)
    expect(skipped).toBe(1)
    expect(next[0].supportingDocDesc).toContain('G12-4估值')
  })
})
