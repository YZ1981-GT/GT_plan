/**
 * useG2VoucherCheck — 抽样计划 / 检查比例 / 五项核对 / 抽凭分配
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useG2VoucherCheck,
  calcInspectionRatio,
  G2_CONCLUSION_TEMPLATES,
  G2_EXPANSION_FACTORS,
  suggestSampleSizeByExpansion,
} from '../useG2VoucherCheck'
import type { SampledVoucher } from '../useSamplingAlgorithms'

function makeVc() {
  const allResponses = ref(new Map<string, any>())
  return useG2VoucherCheck({
    wpId: ref('wp-1'),
    projectId: ref('p-1'),
    allResponses,
    isReadonly: ref(false),
  })
}

describe('calcInspectionRatio', () => {
  it('总体为 0 返回 null（避免 DIV/0）', () => {
    expect(calcInspectionRatio(100, 0)).toBeNull()
  })
  it('样本/总体', () => {
    expect(calcInspectionRatio(50, 200)).toBeCloseTo(0.25)
  })
})

describe('useG2VoucherCheck 抽样与核对', () => {
  it('更新抽样计划并计算检查比例', () => {
    const vc = makeVc()
    vc.updateSamplingPlan({ populationDebit: 10000, populationCredit: 0 })
    vc.insertDebitSamples([{ summary: 'a', amount: 1000 }])
    expect(vc.inspectionRatio.value).toBeCloseTo(0.1)
  })

  it('扁平 G2-8-rows 与借/贷区 round-trip', () => {
    const allResponses = ref(new Map<string, any>())
    const vc = useG2VoucherCheck({
      wpId: ref('wp-1'),
      projectId: ref('p-1'),
      allResponses,
      isReadonly: ref(false),
    })
    vc.addDebitRow()
    vc.updateDebitCell(vc.debitRows.value[0].id, 'summary', '利息确认')
    vc.updateDebitCell(vc.debitRows.value[0].id, 'amount', 100)
    vc.updateDebitCell(vc.debitRows.value[0].id, 'faceValue', 10000)
    vc.updateDebitCell(vc.debitRows.value[0].id, 'rate', 3.65)
    vc.updateDebitCell(vc.debitRows.value[0].id, 'accruedDays', 100)
    vc.addCreditRow()
    vc.updateCreditCell(vc.creditRows.value[0].id, 'summary', '收回')
    vc.updateCreditCell(vc.creditRows.value[0].id, 'amount', 50)
    vc.persistFlatExport()
    const flat = allResponses.value.get('G2-8-rows')?.remark
    expect(flat).toBeTruthy()
    const parsed = JSON.parse(String(flat))
    expect(parsed.some((r: any) => r.checkZone === 'debit')).toBe(true)
    expect(parsed.some((r: any) => r.checkZone === 'credit')).toBe(true)

    allResponses.value.delete('G2-8-debit-check-rows')
    allResponses.value.delete('G2-8-credit-check-rows')
    expect(vc.hydrateFromFlat(flat)).toBe(true)
    expect(vc.debitRows.value[0].summary).toBe('利息确认')
    expect(vc.creditRows.value[0].summary).toBe('收回')
    expect(vc.debitRows.value[0].amount).toBe(100)
  })

  it('五项核对失败标异常', () => {
    const vc = makeVc()
    vc.addDebitRow()
    const id = vc.debitRows.value[0].id
    vc.setDebitCheck(id, 'check3Accounting', false)
    expect(vc.debitRows.value[0].isAbnormal).toBe(true)
    expect(vc.abnormalCount.value).toBe(1)
  })

  it('利息差异≥0.01 标异常', () => {
    const vc = makeVc()
    vc.insertDebitSamples([{ amount: 100, faceValue: 10000, rate: 3.65, accruedDays: 365 }])
    // 测算 = 10000*3.65/100*365/365 = 365，差异 265
    expect(vc.debitRows.value[0].calculatedInterest).toBeCloseTo(365)
    expect(vc.debitRows.value[0].isAbnormal).toBe(true)
  })

  it('抽凭样本按借贷分配', () => {
    const vc = makeVc()
    const samples: SampledVoucher[] = [
      {
        voucherNo: '记-1',
        voucherDate: '2025-01-01',
        summary: '计提利息',
        debitAmount: '5000',
        creditAmount: null,
        accountCode: '1132',
        accountName: '应收利息',
        counterpartAccount: '6101',
        voucherType: null,
        accountingPeriod: null,
        checkResult: '',
        abnormal: false,
        remark: '',
        selected: true,
        phase: 'final',
        editTrail: [],
      },
      {
        voucherNo: '记-2',
        voucherDate: '2025-02-01',
        summary: '收到利息',
        debitAmount: null,
        creditAmount: '3000',
        accountCode: '1132',
        accountName: '应收利息',
        counterpartAccount: '1002',
        voucherType: null,
        accountingPeriod: null,
        checkResult: '',
        abnormal: false,
        remark: '',
        selected: true,
        phase: 'final',
        editTrail: [],
      },
    ]
    vc.applySamplingResults(samples, 'append')
    expect(vc.debitRows.value).toHaveLength(1)
    expect(vc.debitRows.value[0].amount).toBe(5000)
    expect(vc.creditRows.value).toHaveLength(1)
    expect(vc.creditRows.value[0].amount).toBe(3000)
  })

  it('从 G2-2 带入总体', () => {
    const allResponses = ref(new Map<string, any>())
    allResponses.value.set('G2-2-detail-rows', {
      remark: JSON.stringify([
        { debit: 800, credit: 200 },
        { debit: 200, credit: 100 },
      ]),
    })
    const vc = useG2VoucherCheck({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses,
      isReadonly: ref(false),
    })
    vc.seedPopulationFromDetail(true)
    expect(vc.samplingPlan.value.populationDebit).toBe(1000)
    expect(vc.samplingPlan.value.populationCredit).toBe(300)
    expect(vc.samplingPlan.value.populationCount).toBe(2)
  })

  it('结论模板与扩展系数常量完整', () => {
    expect(G2_CONCLUSION_TEMPLATES.A).toContain('未见异常')
    expect(G2_EXPANSION_FACTORS).toHaveLength(3)
  })

  it('扩展系数建议样本量', () => {
    expect(suggestSampleSizeByExpansion(100000, 10000, 5)).toBe(16) // 100000*1.6/10000
    expect(suggestSampleSizeByExpansion(0, 10000, 5)).toBeNull()
  })

  it('异常行索引填 G2-4', () => {
    const vc = makeVc()
    vc.insertDebitSamples([{ amount: 100, faceValue: 10000, rate: 3.65, accruedDays: 365 }])
    expect(vc.debitRows.value[0].isAbnormal).toBe(true)
    const n = vc.fillAbnormalIndexToAdjustment(false)
    expect(n).toBe(1)
    expect(vc.debitRows.value[0].indexRef).toBe('G2-4')
  })
})
