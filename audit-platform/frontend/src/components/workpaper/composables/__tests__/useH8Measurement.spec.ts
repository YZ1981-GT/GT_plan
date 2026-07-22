/**
 * useH8Measurement — H8-5 带入 / 差异提示单测
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useH8Measurement,
  listLeaseTermsFromH85Raw,
  pickH85TermOption,
  buildH86AmortSchedule,
} from '../useH8Measurement'

describe('listLeaseTermsFromH85Raw / pickH85TermOption', () => {
  it('解析有效租赁期并优先已结论合同', () => {
    const opts = listLeaseTermsFromH85Raw([
      { recordId: 'a', contractNo: 'A', nonCancellableMonths: 12, conclusion: '' },
      {
        recordId: 'b', contractNo: 'B',
        determinedLeaseTermMonths: 60, conclusion: '是',
      },
    ])
    expect(opts).toHaveLength(2)
    expect(opts[1].months).toBe(60)
    expect(pickH85TermOption(opts)?.contractNo).toBe('B')
    expect(pickH85TermOption(opts, 'A')?.months).toBe(12)
  })
})

describe('useH8Measurement pullLeaseTermFromH85', () => {
  it('从 H8-5 带入并保留其他计量参数', () => {
    const saved = new Map<string, any>()
    const map = ref(new Map<string, any>([
      ['H8-6-params', {
        remark: JSON.stringify({
          leaseLiabilityInitial: 88000,
          directCost: 100,
          incentive: 0,
          discountRate: 5,
          leaseTermMonths: 10,
          rentalPerPeriod: 2000,
          paymentTiming: '期初',
        }),
      }],
      ['H8-5-records', {
        remark: JSON.stringify([{
          recordId: 'r1',
          contractNo: 'ZL-PULL',
          determinedLeaseTermMonths: 48,
          conclusion: '是',
        }]),
      }],
    ]))

    const api = useH8Measurement({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: map,
      onSave: (id, v) => saved.set(id, v),
    })

    const r = api.pullLeaseTermFromH85()
    expect(r.ok).toBe(true)
    expect(r.months).toBe(48)
    expect(r.previousMonths).toBe(10)
    expect(api.measurementParams.value.leaseTermMonths).toBe(48)
    expect(api.measurementParams.value.leaseLiabilityInitial).toBe(88000)
    expect(api.measurementParams.value.paymentTiming).toBe('期初')
    expect(api.measurementParams.value.leaseTermSourceContract).toBe('ZL-PULL')
    expect(saved.get('H8-6-params').leaseTermMonths).toBe(48)
  })

  it('手改租赁期后 h85TermMismatch 提示不一致', () => {
    const map = ref(new Map<string, any>([
      ['H8-5-records', {
        remark: JSON.stringify([{
          recordId: 'r1',
          contractNo: 'ZL-M',
          determinedLeaseTermMonths: 36,
          conclusion: '是',
        }]),
      }],
      ['H8-6-params', {
        remark: JSON.stringify({
          leaseTermMonths: 36,
          leaseTermSourceContract: 'ZL-M',
          leaseTermSyncedFrom: 'H8-5',
          paymentTiming: '期末',
        }),
      }],
    ]))
    const api = useH8Measurement({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: map,
      onSave: () => {},
    })
    expect(api.h85TermMismatch.value).toBeNull()
    api.updateParam('leaseTermMonths', 24)
    expect(api.h85TermMismatch.value).toEqual({
      contractNo: 'ZL-M',
      h85Months: 36,
      h86Months: 24,
    })
  })

  it('H8-5 无记录时 pull 失败', () => {
    const api = useH8Measurement({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(new Map()),
      onSave: () => {},
    })
    const r = api.pullLeaseTermFromH85()
    expect(r.ok).toBe(false)
  })
})

describe('buildH86AmortSchedule', () => {
  it('按年：5 年表末期归零，利息合计>0', () => {
    const r = buildH86AmortSchedule({
      leaseLiabilityInitial: 100_000,
      discountRate: 5,
      leaseTermMonths: 60,
      rentalPerPeriod: 2000, // 月租 → 年付 24000
      branch: '按年计量',
    })
    expect(r.periods).toBe(5)
    expect(r.periodPayment).toBe(24_000)
    expect(r.rows).toHaveLength(5)
    expect(r.validation.isValid).toBe(true)
    expect(Math.abs(r.rows[r.rows.length - 1].endBalance)).toBeLessThan(1)
    expect(r.totalInterest).toBeGreaterThan(0)
  })

  it('按月：12 期表末期归零', () => {
    const r = buildH86AmortSchedule({
      leaseLiabilityInitial: 50_000,
      discountRate: 6,
      leaseTermMonths: 12,
      rentalPerPeriod: 4500,
      branch: '按月计量',
    })
    expect(r.periods).toBe(12)
    expect(r.rows).toHaveLength(12)
    expect(r.validation.isValid).toBe(true)
  })
})
