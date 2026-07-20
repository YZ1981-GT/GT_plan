/**
 * evaluateMaterialUsageChecks / fee cross / F2-7 reconcile
 */
import { describe, it, expect } from 'vitest'
import {
  evaluateMaterialUsageChecks,
  assessMaterialAbnormal,
  emptyMaterialUsageRow,
  evaluateSubcontractFeeCross,
  reconcileSubcontractWithF27,
} from '../useF2InspectionCheckFormulas'

describe('evaluateMaterialUsageChecks', () => {
  it('flags missing doc when voucher present', () => {
    const row = { ...emptyMaterialUsageRow(1), voucherNo: 'V1', amount: 100, qty: 10 }
    const checks = evaluateMaterialUsageChecks(row)
    expect(checks.find((c) => c.key === 'doc_exist')?.status).toBe('missing')
    expect(assessMaterialAbnormal(row)).toBe(true)
  })

  it('flags qty mismatch', () => {
    const row = {
      ...emptyMaterialUsageRow(1),
      voucherNo: 'V1',
      qty: 10,
      docDateNo: '2025-01-01/D1',
      docQty: 8,
    }
    expect(evaluateMaterialUsageChecks(row).find((c) => c.key === 'qty_doc')?.status).toBe('mismatch')
  })

  it('ok when qty and doc align', () => {
    const row = {
      ...emptyMaterialUsageRow(1),
      voucherNo: 'V1',
      amount: 100,
      qty: 10,
      docDateNo: 'D1',
      docQty: 10,
    }
    const checks = evaluateMaterialUsageChecks(row)
    expect(checks.every((c) => c.status === 'ok')).toBe(true)
    expect(assessMaterialAbnormal({ ...row, abnormalOverride: null })).toBe(false)
  })
})

describe('evaluateSubcontractFeeCross', () => {
  it('pending when all fees empty', () => {
    expect(evaluateSubcontractFeeCross([{ processingFee: 0 }], [{ feeAmount: 0 }], [{ fee: 0 }]).status).toBe('pending')
  })

  it('ok when three tables agree', () => {
    const r = evaluateSubcontractFeeCross(
      [{ processingFee: 100 }, { processingFee: 50 }],
      [{ feeAmount: 150 }],
      [{ fee: 100 }, { fee: 50 }],
    )
    expect(r.status).toBe('ok')
    expect(r.basicFee).toBe(150)
  })

  it('mismatch when tables disagree', () => {
    const r = evaluateSubcontractFeeCross(
      [{ processingFee: 200 }],
      [{ feeAmount: 150 }],
      [{ fee: 100 }],
    )
    expect(r.status).toBe('mismatch')
  })
})

describe('reconcileSubcontractWithF27', () => {
  it('pending without F2-7', () => {
    expect(reconcileSubcontractWithF27(100, null).status).toBe('pending')
  })

  it('ok when equal', () => {
    expect(reconcileSubcontractWithF27(1200.01, 1200.005).status).toBe('ok')
  })

  it('mismatch when differ', () => {
    const r = reconcileSubcontractWithF27(1000, 900)
    expect(r.status).toBe('mismatch')
    expect(r.variance).toBe(100)
  })
})
