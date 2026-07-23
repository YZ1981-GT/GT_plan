import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useK1VoucherCheck,
  pullK1BookAmounts,
  pullK1LargeAmountSpecifics,
  computeK1SamplingPopulation,
  isK1VoucherRowChecksComplete,
  K1_VOUCHER_CHECK_LABELS,
  K1_VOUCHER_PUSH_MARK,
} from '../useK1VoucherCheck'

describe('useK1VoucherCheck', () => {
  it('uses Excel-aligned five-point check labels', () => {
    const map = ref(new Map())
    const vc = useK1VoucherCheck({ allResponses: map })
    expect(vc.checkLabels).toEqual([...K1_VOUCHER_CHECK_LABELS])
    expect(vc.checkLabels[0]).toBe('原始凭证内容完整')
  })

  it('computes check ratios with book occurrence denominators', () => {
    const map = ref(new Map())
    const vc = useK1VoucherCheck({ allResponses: map })
    vc.criteria.value.bookDebitOccurrence = 10000
    vc.criteria.value.bookCreditOccurrence = 5000
    vc.criteria.value.endBalance = 8000
    vc.occurrenceRows.value.push({
      id: 'r1', debtorName: '甲', date: '', voucherNo: 'V1', businessContent: '',
      offsetAccount: '', offsetSubAccount: '', debitAmount: 3000, creditAmount: 0,
      supportingDoc: '', checks: [true, true, true, true, true], indexNo: '', abnormal: false, remark: '',
    })
    vc.postCollectionRows.value.push({
      id: 'r2', debtorName: '甲', date: '', voucherNo: 'V2', businessContent: '',
      offsetAccount: '', offsetSubAccount: '', debitAmount: 0, creditAmount: 2000,
      supportingDoc: '', checks: [true, true, true, true, true], indexNo: '', abnormal: false, remark: '',
    })
    const ratios = vc.checkRatios.value
    expect(ratios[0].ratio).toBeCloseTo(0.3)
    expect(ratios[1].ratio).toBe(0)
    expect(ratios[2].ratio).toBeCloseTo(0.25)
    expect(vc.lowRatioWarnings.value.map(r => r.direction)).toContain('本期贷方')
    expect(vc.lowRatioWarnings.value.map(r => r.direction)).toContain('期末余额')
  })

  it('flags sample size deviation when actual < planned', () => {
    const map = ref(new Map())
    const vc = useK1VoucherCheck({ allResponses: map })
    vc.criteria.value.sampleSize = 5
    vc.occurrenceRows.value.push({
      id: 'r1', debtorName: '', date: '', voucherNo: 'V1', businessContent: '',
      offsetAccount: '', offsetSubAccount: '', debitAmount: 100, creditAmount: 0,
      supportingDoc: '', checks: [false, false, false, false, false], indexNo: '', abnormal: false, remark: '',
    })
    expect(vc.sampleSizeDeviation.value).toEqual({
      planned: 5, actual: 1, diff: -4, needsExpansion: true,
    })
  })

  it('pullK1BookAmounts reads K1-1 and K1-2 keys', () => {
    const map = new Map<string, any>([
      ['K1-1-receivable-count', { remark: '2' }],
      ['K1-1-receivable-r0-debit', { remark: '1000' }],
      ['K1-1-receivable-r0-credit', { remark: '200' }],
      ['K1-1-receivable-r1-debit', { remark: '500' }],
      ['K1-1-receivable-r1-credit', { remark: '100' }],
      ['K1-2-end-subtotal', { remark: '1200' }],
      ['K1-2-detail-rows', { remark: JSON.stringify([
        { counterparty: '关联方A', relatedParty: '是' },
        { counterparty: '客户B', relatedParty: '否' },
      ]) }],
    ])
    const pulled = pullK1BookAmounts(map)
    expect(pulled.debit).toBe(1500)
    expect(pulled.credit).toBe(300)
    expect(pulled.endBalance).toBe(1200)
    expect(pulled.relatedParties).toEqual(['关联方A'])
  })

  it('applyFromK1Sheets fills criteria from cross-sheet data', () => {
    const map = ref(new Map<string, any>([
      ['K1-1-receivable-count', { remark: '1' }],
      ['K1-1-receivable-r0-debit', { remark: '8000' }],
      ['K1-1-receivable-r0-credit', { remark: '1000' }],
      ['K1-2-end-subtotal', { remark: '7000' }],
    ]))
    const vc = useK1VoucherCheck({ allResponses: map })
    const result = vc.applyFromK1Sheets()
    expect(result.filled).toBe(true)
    expect(vc.criteria.value.bookDebitOccurrence).toBe(8000)
    expect(vc.criteria.value.endBalance).toBe(7000)
  })

  it('detects incomplete check rows', () => {
    const map = ref(new Map())
    const vc = useK1VoucherCheck({ allResponses: map })
    const row = {
      id: 'r1', debtorName: '', date: '', voucherNo: 'V1', businessContent: '',
      offsetAccount: '', offsetSubAccount: '', debitAmount: 100, creditAmount: 0,
      supportingDoc: '', checks: [true, true, false, false, false], indexNo: '', abnormal: false, remark: '',
    }
    expect(isK1VoucherRowChecksComplete(row)).toBe(false)
    vc.occurrenceRows.value.push(row)
    expect(vc.incompleteCheckRows.value).toHaveLength(1)
  })

  it('computeK1SamplingPopulation subtracts specific samples', () => {
    const result = computeK1SamplingPopulation({
      populationDebitCount: 80,
      populationCreditCount: 20,
      populationDebitAmount: 800000,
      populationCreditAmount: 200000,
      specificSampleCount: 15,
      specificSampleAmount: 300000,
    })
    expect(result.count).toBe(85)
    expect(result.amount).toBe(700000)
  })

  it('recalcSamplingPopulation updates criteria fields', () => {
    const map = ref(new Map())
    const vc = useK1VoucherCheck({ allResponses: map })
    vc.criteria.value.populationDebitCount = 50
    vc.criteria.value.populationCreditCount = 10
    vc.criteria.value.populationDebitAmount = 500000
    vc.criteria.value.populationCreditAmount = 100000
    vc.criteria.value.specificSampleCount = 5
    vc.criteria.value.specificSampleAmount = 200000
    const derived = vc.recalcSamplingPopulation()
    expect(derived).toEqual({ count: 55, amount: 400000 })
    expect(vc.criteria.value.samplingPopulationCount).toBe(55)
    expect(vc.criteria.value.samplingPopulationAmount).toBe(400000)
  })

  it('pullK1LargeAmountSpecifics reads K1-5 rows above threshold', () => {
    const map = new Map<string, any>([
      ['K1-5-large-rows', { remark: JSON.stringify([
        { counterparty: '甲公司', endBalance: 600000, proportion: 0.6 },
        { counterparty: '乙公司', endBalance: 50000, proportion: 0.05 },
        { counterparty: '丙公司', endBalance: 350000, proportion: 0.35 },
        { counterparty: '丁公司', endBalance: 10000, proportion: 0.01 },
        { counterparty: '戊公司', endBalance: 8000, proportion: 0.008 },
        { counterparty: '己公司', endBalance: 7000, proportion: 0.007 },
      ]) }],
    ])
    const data = pullK1LargeAmountSpecifics(map, 0.1)
    expect(data.count).toBe(2)
    expect(data.counterparties.map(c => c.name)).toEqual(['甲公司', '丙公司'])
    expect(data.totalAmount).toBe(950000)
  })

  it('applyFromK1LargeAmount fills specific sample from K1-5', () => {
    const map = ref(new Map<string, any>([
      ['K1-5-large-rows', { remark: JSON.stringify([
        { counterparty: '甲公司', endBalance: 500000, proportion: 0.5 },
      ]) }],
      ['K1-1-receivable-count', { remark: '1' }],
      ['K1-1-receivable-r0-debit', { remark: '600000' }],
    ]))
    const vc = useK1VoucherCheck({ allResponses: map })
    vc.criteria.value.populationDebitCount = 10
    vc.criteria.value.populationDebitAmount = 600000
    const result = vc.applyFromK1LargeAmount()
    expect(result.filled).toBe(true)
    expect(vc.criteria.value.specificSampleCount).toBe(1)
    expect(vc.criteria.value.specificSampleAmount).toBe(500000)
    expect(vc.criteria.value.specificSample).toContain('甲公司')
    expect(vc.criteria.value.samplingPopulationCount).toBe(9)
  })

  it('buildAbnormalAdjDrafts includes push mark for K1-4 dedup', () => {
    const map = ref(new Map())
    const vc = useK1VoucherCheck({ allResponses: map })
    vc.occurrenceRows.value.push({
      id: 'r1', debtorName: '甲', date: '', voucherNo: '记-001', businessContent: '借款',
      offsetAccount: '', offsetSubAccount: '', debitAmount: 10000, creditAmount: 0,
      supportingDoc: '', checks: [true, true, true, true, true], indexNo: 'K1-12-1',
      abnormal: true, remark: '无合同',
    })
    const drafts = vc.buildAbnormalAdjDrafts()
    expect(drafts).toHaveLength(1)
    expect(drafts[0].summary).toContain(K1_VOUCHER_PUSH_MARK)
    expect(drafts[0].accountCode).toBe('1221')
    expect(drafts[0].remark).toContain('无合同')
  })
})
