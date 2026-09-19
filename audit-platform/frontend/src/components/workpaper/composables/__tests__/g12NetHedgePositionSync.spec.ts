import { describe, it, expect } from 'vitest'
import {
  buildG12PositionMatchKey,
  extractAmortizationFromFvTest,
  extractAmortizationFromVouchers,
  planG12NetPositionSync,
} from '../g12NetHedgePositionSync'
import type { G12HedgeDetailRow } from '../useG12HedgeDetail'
import type { G12NetExposureRow } from '../useG12NetExposure'
import { groupG12AdjustmentsByDesc } from '../g12AdjStorage'

describe('g12NetHedgePositionSync', () => {
  const detailRow = (patch: Partial<G12HedgeDetailRow>): G12HedgeDetailRow => ({
    rowId: patch.rowId ?? 'd1',
    seq: 1,
    item: '预测销售和预测采购的外汇净头寸',
    netPosition: '支付200万美元',
    hedgingInstrument: '远期200万美元',
    rowKind: 'fv_allocation',
    instrumentFvCumulative: 0,
    salesPortion: 0,
    purchasePortion: 0,
    hedgeAdjAmortization: 0,
    indexRef: '',
    remark: '',
    ...patch,
  })

  const neRow = (patch: Partial<G12NetExposureRow>): G12NetExposureRow => ({
    rowId: patch.rowId ?? 'n1',
    seq: 1,
    hedgeRelationId: '',
    item: '预测销售和预测采购的外汇净头寸',
    currency: 'USD',
    position1Desc: '',
    position1Amount: '',
    position2Desc: '',
    position2Amount: '',
    netPosition: '收100万美元',
    netPositionManual: true,
    supportingEvidence: '',
    hedgingInstrument: '远期200万美元',
    indexRef: '',
    ...patch,
  })

  it('buildG12PositionMatchKey uses item+instrument', () => {
    expect(buildG12PositionMatchKey({ item: 'A', hedgingInstrument: 'B' }))
      .toBe(buildG12PositionMatchKey({ item: 'A', hedgingInstrument: 'B' }))
  })

  it('planG12NetPositionSync g12-5 → g12-2', () => {
    const plan = planG12NetPositionSync(
      'g12-5',
      [detailRow({ netPosition: '旧值' })],
      [neRow({ netPosition: '支付200万美元' })],
    )
    expect(plan.syncedCount).toBe(1)
    expect(plan.detailUpdates[0].netPosition).toBe('支付200万美元')
  })

  it('planG12NetPositionSync g12-2 → g12-5', () => {
    const plan = planG12NetPositionSync(
      'g12-2',
      [detailRow({ netPosition: '支付200万美元' })],
      [neRow({ netPosition: '旧值' })],
    )
    expect(plan.syncedCount).toBe(1)
    expect(plan.neUpdates[0].netPosition).toBe('支付200万美元')
  })

  it('extractAmortizationFromFvTest uses ineffectiveness', () => {
    const items = extractAmortizationFromFvTest([
      { hedgeRelationId: 'HR-1', instrumentFVChange: 100, itemFVChange: 80 },
    ])
    expect(items).toHaveLength(1)
    expect(items[0].amount).toBe(-20)
    expect(items[0].source).toBe('G12-4')
  })

  it('extractAmortizationFromVouchers picks 6103 rows', () => {
    const items = extractAmortizationFromVouchers([
      { businessContent: '套期调整摊销', counterAccount: '6103', debitAmount: 0, creditAmount: 240000, voucherNo: '记-001' },
    ])
    expect(items).toHaveLength(1)
    expect(items[0].source).toBe('G12-6')
    expect(items[0].amount).toBe(-240000)
  })
})

describe('groupG12AdjustmentsByDesc', () => {
  it('groups rows by adjustmentDesc', () => {
    const groups = groupG12AdjustmentsByDesc([
      { adjustmentDesc: '事项A', debitAmount: 100, creditAmount: 0 },
      { adjustmentDesc: '事项A', debitAmount: 0, creditAmount: 100 },
      { adjustmentDesc: '事项B', debitAmount: 50, creditAmount: 50 },
    ])
    expect(groups).toHaveLength(2)
    expect(groups[0].balanced).toBe(true)
    expect(groups[0].rows).toHaveLength(2)
  })
})
