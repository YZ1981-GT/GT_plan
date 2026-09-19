import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import {
  migrateVoucherRow,
  useG6EclVoucherCheck,
  validateVoucherRow,
} from '../useG6EclVoucherCheck'

vi.mock('@/utils/http', () => ({
  default: { post: vi.fn() },
}))

describe('useG6EclVoucherCheck', () => {
  it('旧 boolean false 默认迁移为空（未检查），仅异常行转为 N', () => {
    const unchecked = migrateVoucherRow({
      voucherNo: 'PZ-1',
      checkOriginal: true,
      checkAuthorized: true,
      checkAccounting: true,
      checkAmount: false,
      checkInterest: true,
      checkClassification: true,
      isAbnormal: false,
    })
    expect(unchecked.checkOriginal).toBe('Y')
    expect(unchecked.checkInitialCost).toBe('')
    expect(unchecked.isAbnormal).toBe(false)

    const failed = migrateVoucherRow({
      voucherNo: 'PZ-2',
      checkOriginal: true,
      checkAuthorized: false,
      checkAccounting: true,
      checkAmount: true,
      checkInterest: true,
      checkClassification: true,
      isAbnormal: true,
    })
    expect(failed.checkAuthorized).toBe('N')
    expect(failed.isAbnormal).toBe(true)
  })

  it('分别计算本期借贷检查比例，不要求样本集合借贷平衡', () => {
    const vc = useG6EclVoucherCheck(ref('wp-1'), ref('p-1'))
    vc.criteria.value.bookDebitOccurrence = 1000
    vc.criteria.value.bookCreditOccurrence = 500
    vc.loadRows([
      { voucherNo: 'D-1', debitAmount: 300, period: 'occurrence' },
      { voucherNo: 'C-1', creditAmount: 100, period: 'occurrence' },
      { voucherNo: 'POST-1', debitAmount: 900, period: 'post' },
    ])
    expect(vc.debitRatio.value).toBe(0.3)
    expect(vc.creditRatio.value).toBe(0.2)
    expect(vc.postDebitChecked.value).toBe(900)
  })

  it('抽凭回填按 sourceId 去重，期后剔除截止日前凭证', () => {
    const vc = useG6EclVoucherCheck(ref('wp-1'), ref('p-1'), ref({ bsDate: '2025-12-31' }))
    const sample = {
      voucherNo: 'PZ-1',
      voucherDate: '2026-01-05',
      debitAmount: '100',
      creditAmount: '0',
      sourceId: 'ledger-1',
    }
    expect(vc.fillVoucherSamples('post', [sample, sample]).added).toBe(1)
    expect(vc.fillVoucherSamples('post', [sample]).skipped).toBe(1)

    const rejected = vc.fillVoucherSamples('post', [{
      voucherNo: 'OLD',
      voucherDate: '2025-12-01',
      debitAmount: 10,
      creditAmount: 0,
    }], { bsDate: '2025-12-31' })
    expect(rejected.rejectedPostDated).toBe(1)

    const replacement = { ...sample, voucherNo: 'PZ-2', sourceId: 'ledger-2', isHighValue: true }
    vc.fillVoucherSamples('post', [replacement], { mode: 'replace', method: 'systematic' })
    expect(vc.postPeriodRows.value).toHaveLength(1)
    expect(vc.postPeriodRows.value[0].voucherNo).toBe('PZ-2')
    expect(vc.postPeriodRows.value[0].samplingMethod).toBe('systematic')
    expect(vc.postPeriodRows.value[0].selectionCategory).toBe('specific')
  })

  it('样本计划勾稽：特定与代表性分别告警', () => {
    const vc = useG6EclVoucherCheck(ref('wp-1'), ref('p-1'))
    vc.criteria.value.populationDebitCount = 10
    vc.criteria.value.specificSampleCount = 2
    vc.criteria.value.sampleSize = 3
    vc.criteria.value.samplingProcess = '分层后随机'
    vc.loadRows([
      { voucherNo: 'S1', debitAmount: 1, selectionCategory: 'specific', checkOriginal: 'Y', checkAuthorized: 'Y', checkAccounting: 'Y', checkInitialCost: 'Y', checkInterest: 'Y', checkFairValue: 'Y' },
      { voucherNo: 'R1', debitAmount: 1, selectionCategory: 'representative', checkOriginal: 'Y', checkAuthorized: 'Y', checkAccounting: 'Y', checkInitialCost: 'Y', checkInterest: 'Y', checkFairValue: 'Y' },
    ])
    expect(vc.gateWarnings.value.some(w => w.includes('特定样本'))).toBe(true)
    expect(vc.gateWarnings.value.some(w => w.includes('代表性样本'))).toBe(true)
  })

  it('行级质量校验覆盖空凭证号、双金额与异常缺说明', () => {
    const errors = validateVoucherRow({
      ...migrateVoucherRow({}),
      date: '',
      voucherNo: '',
      debitAmount: 10,
      creditAmount: 5,
      isAbnormal: true,
      abnormalNote: '',
      riskLevel: '',
      suggestion: '',
    })
    expect(errors).toEqual(expect.arrayContaining([
      '日期为空',
      '凭证号为空',
      '借贷方同时有金额',
      '异常未填写说明',
      '异常未定风险等级',
      '异常未填处理建议',
    ]))
  })

  it('跨底稿覆盖：G6-12/G6-14 重大事项未抽凭时告警', () => {
    const vc = useG6EclVoucherCheck(ref('wp-1'), ref('p-1'))
    vc.criteria.value.populationDebitAmount = 100000
    vc.evaluateCrossCoverage({
      impairmentRows: [{ currentProvision: 5000 }],
      reversals: [{ reversalAmount: 1000 }],
      writeOffs: [{ writeOffAmount: 2000 }],
      materialityThreshold: 100,
    })
    expect(vc.crossCoverageGaps.value.length).toBe(3)
    expect(vc.gateWarnings.value.some(w => w.includes('G6-12'))).toBe(true)
  })

  it('检查比例超过100%时告警', () => {
    const vc = useG6EclVoucherCheck(ref('wp-1'), ref('p-1'))
    vc.criteria.value.populationDebitCount = 1
    vc.criteria.value.bookDebitOccurrence = 100
    vc.criteria.value.sampleSize = 1
    vc.criteria.value.samplingProcess = '全查'
    vc.loadRows([
      {
        voucherNo: 'D1', debitAmount: 150, period: 'occurrence',
        selectionCategory: 'representative',
        checkOriginal: 'Y', checkAuthorized: 'Y', checkAccounting: 'Y',
        checkInitialCost: 'Y', checkInterest: 'Y', checkFairValue: 'Y',
      },
    ])
    expect(vc.gateWarnings.value.some(w => w.includes('超过100%'))).toBe(true)
  })

  it('N/A 视为已完成但不形成异常', () => {
    const vc = useG6EclVoucherCheck(ref('wp-1'), ref('p-1'))
    const row = migrateVoucherRow({
      checkOriginal: 'Y',
      checkAuthorized: 'Y',
      checkAccounting: 'Y',
      checkInitialCost: 'NA',
      checkInterest: 'NA',
      checkFairValue: 'Y',
    })
    expect(vc.isAllChecked(row)).toBe(true)
    expect(row.isAbnormal).toBe(false)
  })
})
