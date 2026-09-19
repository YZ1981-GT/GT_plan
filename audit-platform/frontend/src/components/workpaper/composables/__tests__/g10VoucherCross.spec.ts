import { describe, expect, it } from 'vitest'
import {
  buildG10VoucherPushItems,
  isFromG107,
  isG10QuantitativeVoucherAbnormal,
  pushG10VoucherAbnormalToAdjustment,
  resolveG10VoucherAdjKind,
} from '../g10VoucherCross'
import type { G10VoucherCheckRow } from '../useG10VoucherCheck'

function baseRow(overrides: Partial<G10VoucherCheckRow> = {}): G10VoucherCheckRow {
  return {
    id: 'v1',
    seq: 1,
    periodScope: 'current',
    voucherDate: '2025-01-15',
    voucherNo: '记-001',
    businessContent: '卖空债券',
    counterAccount: '1002 银行存款',
    debitAmount: 0,
    creditAmount: 50000,
    attachment: null,
    supportingDocDesc: '',
    check1OriginalComplete: true,
    check2Authorization: true,
    check3Accounting: true,
    check4InitialCost: true,
    check5Interest: true,
    check6FairValueCorrect: true,
    indexNo: '',
    isAbnormal: false,
    abnormalDesc: '',
    riskLevel: '',
    remark: '',
    source: '抽凭',
    ...overrides,
  }
}

describe('g10VoucherCross', () => {
  it('isG10QuantitativeVoucherAbnormal 识别金额类异常', () => {
    const row = baseRow({
      isAbnormal: true,
      check6FairValueCorrect: false,
      creditAmount: 1000,
    })
    expect(isG10QuantitativeVoucherAbnormal(row)).toBe(true)
    expect(isG10QuantitativeVoucherAbnormal(baseRow({ isAbnormal: true, check1OriginalComplete: false }))).toBe(false)
  })

  it('resolveG10VoucherAdjKind 按失败项优先级', () => {
    expect(resolveG10VoucherAdjKind(baseRow({ check6FairValueCorrect: false }))).toBe('fv')
    expect(resolveG10VoucherAdjKind(baseRow({ check5Interest: false }))).toBe('interest')
    expect(resolveG10VoucherAdjKind(baseRow({ check4InitialCost: false }))).toBe('cost')
  })

  it('pushG10VoucherAbnormalToAdjustment 公允异常 Dr6101/Cr2101', () => {
    const row = baseRow({
      isAbnormal: true,
      check6FairValueCorrect: false,
      creditAmount: 800,
    })
    const saves: Array<{ id: string; data: any }> = []
    const responses = new Map<string, { remark?: string }>()
    const { pushed } = pushG10VoucherAbnormalToAdjustment(
      responses as any,
      (id, data) => {
        saves.push({ id, data })
        responses.set(id, data as any)
      },
      [row],
    )
    expect(pushed).toBe(1)
    const rows = JSON.parse(String(saves.find((s) => s.id === 'G10-aje-rows')?.data.remark))
    expect(rows).toHaveLength(2)
    expect(rows.find((r: any) => r.accountCode === '6101').debitAmount).toBe(800)
    expect(rows.find((r: any) => r.accountCode === '2101').creditAmount).toBe(800)
    expect(isFromG107(rows[0])).toBe(true)
  })

  it('buildG10VoucherPushItems 跳过无金额异常', () => {
    expect(buildG10VoucherPushItems([
      baseRow({ isAbnormal: true, check6FairValueCorrect: false, creditAmount: 0, debitAmount: 0 }),
    ])).toHaveLength(0)
  })
})
