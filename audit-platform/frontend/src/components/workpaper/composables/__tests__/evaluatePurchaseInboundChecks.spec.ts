/**
 * evaluatePurchaseInboundChecks 契约（F2-33 引导式弹窗实时勾稽面板）。
 * 锁定：逐项状态正确 + 与 assessPurchaseAbnormal 一致（mismatch/missing ⟺ 异常）。
 */
import { describe, it, expect } from 'vitest'
import {
  evaluatePurchaseInboundChecks,
  assessPurchaseAbnormal,
  emptyPurchaseInboundRow,
  type PurchaseInboundRow,
} from '../useF2InspectionCheckFormulas'

function make(p: Partial<PurchaseInboundRow>): PurchaseInboundRow {
  return { ...emptyPurchaseInboundRow(1), ...p }
}

function statusOf(rows: ReturnType<typeof evaluatePurchaseInboundChecks>, key: string) {
  return rows.find((r) => r.key === key)?.status
}

describe('evaluatePurchaseInboundChecks', () => {
  it('全部一致 → 各项 ok，assessPurchaseAbnormal=false', () => {
    const row = make({
      voucherNo: 'PZ-1', amount: 1500, qty: 10,
      recvDateNo: 'RK-1', recvQty: 10,
      invoiceDateNo: 'FP-1', invoiceQty: 10, invoiceAmount: 1500,
    })
    const checks = evaluatePurchaseInboundChecks(row)
    expect(statusOf(checks, 'recv_exist')).toBe('ok')
    expect(statusOf(checks, 'qty_recv')).toBe('ok')
    expect(statusOf(checks, 'qty_invoice')).toBe('ok')
    expect(statusOf(checks, 'amount_invoice')).toBe('ok')
    expect(statusOf(checks, 'recv_invoice_qty')).toBe('ok')
    expect(assessPurchaseAbnormal(row)).toBe(false)
  })

  it('有账无入库单 → missing，且异常', () => {
    const row = make({ voucherNo: 'PZ-2', amount: 800, qty: 5 })
    expect(statusOf(evaluatePurchaseInboundChecks(row), 'recv_exist')).toBe('missing')
    expect(assessPurchaseAbnormal(row)).toBe(true)
  })

  it('账数量 ≠ 入库数量 → mismatch，且异常', () => {
    const row = make({ voucherNo: 'PZ-3', qty: 10, recvDateNo: 'RK-3', recvQty: 8 })
    expect(statusOf(evaluatePurchaseInboundChecks(row), 'qty_recv')).toBe('mismatch')
    expect(assessPurchaseAbnormal(row)).toBe(true)
  })

  it('账金额 ≠ 发票金额（差>0.01）→ mismatch，且异常', () => {
    const row = make({
      voucherNo: 'PZ-4', amount: 1000, qty: 10, recvDateNo: 'RK-4', recvQty: 10,
      invoiceAmount: 1000.5, invoiceQty: 10, invoiceDateNo: 'FP-4',
    })
    expect(statusOf(evaluatePurchaseInboundChecks(row), 'amount_invoice')).toBe('mismatch')
    expect(assessPurchaseAbnormal(row)).toBe(true)
  })

  it('数据不足 → pending，不触发异常', () => {
    const row = make({ party: '甲', invCategory: '原材料' })
    const checks = evaluatePurchaseInboundChecks(row)
    expect(statusOf(checks, 'qty_recv')).toBe('pending')
    expect(statusOf(checks, 'amount_invoice')).toBe('pending')
    expect(assessPurchaseAbnormal(row)).toBe(false)
  })

  it('一致性：任一 mismatch/missing ⟺ 异常（abnormalOverride=null）', () => {
    const cases: Partial<PurchaseInboundRow>[] = [
      { voucherNo: 'a', amount: 100, qty: 1 }, // missing recv
      { voucherNo: 'b', qty: 5, recvQty: 4, recvDateNo: 'r' }, // qty mismatch
      { voucherNo: 'c', qty: 5, recvQty: 5, recvDateNo: 'r', invoiceQty: 6, invoiceDateNo: 'f' }, // recv↔invoice mismatch
    ]
    for (const p of cases) {
      const row = make(p)
      const hasBad = evaluatePurchaseInboundChecks(row).some((r) => r.status === 'mismatch' || r.status === 'missing')
      expect(hasBad).toBe(assessPurchaseAbnormal(row))
    }
  })
})
